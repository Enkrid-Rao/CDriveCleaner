#!/usr/bin/env python3
"""_CDrive 重组 —— 把散落在 D 盘根目录的「C 盘迁移目标」收进 D:\\_CDrive。

背景
----
CDriveCleaner 早期把 C 盘目录迁到 D 盘时，目标路径是 D:\\AppData\\xxx、
D:\\Cache\\xxx 这种，直接摊在 D 盘根目录，导致根目录臃肿。
本脚本把这些目标按「C 盘原路径」重新组织到 D:\\_CDrive 下，并重建 junction。

单个迁移项的处理流程
--------------------
    ① 校验 C:\\P 确实是 junction，且目标在 D 盘
    ② 算出新路径  NewP = D:\\_CDrive + (C:\\P 去掉盘符)
    ③ rd  "C:\\P"              删 junction 本身 —— 只删链接，绝不碰数据
    ④ move 旧目标 → NewP        同卷移动 = 改文件系统索引，秒级，不复制数据
    ⑤ mklink /J "C:\\P" NewP    重建链接指向新位置
    ⑥ 验证 C:\\P 的目标是否等于 NewP

安全设计（重要）
----------------
1. **默认 dry-run**，只打印计划；加 --execute 才真正执行
2. 删除前强制校验 reparse 属性 —— 不是 junction 一律跳过
3. 删 junction 用 os.rmdir（删链接本身）；**绝不使用 shutil.rmtree**（那会删掉真实数据）
4. 第 ④ 或 ⑤ 步失败时**自动回滚**：把数据移回原位 + 重建 junction 指回旧路径
5. 新路径已存在且非空时跳过，不覆盖
6. 执行前自动导出**快照**（当前所有 junction 状态），事后可对照
7. 每项结果写入**执行日志**；出问题可用 `--rollback <日志>` 一键反向恢复

为什么数据不会丢
----------------
- `rd` 删的是 reparse point，物理上碰不到目标数据
- `move` 在同一个卷内是文件系统索引操作，是原子的，不存在「复制到一半」
- 最坏情况：所有 junction 都断了，但数据完整躺在 D 盘上，重建链接即可恢复

用法
----
    python reorganize_cdrive.py                          # dry-run，看计划
    python reorganize_cdrive.py --execute --only NGR     # 先拿单项试点
    python reorganize_cdrive.py --execute --skip-admin   # 跳过需管理员的两项
    python reorganize_cdrive.py --rollback logs/xxx.log  # 回滚
"""

from __future__ import annotations

import argparse
import os
import stat
import subprocess
import sys
import time

NEW_BASE = r"D:\_CDrive"
REPARSE = getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0x400)

# 扫描这些根目录下的 junction
_USERPROFILE = os.environ.get("USERPROFILE") or os.path.expanduser("~")
SCAN_ROOTS = [
    _USERPROFILE,
    r"C:\ProgramData",
    r"C:\Program Files",
    r"C:\Program Files (x86)",
]

# 这些路径下的链接不参与重组
SKIP_PATTERNS = ("node_modules", "\\Packages\\", "\\.agents\\")

# 需要管理员权限的项（路径前缀）
ADMIN_PREFIXES = (r"C:\ProgramData", r"C:\Program Files")

# 迁移前应关闭的进程（提示用，不做强制）
WARN_PROCESSES = (
    "chrome", "msedge", "Code", "CodeBuddy", "Trae", "cursor", "idea64",
    "pycharm64", "clion64", "WeChat", "Weixin", "QQ", "DingTalk",
    "JianyingPro", "Doubao", "Quark", "IDMan", "steam", "bilibili",
    "WorkBuddy", "ZTools", "Qwen", "DaVinci", "Resolve",
)

LOG_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "logs")


# ---------------------------------------------------------------- 基础工具

def is_reparse(path: str) -> bool:
    try:
        return bool(os.lstat(path).st_file_attributes & REPARSE)
    except Exception:
        return False


def junction_target(path: str) -> str | None:
    r"""读 junction 的目标路径。Windows 上返回 \\?\D:\... 或 \??\D:\... 形式。"""
    try:
        t = os.readlink(path)
    except Exception:
        return None
    for prefix in ("\\\\?\\", "\\??\\"):
        if t.startswith(prefix):
            t = t[len(prefix):]
            break
    return t


def new_path_for(cpath: str) -> str:
    assert cpath[1] == ":"
    return NEW_BASE + cpath[2:]


def make_junction(link: str, target: str) -> bool:
    r = subprocess.run(["cmd", "/c", "mklink", "/J", link, target],
                       capture_output=True, text=True)
    return r.returncode == 0


