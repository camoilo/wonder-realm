"""启动脚本（*.bat）的编码与行尾约定（DEVELOPMENT §9.8）。

cmd 在 **65001 代码页**下读一个多字节的 bat 时按字节偏移续读，位置会算歪，于是从半行中间
开始当命令执行，双击时报：

    '所以这里查的是那个可执行文件本身，缺了就分两种情况给出各自该跑的命令。'
    is not recognized as an internal or external command

两个变体都真实踩过：裸 LF（行尾错位）与 UTF-8 + `chcp 65001`（字节错位）。所以仓库里的
bat 一律 **GBK + CRLF**，并且不许出现 `chcp 65001`。这条守卫就是钉住这两点。
"""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

FAILED = []


def check(name, got, want):
    ok = got == want
    print(("PASS  " if ok else "FAIL  ") + name + ("" if ok else f"  got={got!r} want={want!r}"))
    if not ok:
        FAILED.append(name)


bats = sorted(ROOT.glob("*.bat"))
check("根目录至少有 start.bat 与 start_desktop.bat", len(bats) >= 2, True)

for p in bats:
    raw = p.read_bytes()
    check(f"{p.name} 只有 CRLF（没有裸 LF）", raw.count(b"\n") - raw.count(b"\r\n"), 0)

    if any(b > 0x7F for b in raw):  # 有中文才谈编码
        try:
            raw.decode("utf-8")
            is_utf8 = True
        except UnicodeDecodeError:
            is_utf8 = False
        # GBK 的中文几乎不会是合法 UTF-8 序列，所以"能被 UTF-8 解开"就等于"存成了 UTF-8"
        check(f"{p.name} 中文不是 UTF-8 存的（即 GBK）", is_utf8, False)
        try:
            raw.decode("gbk")
            gbk_ok = True
        except UnicodeDecodeError:
            gbk_ok = False
        check(f"{p.name} 能按 GBK 解码", gbk_ok, True)

    # 注释里提"65001"是有意的（写明为什么不用它），所以只看真正会执行的行
    code = [
        ln for ln in raw.decode("gbk", "replace").splitlines()
        if not ln.strip().lower().startswith("rem")
    ]
    check(f"{p.name} 不用 chcp 65001", "chcp 65001" not in "\n".join(code).lower(), True)

# 电脑端入口的关键结构：改坏了（去掉依赖检查或前端重建）要报红
desk = (ROOT / "start_desktop.bat").read_bytes().decode("gbk")
check("电脑端入口检查的是 electron.exe 本体", "node_modules\\electron\\dist\\electron.exe" in desk, True)
check("电脑端入口分两种情况提示", desk.count("[X]") >= 2, True)
check("电脑端入口顺手重建前端", "npm run build" in desk, True)

print()
if FAILED:
    print(f"失败 {len(FAILED)} 项：{FAILED}")
    sys.exit(1)
print("启动脚本约定用例全部通过")
