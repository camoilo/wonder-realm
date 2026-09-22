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

frontend = ROOT / "frontend"
# 拆成单文件组件后，源码分散在若干文件里；测试按下面两坨分别拼接：
#   html —— 入口 HTML + 所有 .vue（模板 + 脚本），模板类断言在它上面找
#   js   —— store.js + main.js + 各 .vue 的 script 块，逻辑类断言在它上面找
# 顺序固定为"骨架 → 左栏 → 顶栏 → 对话区 → 输入区 → 面板 → 弹窗"，
# 这样原来那些"A 在 B 之前"的顺序断言仍然成立。
# 组件文件自动发现：App.vue 必须排第一（骨架顺序断言要看它），其余按路径排序（结果稳定）。
# 这样以后继续拆组件（例如把面板里的标签页再拆出去）不用再回来改测试。
VUE_ORDER = ["App.vue"] + sorted(
    str(x.relative_to(frontend / "src")).replace("\\", "/")
    for x in (frontend / "src" / "components").rglob("*.vue")
)
vue_sources = [(frontend / "src" / rel).read_text(encoding="utf-8") for rel in VUE_ORDER]
# store 现在拆成 barrel（src/store.js）+ 领域模块（src/store/*.js）：断言要在整份源码上看，
# 所以拼成一坨（顺序稳定：先 barrel，再按文件名排序的模块）
store_files = [frontend / "src/store.js"] + sorted((frontend / "src/store").glob("*.js"))
store_js = "\\n".join(f.read_text(encoding="utf-8") for f in store_files)
main_js = (frontend / "src/main.js").read_text(encoding="utf-8")
vite_cfg = (frontend / "vite.config.js").read_text(encoding="utf-8")
css = (frontend / "src/style.css").read_text(encoding="utf-8")
html = (frontend / "index.html").read_text(encoding="utf-8") + "\n" + "\n".join(vue_sources)
script_blocks = [re.search(r"<script setup>(.*?)</script>", v, re.S).group(1)
                 for v in vue_sources if "<script setup>" in v]
js = store_js + "\n" + main_js + "\n" + "\n".join(script_blocks)
# store.js 是把选项对象的 this. 机械换成 store. 得来的；下面这行把视图换回 this.，
# 于是针对选项对象写的断言（this.panelTab / this.api(...) 之类）不用改。
# 排除前面带 / 的情况，免得把 "../store.js" 这种路径也改坏。
js = re.sub(r"(?<![\w/])store\.", "this.", js)
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


# ---- 构建方式：Vue 3 + Vite（不再走 CDN） ----
check("index.html 不再引用 CDN", "cdn.jsdelivr" in html, False)
check("入口改成 ES 模块", '<script type="module" src="/src/main.js"></script>' in html, True)
check("样式改由入口 import（HTML 里不再有 link）", 'rel="stylesheet"' in html, False)
check("app.js 不在顶层创建应用", "Vue.createApp" in js, False)
check("store 导出 reactive 状态", "export const store = reactive({" in js, True)
check("store 里没有残留的 this.", "this." in store_js, False)
check("入口挂载根组件",
      'import App from "./App.vue";' in main_js
      and 'createApp(App)' in main_js and '.mount("#app")' in main_js, True)
check("入口引入样式", 'import "./style.css";' in main_js, True)
check("Vite 把产物写进后端静态目录", '"../app/static"' in vite_cfg, True)
# 产物守卫：改了源码忘了构建、或产物被删，都在这里拦下（产物是提交进仓库的）
built_html = (ROOT / "app/static/index.html").read_text(encoding="utf-8")
assets = re.findall(r'(?:src|href)="(/assets/[^"]+)"', built_html)
check("构建产物被引用（一个 js + 一个 css）", len(assets), 2)
check("引用的产物文件都在",
      all((ROOT / "app/static" / a.lstrip("/")).is_file() for a in assets), True)
check("构建产物里没有 CDN 残留", "cdn.jsdelivr" in built_html, False)


# 方法名从**当前源码**里现取，不用冻结的快照：
# 快照漏掉后加的方法，模板里一写成 @click="foo(x)" 就会误报"方法不存在"。
# 只认"名字(参数) {" 这种定义形态，避免把 if ( / return ( 之类的行也算进来。
_store_methods = "\n".join(f.read_text(encoding="utf-8") for f in store_files)


