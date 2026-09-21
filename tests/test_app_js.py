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
# 判断"某条样式是否已清除"时要先去掉注释：注释里解释"这里原来有个 XXX"是正常的，
# 不该被当成样式还在（反过来也避免有人把规则注释掉却骗过检查）
css_code = re.sub(r"/\*.*?\*/", "", css, flags=re.S)

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


# ---- HTML 标签配对 ----
# 先剥掉注释：注释里可以出现 <mark> 这类字面标签（说明文字里就会写），
# 浏览器会忽略注释内容，解析器也必须照做，否则会数出多余的"开标签"
VOID_TAGS = {"input", "br", "img", "hr", "meta", "link", "source", "textarea"}
markup = re.sub(r"<!--.*?-->", "", html, flags=re.S)
stack, bad = [], []
for close, name, attrs, selfc in re.findall(r"<(/?)([a-zA-Z][\w-]*)([^>]*?)(/?)>", markup):
    n = name.lower()
    if n in VOID_TAGS or selfc:
        continue
    if close:
        if stack and stack[-1] == n:
            stack.pop()
        else:
            bad.append((n, stack[-3:]))
    else:
        stack.append(n)
check("HTML 标签配对", (stack[-5:], bad[:2]), ([], []))

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
check("标签按钮（模板里五个，自由情境少两个）", html.count('class="panel-tab"'), 5)
check("内容面板（模板里五个）", html.count("panel-tab-pane"), 5)
check("旧的折叠结构已清除",
      [w for w in ("panel-section", "panelFold", "togglePanelFold") if (w in html or w in js)], [])
check("CSS 里的折叠样式已清除", ".panel-section" in css_code, False)
check("未保存圆点样式在", ".tab-dot" in css, True)
check("当前标签的未保存状态有计算属性", "activeTabDirty" in js and "activeTabDirty" in html, True)
check("切到没有该标签的会话时有兜底", "fixPanelTab" in js, True)

# ---- 面板里不再有标题与关闭键；收起/展开只走顶栏那个"面板"按钮（10.45） ----
check("面板里没有标题行", 'class="panel-head"' not in html, True)
check("面板里没有'面板'二字", ">面板</h2>" not in html, True)
check("面板里没有关闭键", 'title="收起面板"' not in html, True)
check("面板标题的样式已清除", ".panel-head" in css_code, False)
check("顶栏的'面板'按钮仍是唯一开关",
      html.count("panelCollapsed = !panelCollapsed"), 1)
# 标签栏现在是面板最上面一行，它下面那条线就是"标签区 / 内容区"的分界，必须够清楚
check("标签栏分隔线加重", "border-bottom: 2px solid #d7dae1;" in css, True)
panel_tab_css = re.search(r"\.panel-tab \{[^}]*\}", css)
check("标签边框常驻（不再只给选中项画边）",
      bool(panel_tab_css) and "border: 1px solid var(--border);" in panel_tab_css.group(0)
      and "border: 1px solid transparent;" not in panel_tab_css.group(0), True)
on_tab_css = re.search(r"\.panel-tab\.on \{[^}]*\}", css)
check("选中标签用强调色边框区分",
      bool(on_tab_css) and "border-color: var(--accent);" in on_tab_css.group(0), True)

# ---- 字数上限与右下角实时提示 ----
counters = html.count('class="char-count')
check("计数提示数量（含我的设定三项、世界设定三项与词条两项）", counters, 26)
check("每个计数器都有 .counted 定位父层", html.count('class="counted') >= counters, True)
check("计数方法在", "isNear(value, max)" in js and "len(value)" in js, True)
# 所有自由文本输入都要有 maxlength（文件选择、单选、滑杆除外）；会话内搜索框是
# 界面过滤器、不落库，也不该占一个上限，所以单独放行
free_boxes = []
for tag, attrs in re.findall(r"<(input|textarea)([^>]*)>", html, flags=re.S):
    if tag == "input" and any(k in attrs for k in ('type="file"', 'type="radio"', 'type="range"')):
        continue
    if "search-input" in attrs:
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

# ---- 消息上方那一行：说话人 + 发送时间 ----
check("有名字与时间的那一行", 'class="msg-head"' in html, True)
check("时间只在消息行里出现一次（流式占位没有）", html.count('class="msg-time"'), 1)
check("时间在气泡之前（上方那一行）",
      html.index('class="msg-time"') < html.index('title="双击可编辑这条消息"'), True)
