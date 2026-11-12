#!/usr/bin/env python3
"""冷数据外迁：D 盘 → E 盘（仓库盘）。

为什么不用 robocopy /MOVE
------------------------
/MOVE 是「复制一个文件、删一个文件」的流式行为。中途断电、盘掉线、目标空间不足，
就会出现「源删了、目标没写全」的状态，数据直接丢。
本脚本坚持三步分离：**复制 → 校验 → 删源**，中间任一步失败都不动源。

流程
----
    ① robocopy 复制      源 → 目标（/E 含空目录，/COPY:DAT 保留属性时间戳）
    ② 校验              对比文件数 + 总字节数，不一致就中止
    ③ 删源（可选）      只有 --delete-source 才执行，且必须第 ② 步通过

用法
----
    python migrate_to_e.py --list
    python migrate_to_e.py --src "D:\\AppStore" --dst "E:\\Software\\Installers\\MYOS"
    python migrate_to_e.py --src "D:\\AppStore" --dst "E:\\Software\\Installers\\MYOS" --execute
    ... 加上 --delete-source 才会删源
"""

from __future__ import annotations

import argparse
import os
import subprocess
import sys
import tempfile

# 建议的迁移清单（--list 展示用，不会自动执行）
SUGGESTED = [
    (r"D:\AppStore",                      r"E:\Software\Installers\MYOS",      "MYOS 取证工具安装包，装完即废"),
    (r"D:\Downloads\02-ISOs",             r"E:\Software\ISOs",                 "装机镜像"),
    (r"D:\Downloads\01-Software",         r"E:\Software\Installers",           "软件安装包"),
    (r"D:\Videos\剪映",                    r"E:\Media\Videos\Projects",         "剪映成片（先清理重复版本）"),
    (r"D:\Videos\屏幕录制",                r"E:\Media\Videos\ScreenRecord",     "屏幕录制"),
    (r"D:\Downloads\09-Media",            r"E:\Media\Misc",                    "下载的影音"),
    (r"D:\qq聊天记录\Downloads",           r"E:\Archive\QQ\Downloads",          "QQ 接收的历史文件"),
]


def run(cmd: list[str], timeout: int = 3600) -> int:
    return subprocess.run(cmd, capture_output=True, timeout=timeout).returncode


def stats(path: str) -> tuple[int, int]:
    """返回 (文件数, 总字节)。"""
    n = 0
    total = 0
    for dirpath, _dirnames, filenames in os.walk(path):
        for f in filenames:
            try:
                total += os.path.getsize(os.path.join(dirpath, f))
                n += 1
            except OSError:
                pass
    return n, total


def human(b: int) -> str:
    for unit in ("B", "KB", "MB", "GB", "TB"):
        if b < 1024:
            return f"{b:.2f} {unit}"
        b /= 1024
    return f"{b:.2f} PB"


def copy_tree(src: str, dst: str) -> bool:
    """robocopy 复制。退出码 < 8 视为成功。"""
    os.makedirs(dst, exist_ok=True)
    rc = run(["robocopy", src, dst, "/E", "/COPY:DAT", "/R:2", "/W:2",
              "/NP", "/NFL", "/NDL"])
    return rc < 8


def empty_source(src: str) -> bool:
    """用空目录 /MIR 清空源（比 shutil.rmtree 更能处理只读/长路径）。"""
    empty = os.path.join(tempfile.gettempdir(), "_migrate_empty")
    os.makedirs(empty, exist_ok=True)
    rc = run(["robocopy", empty, src, "/MIR", "/R:1", "/W:1", "/NP",
              "/NFL", "/NDL"])
    if rc >= 8:
        return False
    try:
        os.rmdir(src)
    except OSError:
        pass  # 留个空壳也无妨
    return True


def main() -> int:
    ap = argparse.ArgumentParser(description="冷数据外迁 D → E（默认 dry-run）")
    ap.add_argument("--list", action="store_true", help="列出建议的迁移清单")
    ap.add_argument("--src", help="源目录")
    ap.add_argument("--dst", help="目标目录")
    ap.add_argument("--execute", action="store_true", help="真正执行复制")
    ap.add_argument("--delete-source", action="store_true",
                    help="校验通过后删除源目录（危险，确认后再用）")
    args = ap.parse_args()

    if args.list:
        print("建议的迁移清单：\n")
        print(f"{'源':<38} {'目标':<42} 说明")
        print("-" * 110)
        for s, d, note in SUGGESTED:
            exists = "✓" if os.path.exists(s) else "✗"
            size = ""
            if os.path.exists(s):
                n, b = stats(s)
                size = f" [{human(b)}]"
            print(f"{s:<38} {d:<42} {note}{size} {exists}")
        print("\n✗ 表示该目录当前不存在（可能还没建）。")
        print("实际迁移时用 --src / --dst 指定。")
        return 0

    if not args.src or not args.dst:
        ap.print_help()
        return 2

    src, dst = args.src, args.dst
    if not os.path.isdir(src):
        print(f"源目录不存在：{src}")
        return 2
    if os.path.abspath(dst).startswith(os.path.abspath(src)):
        print("目标不能位于源内部。")
        return 2

    n_src, b_src = stats(src)
    print(f"源   {src}")
    print(f"      {n_src} 个文件，{human(b_src)}")
    print(f"目标 {dst}")
    print("-" * 60)

    if not args.execute:
        print("这是 dry-run。加 --execute 执行复制。")
        return 0

    # ① 复制
    print("① 复制中（robocopy）…")
    if not copy_tree(src, dst):
        print("   复制失败，源目录未动。")
        return 1
    print("   复制完成。")

    # ② 校验
    print("② 校验中…")
    n_dst, b_dst = stats(dst)
    print(f"   源：{n_src} 文件 / {human(b_src)}")
    print(f"   目标：{n_dst} 文件 / {human(b_dst)}")
    if (n_src, b_src) != (n_dst, b_dst):
        print("   ✗ 不一致，已中止，源目录未删。请手工核对。")
        return 1
    print("   ✓ 一致。")

    # ③ 删源
    if args.delete_source:
        print("③ 删除源目录…")
        if empty_source(src):
            print("   ✓ 已删除。")
        else:
            print("   ✗ 删除失败，源仍在，请手工处理。")
            return 1
    else:
        print("③ 未指定 --delete-source，源目录保留。")
        print("   确认目标无误后，可手工删除源，或重跑时加上 --delete-source。")

    return 0


if __name__ == "__main__":
    sys.exit(main())