def walk_junctions(root: str, depth: int = 6):
    stack = [(root, 0)]
    while stack:
        d, lv = stack.pop()
        if lv > depth:
            continue
        try:
            with os.scandir(d) as it:
                for e in it:
                    try:
                        p = e.path
                        if is_reparse(p):
                            if e.is_dir(follow_symlinks=False):
                                t = junction_target(p)
                                # 只挑「目标在 D 盘、但还不在 _CDrive 里」的，已完成的跳过
                                if (t and t.upper().startswith("D:\\")
                                        and not t.upper().startswith(NEW_BASE.upper())):
                                    if not any(s in p for s in SKIP_PATTERNS):
                                        yield p, t
                            continue  # 不递归进链接
                        if not e.is_dir(follow_symlinks=False):
                            continue
                        if any(s in p for s in SKIP_PATTERNS):
                            continue
                        stack.append((p, lv + 1))
                    except Exception:
                        pass
        except Exception:
            pass


def build_plan() -> list[dict]:
    items = []
    for root in SCAN_ROOTS:
        if not os.path.isdir(root):
            continue
        for cpath, old in walk_junctions(root):
            items.append({
                "cpath": cpath,
                "old": old,
                "new": new_path_for(cpath),
                "admin": cpath.startswith(ADMIN_PREFIXES),
                "name": os.path.basename(cpath),
            })
    items.sort(key=lambda x: x["cpath"])
    return items


def is_admin() -> bool:
    try:
        import ctypes
        return bool(ctypes.windll.shell32.IsUserAnAdmin())
    except Exception:
        return False


def running_processes() -> list[str]:
    try:
        out = subprocess.run(["tasklist", "/FO", "CSV", "/NH"],
                             capture_output=True, text=True, timeout=30).stdout
    except Exception:
        return []
    low = out.lower()
    return [p for p in WARN_PROCESSES if f'"{p.lower()}"' in low
            or f'"{p.lower()}.exe"' in low]


# ---------------------------------------------------------------- 快照 / 日志

def write_snapshot(plan: list[dict]) -> str:
    os.makedirs(LOG_DIR, exist_ok=True)
    ts = time.strftime("%Y%m%d-%H%M%S")
    path = os.path.join(LOG_DIR, f"junction_snapshot_{ts}.txt")
    with open(path, "w", encoding="utf-8") as f:
        f.write(f"# _CDrive 重组前的 junction 快照  {ts}\n")
        f.write(f"# 格式：C盘路径 <TAB> 旧D盘目标 <TAB> 计划新路径\n")
        for it in plan:
            f.write(f"{it['cpath']}\t{it['old']}\t{it['new']}\n")
    return path


def append_log(logpath: str, item: dict, status: str) -> None:
    with open(logpath, "a", encoding="utf-8") as f:
        f.write(f"{item['cpath']}\t{item['old']}\t{item['new']}\t{status}\n")


# ---------------------------------------------------------------- 执行

def do_one(item: dict, dry_run: bool) -> tuple[str, str]:
    cpath, old, new = item["cpath"], item["old"], item["new"]

    if not is_reparse(cpath):
        return "SKIP", "不是 junction（可能已处理过）"
    cur = junction_target(cpath)
    if cur != old:
        return "SKIP", f"目标已变化：{cur}"
    if os.path.exists(new):
        try:
            if os.listdir(new):
                return "SKIP", f"新路径已存在且非空：{new}"
        except Exception:
            return "SKIP", f"新路径不可读：{new}"

    if dry_run:
        return "PLAN", f"{old}\n            → {new}"

    # ③ 删 junction（只删链接本身）
    try:
        os.rmdir(cpath)
    except Exception as e:
        return "FAIL", f"删除 junction 失败（未动数据）：{e}"

    # ④ 同卷移动数据
    try:
        os.makedirs(os.path.dirname(new), exist_ok=True)
        os.rename(old, new)
    except Exception as e:
        make_junction(cpath, old)
        return "FAIL", f"移动失败（已回滚）：{e}"

    # ⑤ 重建 junction
    if not make_junction(cpath, new):
        try:
            os.rename(new, old)
            make_junction(cpath, old)
        except Exception:
            pass
        return "FAIL", "mklink 失败（已回滚）"

    # ⑥ 验证
    if junction_target(cpath) == new:
        return "OK", f"{cpath}\n            → {new}"
    return "WARN", "重建成功但验证异常，请手工确认"