# ---- 拆组件后的守卫：模板里用到的 store 成员必须在该文件声明过 ----
# 漏声明时 Vue 只在开发构建里 warning，生产构建下就是"看起来正常但点了没反应"，很难查。
STORE_KEYS = (
    set(re.findall(r"^      ([A-Za-z_$][\w$]*)[,:]", store_js, re.M))          # data 字段
    | set(re.findall(r"^store\.([A-Za-z_$][\w$]*) = computed", store_js, re.M))  # 计算属性
    | set(re.findall(r"^  (?:async )?([A-Za-z_$][\w$]*)\([^)]*\) \{", _store_methods, re.M))  # 方法
)
_SKIP = {
    "true", "false", "null", "undefined", "typeof", "instanceof", "in", "of", "new",
    "Math", "JSON", "Object", "Array", "String", "Number", "Boolean", "Date", "RegExp",
    "Error", "Promise", "Map", "Set", "Number", "parseInt", "parseFloat", "isNaN",
    "window", "document", "console", "setTimeout", "clearTimeout", "$event",
    # 注意：MODES 这类"从 store.js 具名导入的模块级常量"**不放进白名单** ——
    # 放进来等于"组件用了却不导入也算过"，而它同样是漏导入就会 ReferenceError 的名字。
    # 组件自己 import 了，就会出现在下面 _declared 里，不会误报。
}


def _ids(text: str) -> set:
    """把模板表达式里的标识符抠出来（去掉字符串字面量，且不取属性访问的后半截）。"""
    text = re.sub(r"'(?:[^'\\]|\\.)*'", "''", text)
    text = re.sub(r'"(?:[^"\\]|\\.)*"', '""', text)
    text = re.sub(r"`(?:[^`\\]|\\.)*`", "``", text)
    return {m.group(1) for m in re.finditer(r"(?<![\w$.])([A-Za-z_][\w$]*)", text)}


for _rel, _src in zip(VUE_ORDER, vue_sources):
    _tpl = re.search(r"<template>(.*?)</template>", _src, re.S).group(1)
    _script = re.search(r"<script setup>(.*?)</script>", _src, re.S).group(1)
    _locals = set(re.findall(r'v-for="\(?([^")]*)\)?\s+in\s', _tpl))
    _locals = {x.strip().strip("{}").split(":")[-1].strip() for part in _locals for x in part.split(",")}
    if "defineProps" in _script:
        _locals |= set(re.findall(r"defineProps\(\{\s*([\w$]+):", _script))
    _declared = set(re.findall(r"^  ([A-Za-z_$][\w$]*),$", _script, re.M))
    for _chunk in re.findall(r"import \{([^}]*)\}", _script):
        _declared |= {x.strip() for x in _chunk.split(",") if x.strip()}
    _exprs = list(re.findall(r"\{\{(.*?)\}\}", _tpl, re.S))
    _exprs += re.findall(r'(?:\s(?:v-[a-z-]+|[:@][\w.-]+))="([^"]*)"', _tpl, re.S)
    _used = set()
    for _e in _exprs:
        _used |= _ids(_e)
    _missing = sorted(_used & STORE_KEYS - _declared - _locals - _SKIP)
    check(f"{_rel} 模板用到的 store 成员都已声明", _missing, [])


# ---- 消息列表只能在一处遍历（DEVELOPMENT §9.7 前端工程约定） ----
# MessageItem 是"一条消息"的组件（ChatArea 里 `v-for … :m="m"` 传进去）。它的模板里
# 如果还留着外层 v-for="m in displayMessages"，就变成 n 个组件 × 每个渲染 n 条 = n² 条
# 气泡——两条消息看着"双倍"，四条就是"8 组"。这类结构错误静态检查一点都看不见：prop
# 传了、绑定也都声明齐了，模板标识符守卫照样全绿。所以专门钉住"谁负责遍历这个列表"。
_LIST_LOOPS = [rel for rel, src in zip(VUE_ORDER, vue_sources)
               if re.search(r'v-for="[^"]*\bin\s+displayMessages\b', src)]
check("消息列表只由一个组件遍历", _LIST_LOOPS, ["components/ChatArea.vue"])
# 收单条消息的组件（定义了 m 这个 prop）不许再自己遍历整份列表
_ITEM_LOOPS = [rel for rel, src in zip(VUE_ORDER, vue_sources)
               if "defineProps" in src and re.search(r'v-for="[^"]*\bin\s+displayMessages\b', src)]
