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
check("角色弹窗宽度用复合选择器并与编辑弹窗同宽",
      ".modal.char-modal { width: 780px; }" in css, True)
check("操作行按键不被压缩", ".edit-btns { display: flex; flex: none; gap: 8px; }" in css, True)

# 角色弹窗里的填写框默认高度（不能只靠 rows，样式里也要有下限）
check("角色弹窗文本框有最小高度", "min-height: 118px;" in css, True)
check("背景故事框更高", ".modal.char-modal .field textarea.grow-lg" in css, True)
check("背景故事框用了 grow-lg 类", 'class="grow-lg"' in html, True)
check("宽度规则不作用于右侧面板",
      ".modal.char-modal .field textarea {" in css and css.count(".modal.char-modal .field") >= 2, True)

# ---- 右侧面板改成标签页 ----
check("有标签栏", html.count('class="panel-tabs"'), 1)
check("三个标签按钮", html.count('class="panel-tab"'), 3)
check("三个内容面板", html.count("panel-tab-pane"), 3)
check("旧的折叠结构已清除",
      [w for w in ("panel-section", "panelFold", "togglePanelFold") if (w in html or w in js)], [])
check("CSS 里的折叠样式已清除", ".panel-section" in css, False)
check("未保存圆点样式在", ".tab-dot" in css, True)
check("当前标签的未保存状态有计算属性", "activeTabDirty" in js and "activeTabDirty" in html, True)
check("切到没有该标签的会话时有兜底", "fixPanelTab" in js, True)

# ---- 字数上限与右下角实时提示 ----
counters = html.count('class="char-count')
check("计数提示数量", counters, 18)
check("每个计数器都有 .counted 定位父层", html.count('class="counted') >= counters, True)
check("计数方法在", "isNear(value, max)" in js and "len(value)" in js, True)
# 所有自由文本输入都要有 maxlength（文件选择、单选、滑杆除外）
free_boxes = []
for tag, attrs in re.findall(r"<(input|textarea)([^>]*)>", html, flags=re.S):
    if tag == "input" and any(k in attrs for k in ('type="file"', 'type="radio"', 'type="range"')):
        continue
    if ":maxlength" not in attrs:
        free_boxes.append(attrs.strip().splitlines()[0][:60])
check("没有漏掉 maxlength 的文本输入", free_boxes, [])
check("上限从后端取", 'this.limits = await this.api("/api/limits")' in js, True)
# 前端兜底值与后端必须一致，否则接口拿不到时两边限制不同
from app.limits import LIMITS  # noqa: E402

for key, value in LIMITS.items():
    if f"{key}: {value}" not in js:
        free_boxes.append(f"{key}={value}")
check("前端兜底上限与后端一致", free_boxes, [])
# 单行框的提示要垂直居中（否则贴底边很挤），且注释说明了为什么
check("单行提示有 inline 变体", ".char-count.inline" in css and "char-count inline" in html, True)
check("接近上限时变色", ".char-count.near" in css, True)

# ---- 关闭背景（放在翻页键旁边） ----
check("背景条用 showBgBar", html.count("showBgBar"), 1)
check("有关闭背景键", 'class="bg-close"' in html, True)
check("关闭/显示两种文案", ("关闭背景" in html) and ("显示背景" in html), True)
check("关闭后背景条仍在（不依赖 chatBgUrl）",
      "!!this.activeChar && this.bgImages.length > 0" in js, True)
check("关掉背景时回落到空白", "|| this.bgHidden" in js, True)
check("切会话或角色时恢复显示", "this.bgHidden = false;" in js, True)
check("单张背景时翻页键置灰", ':disabled="bgImages.length < 2"' in html, True)
check("关闭键要压得住 .bg-switch button 的 28px",
      ".bg-switch button.bg-close {" in css, True)

# ---- 标签栏必须在滚动容器外面（否则内容一长就被滚轮带走） ----
check("标签栏排在滚动容器之前", html.index('class="panel-tabs"') < html.index('class="panel-body"'), True)
check("标签内容面板在滚动容器之内",
      html.index('class="panel-body"') < html.index("panel-tab-pane"), True)
check("标签栏与还原行都不参与伸缩", css.count(".panel-tabs {") == 1 and "flex: none;" in css, True)
check("滚动容器仍是 panel-body", "overflow-y: auto;" in css and ".panel-body {" in css, True)

# ---- 消息旁的发送时间 ----
check("气泡与时间在同一行", 'class="bubble-line"' in html, True)
check("时间只在消息行里出现一次（流式占位没有）", html.count('class="msg-time"'), 1)
check("时间在气泡行内", html.index('class="bubble-line"') < html.index('class="msg-time"'), True)
check("user 的时间换到气泡左侧", ".msg.user .bubble-line { flex-direction: row-reverse; }" in css, True)
check("时间样式在", ".msg-time {" in css, True)
check("有时间格式化方法", "timeOf(m)" in js and "fullTimeOf(m)" in js, True)
check("时间取 created_at 的时分秒", 's.slice(11, 19)' in js, True)

# 生成区说明里要交代模型与思考开关（用户问过生成是否跟随它们）
check("生成区说明提到当前模型", "用当前选中的模型" in html, True)
check("生成区说明提到思考开关", "跟着顶栏的思考开关走" in html, True)

# 头像入口：面板与弹窗的按钮文案必须一致（曾经一个写"选择图片"、一个写"选择头像"）
picker = re.findall(r'class="ghost-btn file-btn">\{\{([^}]*)\}\}', html)
normalized = sorted(re.sub(r"char(?:Modal\.form|Form)\.avatar", "AV", p).strip() for p in picker)
check("两处头像按钮都在", len(picker), 2)
check("两处头像按钮同文案（无头像=上传头像 / 有头像=更换头像）",
      normalized, ['AV ? "更换头像" : "上传头像"'] * 2)
check("没有遗留的旧文案", [w for w in ("选择头像", "选择图片") if w in html], [])

print()
if FAILED:
    print(f"失败 {len(FAILED)} 项：{FAILED}")
    sys.exit(1)
print("前端结构与命名用例全部通过")
