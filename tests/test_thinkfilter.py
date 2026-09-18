import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.ollama_client import ThinkFilter


def run_case(name, chunks, expected):
    tf = ThinkFilter()
    out = []
    for c in chunks:
        text, _ = tf.feed(c)
        out.append(text)
    out.append(tf.flush())
    got = "".join(out)
    assert got == expected, f"{name}: got {got!r}, want {expected!r}"


run_case("basic", ["<think>推理</think>", "你好"], "你好")
run_case("split-tag", ["前文<thi", "nk>隐", "藏</th", "ink>后文"], "前文后文")
run_case("char-by-char", list("<think>abc</think>def"), "def")
run_case("no-think", ["直接回答", "继续"], "直接回答继续")
run_case("unclosed", ["<think>还在想"], "")
run_case("false-prefix", ["a<b", "c<think>x</think>d"], "a<bcd")
run_case("multiple-thinks", ["A<think>1</think>B<think>2</think>C"], "ABC")
run_case("empty", [], "")

print("ThinkFilter 全部用例通过")