check("只收一条消息的组件不再遍历列表", _ITEM_LOOPS, [])
# 而且它必须真的用 prop（模板里读 m.xxx），否则分组渲染就成了空壳
_MI = dict(zip(VUE_ORDER, vue_sources))["components/MessageItem.vue"]
check("MessageItem 渲染的是传进来的那条消息",
      bool(re.search(r"\{\{\s*m\.|\bm\.role\b", _MI)), True)


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

# store.js 里的三组名字：状态（reactive 的键）/ 计算属性（store.X = computed）/ 方法
# （Object.assign(store, {...}) 里的条目）。合并到一个 reactive 对象后，重名会**静默覆盖**，
# 比选项对象时代更隐蔽，所以要在这里盯住。
data = set(re.findall(r"^      ([A-Za-z_$][\w$]*)[,:]", store_js, re.M))
computed = set(re.findall(r"^store\.([A-Za-z_$][\w$]*) = computed", store_js, re.M))
methods = set(re.findall(r"^  (?:async )?([A-Za-z_$][\w$]*)\([^)]*\) \{", _store_methods, re.M))
_watch_src = re.search(r"const watchDefs = \{(.*?)\n\};", store_js, re.S).group(1)
watch = set(re.findall(r'^    "?([A-Za-z_$][\w$."]*)"?\(', _watch_src, re.M))
check("三组键名无重名", sorted((data & computed) | (data & methods) | (computed & methods)), [])
check("methods 数量合理（提取器没漏）", len(methods) > 60, True)
check("状态字段数量合理", len(data) > 50, True)
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

# 发送键旁的"回到最新"键（DEVELOPMENT §9.6 界面约定 顺带加的）
check("有 ↓ 键", 'class="jump-btn"' in html, True)
check("↓ 在发送行内", html.index('class="send-row"') < html.index('class="jump-btn"'), True)
check("有 jumpToBottom 方法", "jumpToBottom" in methods, True)

# 弹窗变体宽度必须压得住基础 .modal（DEVELOPMENT §9.6 界面约定 的坑）
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
check("标签按钮（模板里五个，导演模式少两个）", html.count('class="panel-tab"'), 5)
check("内容面板（模板里五个）", html.count("panel-tab-pane"), 5)
check("旧的折叠结构已清除",
      [w for w in ("panel-section", "panelFold", "togglePanelFold") if (w in html or w in js)], [])
check("CSS 里的折叠样式已清除", ".panel-section" in css_code, False)
check("未保存圆点样式在", ".tab-dot" in css, True)
check("当前标签的未保存状态有计算属性", "activeTabDirty" in js and "activeTabDirty" in html, True)
# ---- "配置"开关：常驻 + 改名 + 位置固定（面板开合都不动）（DEVELOPMENT §9.6 界面约定） ----
check("面板里没有标题行（开关不搬进面板）", 'class="panel-head"' not in html, True)
check("面板里没有第二个开关", 'class="panel-title"' not in html, True)
check("顶栏那一份没有 v-if（常驻，不随会话/面板出现消失）",
      re.search(r'<button v-if="[^"]*" class="ghost-btn panel-toggle"', html), None)
check("无会话时禁用", ':disabled="!activeSession"' in html, True)
check("禁用样式有定义（否则看起来仍可点）", ".ghost-btn:disabled {" in css, True)
check("开关在顶栏里（位置固定在工具栏最右）",
      html.index('class="toolbar"') < html.index("panel-toggle") < html.index("</header>"), True)
# 顶栏必须横跨"对话区 + 面板"：面板是 .main 的兄弟列时，面板一开顶栏就窄 330px，
# 按钮会左移并落到面板标签上（DEVELOPMENT §9.6 界面约定 第二版的真实事故）。这条断言把结构钉住
_app_tpl = re.search(r"<template>(.*?)</template>", vue_sources[0], re.S).group(1)
check("App 骨架里 TopBar 在 .work 之前（宽度不受面板影响）",
      _app_tpl.index("<TopBar />") < _app_tpl.index('class="work"'), True)
check("TopBar 组件的根节点是 header.topbar",
      '<header class="topbar"' in vue_sources[VUE_ORDER.index("components/TopBar.vue")], True)
check("对话区与面板在同一行里并排（对话区在 .work-main 内）",
      html.index('class="work"') < html.index('class="work-main"') < html.index('class="chat-area"')
      and html.index('class="chat-area"') < html.index('class="panel"'), True)
check("这两层容器的样式都在", ".work {" in css and ".work-main {" in css, True)
# 文案只换箭头、字数不变，所以按钮宽度不随状态变化（"不挪鼠标点开、看一眼、再点关"）
check("文案按状态只换箭头",
      'activeSession && !panelCollapsed ? "配置 ‹" : "配置 ›"' in html, True)