check("时间在 msg-head 行里", html.index('class="msg-head"') < html.index('class="msg-time"'), True)
check("名字与时间同一行", 'class="msg-head"' in html and 'class="msg-name"' in html, True)
check("时间样式在", ".msg-time {" in css, True)
check("user 侧那一行仍靠右（由 bubble-wrap 的 align-items 决定）",
      ".msg.user .bubble-wrap { align-items: flex-end; }" in css, True)
check("有时间格式化方法", "timeOf(m)" in js and "fullTimeOf(m)" in js, True)
check("时间取 created_at 的时分秒", 's.slice(11, 19)' in js, True)

# ---- 我的设定（用户资料） ----
check("有我的设定标签", ">我的设定<span" in html, True)
check("我的设定面板在", 'panelTab === \'profile\'' in html, True)
check("面板顶部的输出倾向已改名", "输出倾向" in html or "genSectionTitle" in js, False)
check("生成要求标签写死文案", '>生成要求<span' in html, True)
check("用户头像有第三个 target", "pickAvatar($event, 'profile')" in html, True)
check("头像归属有统一入口", "avatarForm(target)" in js, True)
check("我的设定有独立的脏标记与还原", "profileDirty" in js and 'section === "profile"' in js, True)
check("保存派发包含我的设定", 'if (this.panelTab === "profile") return this.saveProfile();' in js, True)
check("启动时加载我的设定", 'await this.api("/api/profile")' in js, True)

# ---- 世界设定（全局一份，三种模式都用得上） ----
check("有世界设定标签", ">世界设定<span" in html, True)
check("世界设定面板在", "panelTab === 'world'" in html, True)
check("世界设定标签不判模式（自由情境也显示）",
      "v-if" not in re.search(r"<button([^>]*)panelTab = 'world'", html).group(1), True)
check("世界设定有独立的脏标记与还原", "worldDirty" in js and 'section === "world"' in js, True)
check("保存派发包含世界设定", 'if (this.panelTab === "world") return this.saveWorld();' in js, True)
check("启动时加载世界设定", 'await this.api("/api/world")' in js, True)
check("词条可增可删", "addTerm()" in js and "removeTerm(index)" in js, True)
check("到上限后不能再加词条",
      ':disabled="worldForm.terms.length >= limits.world_terms_max"' in html, True)
check("名称注明不发给模型", "只用于自己辨认，不发给模型" in html, True)
check("词库说明写清空行会被丢弃", "名词留空的行在保存时自动丢弃" in html, True)
# 5 个标签在 330px 面板里等分只有约 56px，四字标签需要约 68px：必须能换行
tabs_css = re.search(r"\.panel-tabs \{[^}]*\}", css)
check("标签栏可换行", bool(tabs_css) and "flex-wrap: wrap;" in tabs_css.group(0), True)
check("标签栏仍不参与伸缩", bool(tabs_css) and "flex: none;" in tabs_css.group(0), True)
# 实测：基准 56px 时 5 个标签挤在一行、每格 56px，四个汉字要 56px 以上 → 被截成"生成要…"；
# 30% 时排成 3+2、每格 97px，不截断。改这个数字前请重新量一遍
tab_css = re.search(r"\.panel-tab \{[^}]*\}", css)
check("标签基准宽度能排下三个（30%）", bool(tab_css) and "flex: 1 1 30%;" in tab_css.group(0), True)
check("消息按模式取名字", "msgName(m)" in js and "msgName(m)" in html, True)
check("用户头像列有显示条件", "showUserSide" in js and "showUserSide" in html, True)
check("自由情境不显示用户头像列", "return !!this.activeChar && !!(this.profile.avatar || this.profile.name);" in js, True)
check("用户头像列排在气泡之后（渲染到右侧）",
      html.rindex('class="msg-side"') > html.index('class="bubble-wrap"'), True)
check("那一行排在气泡之前（显示在上方）",
      html.index('class="msg-head"') < html.index('title="双击可编辑这条消息"'), True)
# 两侧气泡到头像的间距要一致（user 那侧的头像是后加的，漏了 gap 就会紧贴）
check("两侧消息用同一份间距",
      ".msg.user,\n.msg.assistant { align-items: flex-start; gap: 12px; }" in css, True)
# user 侧与模型侧镜像：时间在名字左边
check("user 侧时间换到名字左边", ".msg.user .msg-head { flex-direction: row-reverse; }" in css, True)
# "已编辑"标记已移除（数据字段仍在，只是不再显示）
check("页面里没有「已编辑」标记", ("已编辑" in html) or ("edited-flag" in css), False)