def rollback(logfile: str) -> int:
    """读执行日志，把 OK 的项反向恢复。"""
    if not os.path.isfile(logfile):
        print(f"日志不存在：{logfile}")
        return 2

    rows = []
    with open(logfile, encoding="utf-8") as f:
        for line in f:
            parts = line.rstrip("\n").split("\t")
            if len(parts) == 4 and parts[3] == "OK":
                rows.append(parts[:3])

    if not rows:
        print("日志里没有成功的项，无需回滚。")
        return 0

    print(f"将回滚 {len(rows)} 项：")
    ok = fail = 0
    for cpath, old, new in reversed(rows):
        print(f"\n  {cpath}")
        if is_reparse(cpath):
            try:
                os.rmdir(cpath)
            except Exception as e:
                print(f"    ✗ 删链接失败：{e}")
                fail += 1
                continue
        if os.path.exists(new):
            try:
                os.makedirs(os.path.dirname(old), exist_ok=True)
                os.rename(new, old)
            except Exception as e:
                print(f"    ✗ 移回失败：{e}")
                fail += 1
                continue
        if make_junction(cpath, old):
            print(f"    ✓ 已恢复 → {old}")
            ok += 1
        else:
            print("    ✗ 重建链接失败")
            fail += 1

    print(f"\n回滚完成：成功 {ok}，失败 {fail}")
    return 1 if fail else 0


def main() -> int:
    ap = argparse.ArgumentParser(description="_CDrive 重组（默认 dry-run）")
    ap.add_argument("--execute", action="store_true", help="真正执行（默认只打印计划）")
    ap.add_argument("--only", default="", help="只处理这些名字，逗号分隔")
    ap.add_argument("--skip-admin", action="store_true", help="跳过 ProgramData / Program Files")
    ap.add_argument("--rollback", metavar="LOGFILE", help="按执行日志回滚")
    args = ap.parse_args()

    if args.rollback:
        return rollback(args.rollback)

    plan = build_plan()
    if args.only:
        want = {s.strip().lower() for s in args.only.split(",") if s.strip()}
        plan = [i for i in plan if i["name"].lower() in want]
    if args.skip_admin:
        plan = [i for i in plan if not i["admin"]]

    if not plan:
        print("没有找到需要处理的 junction。")
        return 0

    admin_items = [i for i in plan if i["admin"]]

    print(f"目标容器：{NEW_BASE}")
    print(f"待处理：{len(plan)} 项（其中需要管理员权限 {len(admin_items)} 项）")
    print("=" * 72)

    logpath = ""
    if args.execute:
        snap = write_snapshot(plan)
        print(f"快照已保存：{snap}")
        ts = time.strftime("%Y%m%d-%H%M%S")
        logpath = os.path.join(LOG_DIR, f"reorganize_{ts}.log")
        with open(logpath, "w", encoding="utf-8") as f:
            f.write("# C盘路径\t旧目标\t新路径\t结果\n")
        print(f"执行日志：{logpath}")

        procs = running_processes()
        if procs:
            print()
            print("⚠️  检测到以下进程正在运行，强烈建议先关闭再执行：")
            print("   " + ", ".join(procs))
        if admin_items and not is_admin():
            print(f"\n⚠️  有 {len(admin_items)} 项需要管理员权限，当前不是管理员，这些项会失败。")
        print()

    counts = {"PLAN": 0, "OK": 0, "SKIP": 0, "FAIL": 0, "WARN": 0}
    failures = []

    for i, item in enumerate(plan, 1):
        status, msg = do_one(item, dry_run=not args.execute)
        counts[status] = counts.get(status, 0) + 1
        tag = {"PLAN": "计划", "OK": "完成", "SKIP": "跳过",
               "FAIL": "失败", "WARN": "警告"}.get(status, status)
        print(f"[{i:2}/{len(plan)}] {tag}  {msg}")
        if args.execute and logpath:
            append_log(logpath, item, status)
        if status == "FAIL":
            failures.append((item["cpath"], msg))

    print("=" * 72)
    print(f"计划 {counts['PLAN']} | 完成 {counts['OK']} | 跳过 {counts['SKIP']} "
          f"| 失败 {counts['FAIL']} | 警告 {counts['WARN']}")

    if not args.execute:
        print("\n这是 dry-run，没有做任何改动。确认无误后加 --execute 执行。")
    elif logpath:
        print(f"\n如需回滚：python reorganize_cdrive.py --rollback \"{logpath}\"")

    if failures:
        print("\n失败项：")
        for p, m in failures:
            print(f"  {p}\n    {m}")

    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
