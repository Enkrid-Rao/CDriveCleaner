#!/usr/bin/env python3
"""把用户库（Pictures / Videos / Music）并入 D:\\_CDrive，并重建 junction。

为什么用 junction 而不是「属性 → 位置」重定向
--------------------------------------------
位置重定向要求目标目录不存在或为空。但 reorganize_cdrive.py 已经把
Pictures\\Screenshots 搬到了 D:\\_CDrive\\Users\\<用户>\\Pictures\\Screenshots，
目标非空，重定向会失败。junction 没有这个限制，且效果一样（软件无感知）。

前提
----
先跑过 reorganize_cdrive.py。它会处理掉 Pictures\\Screenshots 那个 junction，
把数据挪到 _CDrive 里。本脚本随后接管整个 Pictures / Videos / Music 库。

处理流程（对每个库）
--------------------
    ① src 已是 junction → 跳过
    ② 删掉 src 里的 junction（如 Screenshots）—— 数据已在 _CDrive，删链接不丢数据
    ③ D:\\Media\\<库> 的内容 → 并入 _CDrive\\Users\\<用户>\\<库>
    ④ src 里的真实内容 → 同样并入
    ⑤ 删掉 src 空目录
    ⑥ mklink /J src → _CDrive 目标

安全设计
--------
- 默认 dry-run；--execute 才执行
- 同名冲突时跳过并警告，不覆盖
- 只删「已确认内容搬空」的目录
- 绝不使用 shutil.rmtree（改为 cmd rd，可处理只读/系统属性文件）

用法
----
    python migrate_userlibs.py              # dry-run
    python migrate_userlibs.py --execute
"""

from __future__ import annotations

import argparse
import os
import shutil
import stat
import subprocess
import sys

NEW_BASE = r"D:\_CDrive"
REPARSE = getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0x400)

USERPROFILE = os.environ.get("USERPROFILE") or os.path.expanduser("~")
USERNAME = os.environ.get("USERNAME") or os.path.basename(USERPROFILE)

# (库名, 旧落点 D:\Media\<名>)
LIBS = [
    ("Pictures", r"D:\Media\Pictures"),
    ("Videos",   r"D:\Media\Videos"),
    ("Music",    r"D:\Media\Music"),
]

SKIP_NAMES = {"desktop.ini", "thumbs.db"}


def is_reparse(path: str) -> bool:
    try:
        return bool(os.lstat(path).st_file_attributes & REPARSE)
    except Exception:
        return False


def force_rmdir(path: str) -> bool:
    """删除目录（调用方需先确认内容已搬空）。cmd rd 能处理系统属性文件。"""
    subprocess.run(["cmd", "/c", "rd", "/s", "/q", path], capture_output=True)
    return not os.path.exists(path)


def move_children(src: str, dst: str, dry: bool, label: str) -> list[str]:
    """把 src 下的条目移到 dst，返回冲突项列表。"""
    conflicts = []
    if not os.path.isdir(src):
        return conflicts
    os.makedirs(dst, exist_ok=True)
    for name in os.listdir(src):
        if name.lower() in SKIP_NAMES:
            continue
        s = os.path.join(src, name)
        if is_reparse(s):
            continue  # 已在 ② 步删除；dry-run 下也跳过，保证输出与实际一致
        d = os.path.join(dst, name)
        if os.path.exists(d):
            conflicts.append(f"{label}: {name}（目标已存在，跳过）")
            continue
        print(f"    move  {s}\n       →  {d}")
        if not dry:
            try:
                os.rename(s, d)          # 同卷（D 盘内）：只改索引，秒级
            except Exception:
                try:
                    shutil.move(s, d)    # 跨卷（C → D）：复制 + 删源
                except Exception as e:
                    conflicts.append(f"{label}: {name} 移动失败（{e}）")
    return conflicts


def do_lib(name: str, media_src: str, dry: bool) -> int:
    src = os.path.join(USERPROFILE, name)
    dst = os.path.join(NEW_BASE, "Users", USERNAME, name)

    print(f"\n{'=' * 68}\n【{name}】")
    print(f"  src = {src}")
    print(f"  dst = {dst}")
    print(f"  old = {media_src}")

    if not os.path.exists(src):
        print("  src 不存在，跳过。")
        return 0

    if is_reparse(src):
        print("  src 已是 junction，已处理过，跳过。")
        return 0

    # ② 先删 src 里的 junction（数据已在 _CDrive）
    for entry in os.listdir(src):
        p = os.path.join(src, entry)
        if is_reparse(p):
            print(f"    删除 junction：{p}")
            if not dry:
                try:
                    os.rmdir(p)
                except Exception as e:
                    print(f"      失败：{e}")

    conflicts: list[str] = []

    # ③ 旧落点内容并入
    if os.path.isdir(media_src):
        print(f"  从旧落点 {media_src} 并入：")
        conflicts += move_children(media_src, dst, dry, "旧落点")

    # ④ src 真实内容并入
    print(f"  从 {src} 并入：")
    conflicts += move_children(src, dst, dry, "源目录")

    # ⑤ 删 src 空目录 —— 先确认真的搬空了，否则绝不删
    if not dry:
        remaining = ([x for x in os.listdir(src)
                      if x.lower() not in SKIP_NAMES
                      and not is_reparse(os.path.join(src, x))]
                     if os.path.isdir(src) else [])
        if remaining:
            print(f"    ⚠️ 源目录仍有 {len(remaining)} 项未搬走，**跳过删除**，请手工检查：")
            for x in remaining[:10]:
                print(f"       - {x}")
            return 1
        if os.path.isdir(src) and force_rmdir(src):
            print("    源目录已清空删除。")
        elif os.path.isdir(src):
            print("    ⚠️ 源目录未删干净，请手工检查。")
    else:
        print("    （dry-run：将删除源目录并重建 junction）")

    # ⑥ 重建 junction
    print(f"    mklink /J \"{src}\" \"{dst}\"")
    if not dry:
        r = subprocess.run(["cmd", "/c", "mklink", "/J", src, dst],
                           capture_output=True, text=True)
        if r.returncode != 0:
            print(f"    ✗ 创建失败：{r.stderr.strip() or r.stdout.strip()}")
            return 1
        print("    ✓ 完成")

    for c in conflicts:
        print(f"    ⚠️ {c}")
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(description="用户库并入 _CDrive（默认 dry-run）")
    ap.add_argument("--execute", action="store_true", help="真正执行")
    args = ap.parse_args()
    dry = not args.execute

    print(f"用户：{USERNAME}")
    print(f"容器：{NEW_BASE}")
    if dry:
        print("模式：dry-run（不做任何改动）")
    else:
        print("模式：**执行**")

    rc = 0
    for name, media_src in LIBS:
        rc |= do_lib(name, media_src, dry)

    # 顺手检查 D:\Media 是否已空
    media = r"D:\Media"
    if os.path.isdir(media):
        left = [x for x in os.listdir(media)
                if x.lower() not in SKIP_NAMES]
        if left:
            print(f"\n注：{media} 仍有内容：{', '.join(left)}")
        else:
            print(f"\n注：{media} 已空，可手工删除。")

    if dry:
        print("\n这是 dry-run。确认无误后加 --execute 执行。")
    return rc


if __name__ == "__main__":
    sys.exit(main())