# ---- 弹窗底部的操作行钉底 ----
check("两个弹窗各有字段滚动区", html.count('class="modal-body"'), 2)
check("弹窗外层保留滚动兜底", ".modal {" in css and "overflow-y: auto;" in css, True)
check("字段区是弹窗里唯一滚动区",
      ".modal-body {" in css and "flex: 1 1 auto;" in css and "min-height: 0;" in css, True)
check("角色弹窗的操作行在字段区之外",
      html.rindex('class="modal-actions"') > html.rindex('class="modal-body"'), True)
check("编辑弹窗的操作行在字段区之外",
      html.rindex('class="edit-actions"') > html.index('class="modal-body"'), True)
check("保存失败提示也在字段区之外（与按钮一起常驻）",
      html.index('charModal.saveError') > html.index('class="modal-body"'), True)

# ---- 会话内搜索 ----
check("顶栏有搜索框", 'class="search-box"' in html and 'class="search-input"' in html, True)
check("搜索框在工具栏里（面板按钮之前）",
      html.index('class="search-box"') < html.index('面板 ‹'), True)
check("搜索框只在有会话时出现", 'v-if="activeSession" class="search-box"' in html, True)
check("Enter / Shift+Enter / Esc 都接上了",
      ('@keydown.enter.exact.prevent="searchNext"' in html)
      and ('@keydown.shift.enter.prevent="searchPrev"' in html)
      and ('@keydown.esc="clearSearch"' in html), True)
check("有命中计数与上一个/下一个（清空走 Esc）",
      ('class="search-count"' in html) and ('@click="searchPrev"' in html)
      and ('@click="searchNext"' in html) and ('@keydown.esc="clearSearch"' in html), True)
check("命中处标黄且区分当前项",
      ("mark.search-hit {" in css) and ("mark.search-hit.current {" in css), True)
check("消息正文走分块渲染（便于标黄）", "partsOf(m)" in html and "partsOf(m)" in js, True)
check("搜索与渲染共用切块", "textParts(m)" in js and "this.textParts(m)" in js, True)
check("关键词按字面转义（元字符不当正则用）", "escapeRegExp(s)" in js, True)
check("只搜显示中的消息", "for (const m of this.displayMessages)" in js, True)
check("跳转是环形的", "((this.searchIndex + step) % total + total) % total" in js, True)
check("换关键词后回到第一处并滚动", "searchQuery() {" in js and "scrollToHit()" in js, True)
# 尺寸稳定：计数与按键始终占位（曾经按有无关键词显示/隐藏，输入前后整框会变宽变窄）
check("计数与按键不按关键词显隐", 'v-if="searchQuery"' in html, False)
check("搜索框里只有上一个/下一个两个键",
      len(re.findall(r'class="icon-btn"[^>]*@click="search(?:Prev|Next)"', html)), 2)
check("清空靠 Esc（不再多放一个清空键占宽度）", "清空搜索" in html, False)
check("搜索框与计数都不伸缩",
      ".search-box {\n  flex: none;" in css and "min-width: 42px;" in css, True)
# 按钮必须显式 opacity: 1——.icon-btn 默认是"悬停才显形"（给侧栏用的），
# 照搬过来会让按钮可点却看不见
check("搜索框按键可见", ".search-box .icon-btn {\n  flex: none;\n  opacity: 1;" in css, True)
check("搜索框在模型选择左边",
      html.index('class="search-box"') < html.index('class="model-select"'), True)
check("顶栏放不下时换行而不是溢出", "flex-wrap: wrap;" in css, True)

# ---- "面板"按钮上的小点不能改变按钮尺寸 ----
check("面板按钮可作定位父层", ".panel-toggle { position: relative; }" in css, True)
check("小点是绝对定位且不吃外边距",
      ".panel-toggle .dirty-dot {" in css and "position: absolute;" in css
      and "margin: 0;" in css, True)

# ---- 左侧栏的"模式选择" ----
check("左侧栏有模式选择标题", '<div class="side-label">模式选择</div>' in html, True)
check("标题在模式按钮之前",
      html.index('class="side-label"') < html.index('class="mode-tabs"'), True)
check("标题样式在", ".side-label {" in css, True)


def css_block(sel):
    m = re.search(re.escape(sel) + r"\s*\{([^}]*)\}", css)
    return m.group(1) if m else ""