check("旧文案'面板'已清除",
      any(w in html for w in ("面板 ‹", "面板 ›", ">面板</h2>", "收起面板")), False)
check("标题提示随状态变化",
      "(panelCollapsed ? '展开配置面板' : '收起配置面板')" in html, True)

# ---- 分隔线：左右两侧同一条（DEVELOPMENT §9.6 界面约定） ----
check("分隔线定义成变量", "--divider: 2px solid #d7dae1;" in css, True)
check("三处分区线都用它（面板标签栏 / 左侧标题 / 左侧模式按钮）",
      css.count("border-bottom: var(--divider);"), 3)
check("标签边框常驻（不再只给选中项画边）",
      bool(re.search(r"\.panel-tab \{[^}]*\}", css))
      and "border: 1px solid var(--border);" in re.search(r"\.panel-tab \{[^}]*\}", css).group(0)
      and "border: 1px solid transparent;" not in re.search(r"\.panel-tab \{[^}]*\}", css).group(0),
      True)
on_tab_css = re.search(r"\.panel-tab\.on \{[^}]*\}", css)
check("选中标签用强调色边框区分",
      bool(on_tab_css) and "border-color: var(--accent);" in on_tab_css.group(0), True)

# ---- 字数上限与右下角实时提示 ----
counters = html.count('class="char-count')
check("计数提示数量（含底部输入区两栏、我的设定三项、预设弹窗三项、世界设定三项与词条两项）",
      counters, 30)
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
check("背景条用 showBgBar",
      html.count('v-if="showBgBar"'), 1)
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
      html.index('class="msg-time"') < html.index('class="msg-actions"'), True)
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
check("世界设定标签不判模式（导演模式也显示）",
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
check("导演模式不显示用户头像列", "return !!this.activeChar && !!(this.profile.avatar || this.profile.name);" in js, True)
check("用户头像列排在气泡之后（渲染到右侧）",
      html.rindex('class="msg-side"') > html.index('class="bubble-wrap"'), True)
check("那一行排在气泡之前（显示在上方）",
      html.index('class="msg-head"') < html.index('class="bubble"'), True)
# 两侧气泡到头像的间距要一致（user 那侧的头像是后加的，漏了 gap 就会紧贴）
check("两侧消息用同一份间距",
      ".msg.user,\n.msg.assistant { align-items: flex-start; gap: 12px; }" in css, True)
# user 侧与模型侧镜像：时间在名字左边
check("user 侧时间换到名字左边", ".msg.user .msg-head { flex-direction: row-reverse; }" in css, True)
# "已编辑"标记不渲染（数据字段仍在，只是不显示）
check("页面里没有「已编辑」标记", ("已编辑" in html) or ("edited-flag" in css), False)

# ---- 弹窗底部的操作行钉底 ----
check("每个滚动型弹窗都有字段滚动区（角色 / 编辑消息 / 预设）", html.count('class="modal-body"'), 3)
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
check("搜索框在工具栏里（配置开关之前）",
      html.index('class="search-box"') < html.index("panel-toggle"), True)
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


def css_rule(sel):
    """选择器**完全等于** sel 的那条规则。

    css_block 是"按前缀找"，遇到共用规则（`.mode-tip, .hint-tip { … }`）会先撞上它，
    所以这种场景要按整条选择器精确匹配。
    """
    for _s, _b in re.findall(r"([^{}]+)\{([^{}]*)\}", css_code):
        if _s.strip() == sel:
            return _b
    return ""


def css_font_size(sel):
    m = re.search(r"font-size:\s*(\d+)px", css_block(sel))
    return int(m.group(1)) if m else 0


# 用户要求：标题居中加粗、字号调大，并在与模式按钮之间加一条分隔线
sl = css_block(".side-label")
check("标题居中", "text-align: center;" in sl, True)
check("标题加粗", "font-weight: 700;" in sl, True)
check("标题字号比模式按钮大", css_font_size(".side-label") > css_font_size(".mode-tab"), True)
check("标题底部有分隔线（与右侧面板同一条）", "border-bottom: var(--divider);" in sl, True)

# ---- 模式按钮的介绍浮层（鼠标移上去/键盘聚焦时显示这个模式是干什么的） ----
_helpers_src = (frontend / "src/store/helpers.js").read_text(encoding="utf-8")
_modes_src = _helpers_src[_helpers_src.index("export const MODES"):]
_modes_src = _modes_src[:_modes_src.index("\n};")]
check("三种模式的介绍都写在 MODES 里（单一数据源）",
      [m for m in ("chat", "immersive", "director")
       if not re.search(rf"{m}: \{{[^}}]*hint:", _modes_src, re.S)], [])
_side_src = dict(zip(VUE_ORDER, vue_sources))["components/SideBar.vue"]
check("侧栏渲染介绍浮层", 'class="mode-tip"' in _side_src and "MODES[hoveredMode].hint" in _side_src, True)
check("鼠标移入与键盘聚焦都显示",
      all(k in _side_src for k in ('@mouseenter="hoveredMode = key"', "@mouseleave=\"hoveredMode = ''\"",
                                   '@focus="hoveredMode = key"', "@blur=\"hoveredMode = ''\"")), True)
_tip = css_block(".mode-tip")
# 两种浮层共用一条规则（.mode-tip, .hint-tip { ... }），css_block 会先撞上它，
# 所以这里单独取：共用块 + .hint-tip 自己的定位块
_shared_m = re.search(r"\.mode-tip,\s*\.hint-tip\s*\{([^}]*)\}", css)
_shared_tip = _shared_m.group(1) if _shared_m else ""
_hint_css = css_rule(".hint-tip")
check("介绍浮层绝对定位（不改变布局）", "position: absolute;" in _tip, True)
check("介绍浮层不吃鼠标（否则自己把自己关掉）", "pointer-events: none;" in _shared_tip, True)
check("浮层的父层可作定位参照", "position: relative;" in css_block(".mode-tabs"), True)

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
check("姓名为空时不能保存",
      "store.saveDisabled = computed(" in store_js
      and ':disabled="saveDisabled"' in html, True)
check("面板里不再有删除角色", html.count(">删除角色</button>"), 1)  # 只剩角色弹窗里那个
check("面板用的删除方法已删除", "async removeCharacter()" in js, False)
check("弹窗用的删除方法还在", "removeCharacterFromModal" in js, True)

# 生成区说明里要交代模型与思考开关（用户问过生成是否跟随它们）
check("生成区说明提到当前模型", "用当前选中的模型" in html, True)
check("生成区说明提到思考开关", "跟着顶栏的思考开关走" in html, True)

# 头像入口：面板与弹窗的按钮文案必须一致（曾经一个写"选择图片"、一个写"选择头像"）
picker = re.findall(r'class="ghost-btn file-btn">\{\{([^}]*)\}\}', html)
normalized = sorted(re.sub(
    r"(?:char(?:Modal\.form|Form)|profileForm|presetModal\.form)\.avatar", "AV", p).strip()
    for p in picker)
check("四处头像入口都在（角色面板 / 角色弹窗 / 我的设定 / 预设弹窗）", len(picker), 4)
check("四处头像按钮同文案（无头像=上传头像 / 有头像=更换头像）",
      normalized, ['AV ? "更换头像" : "上传头像"'] * 4)
check("没有遗留的旧文案", [w for w in ("选择头像", "选择图片") if w in html], [])

# ---- 我的设定的预设 ----
# 面板只显示"当前预设是谁"，挑选/看详情/编辑/删除都在弹窗里：预设名字可能重复，
# 下拉里一行字分不清，弹窗里能看到头像与身份、外观。
check("面板只显示当前预设名",
      'class="preset-current">当前预设：<b>{{ currentPresetLabel }}</b>' in html, True)
check("三个入口键（存为预设 / 载入预设… / 编辑预设…）",
      all(f">{t}</button>" in html for t in ("存为预设", "载入预设…", "编辑预设…")), True)
check("面板上不放删除（不可逆操作收进弹窗）", ">删除预设</button>" in html, False)
check("载入弹窗有列表与详情",
      'class="preset-list"' in html and 'class="preset-detail"' in html
      and ">载入这条</button>" in html and "p.identity" in html, True)
check("删除在编辑预设弹窗里", ">删除这条预设</button>" in html, True)
check("列表与详情都列出预设（名字 + 身份）",
      'v-for="p in profilePresets"' in html, True)
check("没有预设时给出提示", "还没有预设" in html, True)
check("预设方法齐全",
      all(k in js for k in ("async loadPresets()", "openLoadModal() {", "closeLoadModal() {",
                            "pickLoadPreset(id) {", "async confirmLoadPreset() {",
                            "async savePreset()", "openPresetModal() {", "editPickPreset(id) {",
                            "async savePresetModal() {", "async deletePresetInModal() {")), True)
# 载入 = 立即生效（写当前使用的设定），所以要带一次"覆盖"确认；删除也要确认
_confirm = js[js.index("async confirmLoadPreset() {"):js.index("async savePreset()")]
check("载入前对未保存改动要确认", "await this.ask(" in _confirm, True)
check("载入写的是当前配置", 'this.api("/api/profile", this.jsonOpts("PUT", values))' in _confirm, True)
check("载入后记住当前预设", "this.currentPresetId = p.id" in _confirm, True)
check("当前预设名带“已修改”判定",
      "currentPresetLabel = computed" in js and "（已修改）" in js, True)
check("启动时拉预设列表", "await this.loadPresets();" in js, True)
check("删除预设要确认", "删除预设「" in js, True)
check("预设样式在", ".preset-row {" in css and ".preset-current {" in css
      and ".preset-item {" in css and ".preset-detail {" in css, True)

# ---- 没选模型时的提示 ----
check("启动时若没选模型会提示", "还没有选择模型，生成前请先在左边选一个" in js, True)
check("没选模型时思考开关置灰",
      "if (!this.currentModel) return false;" in js and "还没有选择模型，先在左边选一个" in js, True)

# ---- 拆 store 后的守卫：模块里用到的"模块级名字"必须导入或就地声明（DEVELOPMENT §9.7 前端工程约定） ----
# 星形依赖的代价是每个模块都得自己 import 用到的 helper。漏一个，打包器不会吭声
# （ESM 是静态的，缺的标识符只在真的执行到那一行才 ReferenceError），于是
# "点开角色弹窗就崩"这种问题只能靠人拿浏览器点出来。这里把它变成静态检查。
_LIT = re.compile(
    r'"(?:\\.|[^"\\])*"' r"|'(?:\\.|[^'\\])*'" r"|`(?:\\.|[^`\\])*`"
    r"|//[^\n]*" r"|/\*.*?\*/", re.S)
_VUE_APIS = ("computed", "watch", "watchEffect", "nextTick", "reactive", "ref", "toRefs",
             "onMounted", "onBeforeUnmount", "shallowRef")


def _declared_names(src: str) -> set:
    """顶层声明（含 export）与顶层解构出来的名字。"""
    out = set(re.findall(
        r"^(?:export\s+)?(?:const|let|var|function|async\s+function|class)\s+([A-Za-z_$][\w$]*)",
        src, re.M))
    for _m in re.finditer(r"^(?:export\s+)?(?:const|let|var)\s*\{([^}]*)\}", src, re.M):
        for _part in _m.group(1).split(","):
            _n = _part.split(":")[-1].strip().split("=")[0].strip()
            if re.fullmatch(r"[A-Za-z_$][\w$]*", _n):
                out.add(_n)
    return out


def _local_names(src: str) -> set:
    """模块里本地可用的名字：import 进来的（含 as 重命名）+ 顶层声明的。"""
    out = _declared_names(src)
    for _re_m in re.finditer(r"^export\s*\{([^}]*)\}\s*from\s*[\"'][^\"']+[\"'];", src, re.M):
        for _p in _re_m.group(1).split(","):  # barrel 的转发导出
            _n = _p.split(" as ")[-1].strip()
            if re.fullmatch(r"[A-Za-z_$][\w$]*", _n):
                out.add(_n)
    for _im in re.finditer(r"^import\s+(.+?)\s+from\s+[\"'][^\"']+[\"'];", src, re.M):
        _clause = _im.group(1)
        _dm = re.match(r"([A-Za-z_$][\w$]*)", _clause)
        if _dm:
            out.add(_dm.group(1))
        _br = re.search(r"\{([^}]*)\}", _clause, re.S)
        if _br:
            for _p in _br.group(1).split(","):
                _n = _p.strip().split(" as ")[-1].strip()
                if re.fullmatch(r"[A-Za-z_$][\w$]*", _n):
                    out.add(_n)
    return out


def _uses(code: str, name: str) -> bool:
    # 先把展开/剩余运算符 ...x 抹平：否则 "..." 会被误当成属性访问而漏判
    # （第一版生成器就是这样漏掉 ...emptyCharModal() 的）
    return re.search(r"(?<![\w$.])" + re.escape(name) + r"(?![\w$])",
                     code.replace("...", " ")) is not None


# 待查的"外部名字"= 所有 store 模块顶层声明的名字（helpers 的常量/纯函数、state 里的
# 私有量与导出……凡是在别处顶层声明过的都算）+ 会用到的 vue 具名导出。
# 注意别只取 helpers.js 的导出：chat.js 用了 state.js 的 chatBoxEl、character.js 用了
# helpers 的 emptyCharModal，两次都漏在同一类地方。
_MOD_NAMES = set()
for _f in store_files:
    _MOD_NAMES |= _declared_names(_f.read_text(encoding="utf-8"))
for _f in store_files:
    _rel = str(_f.relative_to(frontend / "src")).replace("\\", "/")
    if _f.name == "helpers.js":
        continue
    _raw = _f.read_text(encoding="utf-8")
    _code = _LIT.sub(" ", _raw)
    _have = _local_names(_raw)
    _miss = [n for n in sorted(_MOD_NAMES) + list(_VUE_APIS) if _uses(_code, n) and n not in _have]
    check(f"{_rel} 用到的模块级名字都有来源", _miss, [])
    _dead = [n for n in sorted(_local_names(_raw) - _declared_names(_raw)) if not _uses(_code, n)]
    check(f"{_rel} 没有导入了却没用到的名字", _dead, [])

# ---- 弹窗怎么关：只有"按下"就落在遮罩上，才算点了窗口外（11 处回归） ----# 用 @click.self 的坑：click 的目标是 mousedown 与 mouseup 的**共同祖先**。在弹窗里按住
# 鼠标选文字、拖到遮罩上（或拖出窗口）再松开时，click 会落到遮罩上，于是"点窗口外关闭"
# 被误触发——用户选个文字窗口就没了。判据必须是"按下"的位置。
check("弹窗不再用 @click.self 关闭", [rel for rel, src in zip(VUE_ORDER, vue_sources)
      if "modal-mask" in src and "@click.self" in src], [])
_mask_modals = [rel for rel, src in zip(VUE_ORDER, vue_sources) if "modal-mask" in src]
check("七个弹窗都在", len(_mask_modals), 7)
check("每个弹窗走同一套关闭判定", [rel for rel, src in zip(VUE_ORDER, vue_sources)
      if "modal-mask" in src and not all(k in src for k in (
          "useMaskClose(", '@mousedown="onMaskDown"', '@mouseup="onMaskUp"', '@click="onMaskClick"'))], [])

# ---- 沉浸模式的输入区是两栏：情境（可选）+ 话语（必选） ----
# "话语必填、情境可空"这件事靠"发送键还是绑 store.input"来保证：只填情境时发送键必须是禁用的，
# 所以这里同时钉住两件事——两栏各自绑对字段、发送键不允许换成看情境。
_input_bar = dict(zip(VUE_ORDER, vue_sources))["components/InputBar.vue"]
check("情境栏绑 inputScenario", 'v-model="inputScenario"' in _input_bar, True)
check("话语栏仍绑 input", 'v-model="input"' in _input_bar, True)
check("情境栏只在沉浸模式出现", 'v-if="isImmersiveMode" class="input-field scenario-field"' in _input_bar, True)
check("两栏各有自己的上限（情境 scenario / 话语 message）",
      ":maxlength=\"limits.scenario\"" in _input_bar and ":maxlength=\"limits.message\"" in _input_bar, True)
check("话语必填：发送键仍看 input",
      ':disabled="!input.trim() || orphanActive"' in _input_bar, True)
check("两栏都支持 Enter 发送", _input_bar.count('@keydown.enter.exact.prevent="send"') == 2, True)
check("store 里有 inputScenario", "inputScenario: \"\"" in store_js, True)
# 注意：js 这一坨把 store. 换成了 this.（为了让老的选项对象断言能复用），所以这里不写前缀
check("沉浸模式的模式判定在", "isImmersiveMode = computed" in js, True)
check("发送时把情境一起带上（SSE 请求体）", "{ message: text, scenario: scenario || null }" in js, True)
check("乐观插入的 user 消息带情境", 'role: "user", content: text, scenario: scenario || null' in js, True)
check("失败重试也恢复情境", "inputScenario = scenario" in js, True)
_ib_css = css_block(".input-field")
check("两栏用标签区分（两个并排的框没标签会分不清）",
      ".input-field-label {" in css and ".input-field.scenario-field { flex: 0 0 36%; }" in css
      and "flex-direction: column;" in _ib_css, True)

# ---- 悬停提示统一走 v-hint（不用原生 title） ----
# 原生 title 延迟约一秒、样式跟浏览器走、不能换行；统一用自研浮层（composables/hint.js +
# App.vue 里的单例 .hint-tip），视觉与模式介绍浮层共用一套 CSS。
_all_vue = "\n".join(vue_sources)
check("组件里不再有原生 title",
      [rel for rel, src in zip(VUE_ORDER, vue_sources) if re.search(r'(?<![\w-])title\s*=', src)], [])
check("悬停提示都用 v-hint", len(re.findall(r'v-hint="', _all_vue)) >= 30, True)
check("指令在入口注册", 'directive("hint", hintDirective)' in main_js, True)
check("浮层挂在根组件", 'class="hint-tip"' in _all_vue and "hintText" in _all_vue, True)
check("指令模块在", (frontend / "src/composables/hint.js").exists(), True)
# 两种浮层共用一套视觉；.hint-tip 是 fixed 定位、不吃鼠标、层级高于弹窗遮罩（1200）
check("两种浮层共用一套样式",
      "pointer-events: none;" in _shared_tip and "background: #2f3441;" in _shared_tip, True)
check("v-hint 浮层定位与层级",
      "position: fixed;" in _hint_css and "z-index: 1300;" in _hint_css, True)
check("浮层层级高于弹窗遮罩", "z-index: 1200" in css and "z-index: 1300;" in _hint_css, True)
# 纯图标按钮（可见内容是个符号）去掉 title 后必须能读出来
check("图标按钮都有 aria-label", [rel for rel, src in zip(VUE_ORDER, vue_sources)
      for _l in src.splitlines()
      if "v-hint=" in _l and re.search(r">\s*(✎|✕|‹|›|×|↑|↓|☰)\s*<", _l) and "aria-label" not in _l], [])

# ---- 双击编辑已去掉；自带文字的按钮不加悬停提示 ----
# 双击是"看不见的入口"（用户得先知道有这回事），与旁边的「编辑」按钮重复；
# 而「复制 / 编辑 / 删除 / 重新生成」四个键自己就写着字，再弹一张卡片纯属噪音。
_mi = dict(zip(VUE_ORDER, vue_sources))["components/MessageItem.vue"]
check("气泡不再双击进编辑", "@dblclick" in _mi, False)
check("气泡上没有悬停提示", 'class="bubble"' in _mi and 'class="bubble" v-hint' in _mi, False)
_actions_from = _mi.index('class="msg-actions"')
_actions = _mi[_actions_from:_mi.index("</div>", _actions_from)]
check("操作条按钮（自带文字）不加提示", "v-hint" in _actions, False)

# ---- 预设与当前配置分开：选下拉不碰表单，载入/保存在两个按钮上 ----
# 之前的做法是"选中即把预设填进表单"，于是切换预设就会把表单改脏、点还原又和下拉里
# 选中的那条对不上。现在下拉只是"操作对象"，表单（当前配置）只被「载入」改变。
_pp = dict(zip(VUE_ORDER, vue_sources))["components/panes/ProfilePane.vue"]
check("下拉占位是名词（不再有“从预设载入”）",
      '<option value="">选择预设…</option>' in _pp and "从预设载入" in _pp, False)
check("选下拉不再自动载入表单",
      'v-model="presetPick" @change="loadPreset"' in _pp, False)
check("载入入口打开弹窗（不再就地载入）",
      '@click="openLoadModal"' in _pp and "loadPreset() {" in _pp, False)
check("预设的编辑走独立弹窗",
      '@click="openPresetModal"' in _pp and (frontend / "src/components/modals/PresetModal.vue").exists(), True)
check("存为预设只新建、编辑预设才覆盖",
      'store.jsonOpts("POST", store.profileForm)' in store_js
      and "`/api/profile/presets/${store.presetModal.id}`" in store_js
      and 'store.jsonOpts("PUT", form)' in store_js, True)
check("覆盖接口在", "@router.put(\"/profile/presets/{preset_id}\")" in
      (ROOT / "app/routes/profile.py").read_text(encoding="utf-8"), True)

# ---- 两侧气泡同一种白底 ----
_bub = css_rule(".msg.user .bubble")
check("用户气泡改成白底 + 边框",
      "background: var(--panel);" in _bub and "border: 1px solid var(--border);" in _bub, True)
check("用户气泡不再用强调色实底",
      "var(--user-bubble)" in css or "color: #fff;" in _bub, False)

print()
if FAILED:
    print(f"失败 {len(FAILED)} 项：{FAILED}")
    sys.exit(1)
print("前端结构与命名用例全部通过")
