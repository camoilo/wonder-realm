"""前端结构与命名空间检查（不需要浏览器）。

Vue options API 的 data / computed / methods 共用一个实例命名空间，重名会让其中一个
静默失效——之前 bgDragOver 数据字段盖掉同名方法就是这个坑，所以这里盯住它。
"""
import pathlib
import re
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from app.character_gen import HIDDEN_FIELDS  # noqa: E402

js = (ROOT / "app/static/app.js").read_text(encoding="utf-8")
html = (ROOT / "app/static/index.html").read_text(encoding="utf-8")
css = (ROOT / "app/static/style.css").read_text(encoding="utf-8")

FAILED = []


def check(name, got, want):
    ok = got == want
    if not ok:
        FAILED.append(name)
    print(f"[{'ok' if ok else 'FAIL'}] {name}: {got!r}" + ("" if ok else f" != {want!r}"))


def block(start_pat):
    m = re.search(start_pat, js)
    if not m:
        sys.exit(f"找不到块：{start_pat}")
    i = js.index("{", m.end() - 1)
    depth, j = 0, i
    while j < len(js):
        if js[j] == "{":
            depth += 1
        elif js[j] == "}":
            depth -= 1
            if depth == 0:
                return js[i + 1:j]
        j += 1
    sys.exit("括号不配对")


def top_keys(text, indent):
    pad = " " * indent
    out = set()
    for line in text.splitlines():
        if not line.startswith(pad):
            continue
        rest = line[indent:]
        if rest[:1] in (" ", "\t") or not rest.strip():
            continue
        m = re.match(r'(?:async\s+)?([A-Za-z_$][\w$]*|"[^"]+")\s*[:(]', rest)
        if m:
            out.add(m.group(1).strip('"'))
    return out


data = top_keys(block(r"\n  data\(\)"), 6)
computed = top_keys(block(r"\n  computed:"), 4)
methods = top_keys(block(r"\n  methods:"), 4)
watch = top_keys(block(r"\n  watch:"), 4)
check("三组键名无重名", sorted((data & computed) | (data & methods) | (computed & methods)), [])
check("methods 数量合理（提取器没漏）", len(methods) > 80, True)
check("watch 有内容", len(watch) > 3, True)

# 模板里引用的方法与数据必须存在（写错名字 Vue 只会静默不生效/告警）
refs = set(re.findall(r'@click="([A-Za-z_$][\w$]*)\s*\(', html))
missing = sorted(refs - methods)
check("模板调用的方法都存在", missing, [])

# 探索模式：前端常量必须与后端一致，否则锁定的字段名对不上，界面会"漏"出来
check("前端锁定字段与后端 HIDDEN_FIELDS 一致",
      f'const LOCKED_FIELDS = {list(HIDDEN_FIELDS)!r};'.replace("'", '"') in js, True)

# 关键结构都在
check("弹窗有生成区", 'class="gen-box"' in html, True)
check("有开放/探索模式选择", ('value="open"' in html) and ('value="explore"' in html), True)
check("两处锁定占位（面板 + 弹窗）", html.count('class="locked-box"'), 2)
check("两个公开角色设定按钮", html.count(">公开角色设定</button>"), 2)
check("解锁有确认弹窗文案", "永久取消锁定" in js, True)
check("保存带 draft_id", "charPayload.draft_id = this.charModal.gen.draftId" in js, True)
check("保存失败在弹窗内提示", "charModal.saveError" in js and "charModal.saveError" in html, True)
check("样式含 gen-box / locked-box", (".gen-box" in css) and (".locked-box" in css), True)

# 发送键旁的"回到最新"键（10.28 顺带加的）
check("有 ↓ 键", 'class="jump-btn"' in html, True)
check("↓ 在发送行内", html.index('class="send-row"') < html.index('class="jump-btn"'), True)
check("有 jumpToBottom 方法", "jumpToBottom" in methods, True)

# 弹窗变体宽度必须压得住基础 .modal（10.28 的坑）
check("编辑弹窗宽度用复合选择器", ".modal.edit-modal { width: 780px; }" in css, True)
check("裁剪弹窗宽度用复合选择器", ".modal.crop-modal { width: 380px;" in css, True)
check("操作行按键不被压缩", ".edit-btns { display: flex; flex: none; gap: 8px; }" in css, True)

print()
if FAILED:
    print(f"失败 {len(FAILED)} 项：{FAILED}")
    sys.exit(1)
print("前端结构与命名用例全部通过")