def css_font_size(sel):
    m = re.search(r"font-size:\s*(\d+)px", css_block(sel))
    return int(m.group(1)) if m else 0


# 用户要求：标题居中加粗、字号调大，并在与模式按钮之间加一条分隔线
sl = css_block(".side-label")
check("标题居中", "text-align: center;" in sl, True)
check("标题加粗", "font-weight: 700;" in sl, True)
check("标题字号比模式按钮大", css_font_size(".side-label") > css_font_size(".mode-tab"), True)
check("标题底部有分隔线", "border-bottom: 1px solid var(--border);" in sl, True)

# ---- 面板底部常驻的保存区 ----
check("只有一个保存键且改名为「保存当前配置」", html.count(">保存当前配置</button>"), 1)
check("面板里旧的保存文案已清除",
      [w for w in ("保存生成要求", "保存记忆") if w in html], [])
check("保存区在滚动容器之外",
      html.index('class="panel-footer"') > html.index('class="panel-body"'), True)
check("保存区不参与伸缩", ".panel-footer {" in css and "flex: none;" in css, True)
check("未保存 / 还原移到了保存区",
      html.index('class="dirty-flag"') > html.index('class="panel-footer"'), True)
check("保存按当前标签派发",
      'if (this.panelTab === "char") return this.saveCharacterDrawer();' in js
      and "return this.saveMemory();" in js and "return this.saveGenSettings();" in js, True)
check("姓名为空时不能保存", "saveDisabled()" in js and ":disabled=\"saveDisabled\"" in html, True)
check("面板里不再有删除角色", html.count(">删除角色</button>"), 1)  # 只剩角色弹窗里那个
check("面板用的删除方法已删除", "async removeCharacter()" in js, False)
check("弹窗用的删除方法还在", "removeCharacterFromModal" in js, True)

# 生成区说明里要交代模型与思考开关（用户问过生成是否跟随它们）
check("生成区说明提到当前模型", "用当前选中的模型" in html, True)
check("生成区说明提到思考开关", "跟着顶栏的思考开关走" in html, True)

# 头像入口：面板与弹窗的按钮文案必须一致（曾经一个写"选择图片"、一个写"选择头像"）
picker = re.findall(r'class="ghost-btn file-btn">\{\{([^}]*)\}\}', html)
normalized = sorted(re.sub(r"(?:char(?:Modal\.form|Form)|profileForm)\.avatar", "AV", p).strip() for p in picker)
check("三处头像按钮都在（面板 / 弹窗 / 我的设定）", len(picker), 3)
check("三处头像按钮同文案（无头像=上传头像 / 有头像=更换头像）",
      normalized, ['AV ? "更换头像" : "上传头像"'] * 3)
check("没有遗留的旧文案", [w for w in ("选择头像", "选择图片") if w in html], [])

# ---- 我的设定的预设 ----
check("有预设下拉", 'class="preset-select"' in html and '@change="loadPreset"' in html, True)
check("下拉列出预设（名字 + 身份）",
      'v-for="p in profilePresets"' in html and "p.identity" in html, True)
check("有存为预设与删除预设", (">存为预设</button>" in html) and (">删除预设</button>" in html), True)
check("没有预设时给出提示", "还没有预设" in html, True)
check("预设方法齐全",
      all(k in js for k in ("async loadPresets()", "loadPreset() {", "async savePreset()",
                            "async removePreset()")), True)
# 载入预设只填表单、不直接落库（否则"选错了"就不可撤销），仍走底部保存
_load = js[js.index("loadPreset() {"):js.index("async savePreset()")]
check("载入预设不写库", "this.api(" in _load, False)
check("载入预设填的是这四项",
      all(f"{k}: p.{k}" in _load for k in ("name", "identity", "appearance", "avatar")), True)
check("启动时拉预设列表", "await this.loadPresets();" in js, True)
check("删除预设要确认", "删除预设「" in js, True)
check("预设样式在", ".preset-row {" in css and ".preset-select {" in css, True)

# ---- 没选模型时的提示 ----
check("启动时若没选模型会提示", "还没有选择模型，生成前请先在左边选一个" in js, True)
check("没选模型时思考开关置灰",
      "if (!this.currentModel) return false;" in js and "还没有选择模型，先在左边选一个" in js, True)

print()
if FAILED:
    print(f"失败 {len(FAILED)} 项：{FAILED}")
    sys.exit(1)
print("前端结构与命名用例全部通过")
