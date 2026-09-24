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
# data 字段只在 state.js 里找（状态集中在那一个 reactive 对象里）：方法体内的嵌套对象
# 也会有 6 空格缩进的 `name,`，拿全量源码去匹配会把这些局部键误当成 store 状态
# （踩过：chat.js 与 presets.js 里的 `kind,` 让 `kind` 变成一个假的状态字段）。
_state_js = (frontend / "src/store/state.js").read_text(encoding="utf-8")
STORE_KEYS = (
    set(re.findall(r"^      ([A-Za-z_$][\w$]*)[,:]", _state_js, re.M))           # data 字段
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


# ---- 相对 import 必须指到真实文件（DEVELOPMENT §9.7 前端工程约定） ----
# 组件分散在三层目录里（components/、panes/、modals/），store.js 的相对深度各不相同：
# 多写一层 `../` 时打包器才会报 "Could not resolve"，静态守卫（模板标识符、构建产物）全都看不见。
# 这里把每条相对 import 解析成路径核对一遍，省一次"构建才发现"。
# 注意两件事：正则要写 `(\.[^"]+)` 而不是 `(\./[^"]+)`——后者只匹配 `./x`，多层 `../../x`
# 会被静默跳过（这条守卫第一版就踩了这个坑，等于空转）；另外要先去掉注释，注释里举例写的
# `from "../store.js"` 不是真的 import（store.js 的说明注释里就有这么一句）。
def _code_only(text: str) -> str:
    text = re.sub(r"/\*.*?\*/", "", text, flags=re.S)
    return re.sub(r"//[^\n]*", "", text)


_bad_imports = []
for _rel, _src in zip(VUE_ORDER, vue_sources):
    _base = (frontend / "src" / _rel).parent
    for _spec in re.findall(r'from\s+"(\.[^"]+)"', _code_only(_src)):
        if not (_base / _spec).resolve().exists():
            _bad_imports.append(f"{_rel} -> {_spec}")
for _f in store_files + [frontend / "src/main.js"]:
    _base = _f.parent
    for _spec in re.findall(r'from\s+"(\.[^"]+)"', _code_only(_f.read_text(encoding="utf-8"))):
        if not (_base / _spec).resolve().exists():
            _bad_imports.append(f"{_f.name} -> {_spec}")
check("相对 import 都指到真实文件", _bad_imports, [])


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

# ---- 右侧面板：竖排图标栏 + 展开的内容面板 ----
# 标签从横向文字钮改成最右一条竖排图标（icon rail）：面板收起时也常驻，点图标滑出对应面板、
# 再点当前激活图标收起；悬停显示文字提示（原横向标签的"未保存"圆点沿用到图标右上角）
check("右侧内容面板在", 'class="panel-box"' in html, True)
check("竖排图标栏在（icon rail）", 'class="panel-rail"' in html, True)
check("图标按钮只有一个模板（v-for 渲染五个）", html.count('class="rail-btn"'), 1)
check("五个图标由配置表驱动（加标签只动 tabs 数组）", "const tabs = [" in html, True)
check("内容面板（模板里五个）", html.count("panel-tab-pane"), 5)
check("旧的折叠结构已清除",
      [w for w in ("panel-section", "panelFold", "togglePanelFold") if (w in html or w in js)], [])
check("CSS 里的折叠样式已清除", ".panel-section" in css_code, False)
check("未保存圆点样式在（图标右上角的小点）", ".tab-dot" in css, True)
check("当前标签的未保存状态有计算属性", "activeTabDirty" in js and "activeTabDirty" in html, True)
check("图标的未保存圆点按各标签分别判断",
      "this.worldDirty" in js and "this.charDirty" in js and "this.profileDirty" in js
      and "this.memoryDirty" in js and "this.genDirty" in js, True)
check("点图标：收起时展开、点当前图标收起、点别的图标仅切换",
      "this.panelCollapsed" in js and "this.panelTab" in js and "togglePanel" in html, True)
# ---- "配置"开关已移除：原顶栏最右那个开关由最右竖排图标栏取代（DEVELOPMENT §9.6 界面约定更新） ----
check("顶栏不再有『配置』开关",
      any(w in html for w in ("panel-toggle", '"配置 ›"', '"配置 ‹"')), False)
check("面板里没有标题行 / 没有第二个开关",
      'class="panel-head"' not in html and 'class="panel-title"' not in html, True)
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
check("面板 = 内容区 + 竖排图标栏，收起仍留一条图标",
      "calc(var(--panel-w) + var(--rail-w))" in css
      and ".panel.collapsed { width: var(--rail-w); }" in css, True)

# ---- 分隔线：左右两侧同一条（DEVELOPMENT §9.6 界面约定） ----
check("分隔线定义成变量", "--divider: 2px solid #39404f;" in css, True)
check("两处分区线都用它（左侧标题 / 左侧模式按钮）",
      css.count("border-bottom: var(--divider);"), 2)
# 图标按钮框线常驻（透明），选中/悬停才着色：避免选中状态导致尺寸跳变
rail_css = re.search(r"\.rail-btn \{[^}]*\}", css)
check("图标按钮框线常驻不跳变",
      bool(rail_css) and "border: 1px solid transparent;" in rail_css.group(0), True)
on_rail_css = re.search(r"\.rail-btn\.on \{[^}]*\}", css)
check("选中图标用强调色边框 + 深色底区分",
      bool(on_rail_css) and "border-color: var(--accent);" in on_rail_css.group(0)
      and "background: var(--field);" in on_rail_css.group(0), True)

# ---- 字数上限与右下角实时提示 ----
counters = html.count('class="char-count')
check("计数提示数量（含底部输入区两栏、我的设定三项、两种预设弹窗各三项、世界设定三项与词条两项、附加属性两项）",
      counters, 35)
check("每个计数器都有 .counted 定位父层", html.count('class="counted') >= counters, True)
check("计数方法在", "isNear(value, max)" in js and "len(value)" in js, True)
# 所有自由文本输入都要有 maxlength（文件选择、单选、滑杆、数字框除外——数字框用 min/max）；
# 会话内搜索框是界面过滤器、不落库，也不该占一个上限，所以单独放行
free_boxes = []
for tag, attrs in re.findall(r"<(input|textarea)([^>]*)>", html, flags=re.S):
    if tag == "input" and any(k in attrs for k in (
            'type="file"', 'type="radio"', 'type="range"', 'type="number"')):
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

# ---- 竖排图标栏与内容面板在滚动容器外（内容一长也够得着） ----
check("图标栏排在内容面板之后（贴最右）",
      html.index('class="panel-box"') < html.index('class="panel-rail"'), True)
check("标签内容面板在滚动容器之内",
      html.index('class="panel-body"') < html.index("panel-tab-pane"), True)
check("内容区与图标栏都不参与伸缩",
      ".panel-box {\n  flex: none;" in css and ".panel-rail {\n  flex: none;" in css, True)
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

# ---- 附加属性（角色的动态状态，见 DEVELOPMENT §2.6） ----
# 定义在角色设定标签页里编辑，值随每条消息落库；顶部浮层显示最新一份，气泡里不显示
check("角色设定标签页里挂上定义编辑器",
      'components/AttrEditor.vue' in VUE_ORDER and "<AttrEditor :form=\"charForm\" />" in html, True)
check("定义编辑器三项齐全（名称 / 类型 / 解释）",
      ">名称</span>" in html and ">类型</span>" in html and ">解释</span>" in html
      and "attr_defs" in html, True)
check("类型下拉有占位与两种类型",
      '<option value="">选择类型…</option>' in html
      and '<option v-for="t in ATTR_TYPES"' in html, True)
check("类型必须在界面上选（占位项为空值）", 'class="attr-line select' in css
      or ".attr-line select.empty" in css, True)
check("定义可增可删、到上限置灰",
      '@click="addAttr(form)"' in html and '@click="removeAttr(form, i)"' in html
      and ':disabled="form.attr_defs.length >= limits.attr_max"' in html, True)
# 需求："名称必须填、类型必须选"——名称为空的行保存时丢弃（同词条），
# 填了名称却没选类型要挡下来
check("保存前校验必须选类型",
      "validateAttrDefs(form)" in js and "选个类型（文字型或百分比型）" in js, True)
check("保存前丢掉没命名的行", "cleanAttrDefs(form)" in js
      and "filter((d) => d.name.trim() && d.type)" in js, True)
check("面板保存带着清理后的定义",
      "charPayload.attr_defs = this.cleanAttrDefs(this.charForm);" in js, True)
# 面板表单是整体提交的：漏了 attr_defs 就会在保存角色设定时把定义清空（与 avatar 同一个坑）
check("切换会话时把定义带进面板表单",
      "attr_defs: (c.attr_defs || []).map((d) => ({ ...d }))" in js, True)
check("定义也进 emptyCharForm（面板与新角色表单都用它）",
      "attr_defs: []," in js, True)

# 浮层：可收纳、贴在对话区顶部、只在选中会话且有属性时出现
check("浮层组件挂在消息列表里（sticky 自己占位）",
      'components/AttrPanel.vue' in VUE_ORDER
      and html.index("<AttrPanel />") < html.index('v-for="m in displayMessages"'), True)
check("浮层用 sticky 贴在对话区顶部", ".attr-panel {" in css
      and "position: sticky;" in css and "z-index: 300;" in css and "align-self: center;" in css, True)
# 展开态的宽度要落在"能读清"与"不铺张"之间：太窄（按内容缩成 255px）像信息条、
# 与气泡一样宽（680px）又太宽——用户的两次反馈分别针对这两头，所以钉住中间那个值
check("展开态宽度取中间值（不是按内容缩成窄条，也不是与气泡同宽）",
      "max-width: min(400px, 100%);" in css
      and "width: max-content;" in css.split(".attr-panel.collapsed")[1][:120], True)
check("浮层可收纳（收起时只是一个图标，展开才有标题与内容）",
      'class="attr-icon"' in html and "attrsCollapsed = false" in html
      and 'class="attr-toggle"' in html and ".attr-icon {" in css
      and ".attr-panel.collapsed" in css, True)
check("浮层只在选中会话 + 聊天/沉浸 + 有值时出现",
      "showAttrPanel = computed" in js and "if (!this.activeSession || this.isDirectorMode) return false;" in js
      and "v-if=\"showAttrPanel\"" in html, True)
# 让位不靠量高度：sticky 自己就占位（早先按实测高度让位，展开时仍压住第一条消息 51px）
check("不再靠量高度让位（sticky 自己占位）",
      "attrPanelH" in js or "ResizeObserver" in js, False)
check("文字型直接显示文字、百分比型渲染进度条",
      'v-if="a.type === \'percent\'"' in html and 'class="attr-bar-fill"' in html
      and "attrPercent(a) + '%'" in html and 'class="attr-value"' in html, True)
check("百分比条样式在", ".attr-bar {" in css and ".attr-bar-fill {" in css, True)
# 显示的是**最近一条带属性的消息**，不是最新一条消息：用户刚发完言那条没有属性，
# 取最新一条会让浮层闪空
check("浮层取最近一条带属性的消息",
      "latestAttrs = computed" in js and "for (let i = this.messages.length - 1; i >= 0; i--)" in js
      and "if (attrs && attrs.length) return attrs;" in js, True)

# 编辑面板：能改属性，但属性不出现在消息与气泡里
check("编辑弹窗里有属性一节（仅聊天与沉浸）",
      "showAttrInEditor" in html and ">附加属性</span>" in html, True)
check("百分比型用数字框、文字型用输入框",
      'v-if="a.type === \'percent\'" v-model="a.value" type="number"' in html
      and ':maxlength="limits.attr_value"' in html, True)
check("编辑弹窗按角色定义铺开属性行",
      "attrs: this.showAttrInEditor ? this.attrRowsFor(m) : []" in js
      and "attrRowsFor(message) {" in js, True)
check("保存编辑时一起提交属性（空值不提交）",
      "payload.attrs = this.editForm.attrs" in js
      and 'filter((a) => String(a.value).trim() !== "")' in js, True)
check("SSE done 带回的属性直接进消息列表",
      "attrs: d.attrs || []," in js, True)
check("气泡与消息组件完全不碰属性", "attrs" in dict(zip(VUE_ORDER, vue_sources))["components/MessageItem.vue"], False)

# ---- 我的设定（用户资料） ----
check("有我的设定图标（配置表里登记）", '{ key: "profile", label: "我的设定"' in html, True)
check("我的设定面板在", 'panelTab === \'profile\'' in html, True)
check("面板顶部的输出倾向已改名", "输出倾向" in html or "genSectionTitle" in js, False)
check("生成要求图标在配置表里", '{ key: "gen", label: "生成要求"' in html, True)
check("用户头像有第三个 target", "pickAvatar($event, 'profile')" in html, True)
check("头像归属有统一入口", "avatarForm(target)" in js, True)
check("我的设定有独立的脏标记与还原", "profileDirty" in js and 'section === "profile"' in js, True)
check("保存派发包含我的设定", 'if (this.panelTab === "profile") return this.saveProfile();' in js, True)
check("启动时加载我的设定", 'await this.api("/api/profile")' in js, True)

# ---- 世界设定（全局一份，三种模式都用得上） ----
check("有世界设定图标（配置表里登记）", '{ key: "world", label: "世界设定"' in html, True)
check("世界设定面板在", "panelTab === 'world'" in html, True)
check("世界设定图标不判模式（导演模式也显示）",
      "t.key === 'world'" not in html or "{ key: \"world\", label: \"世界设定\" }" in html, True)
check("世界设定有独立的脏标记与还原", "worldDirty" in js and 'section === "world"' in js, True)
check("保存派发包含世界设定", 'if (this.panelTab === "world") return this.saveWorld();' in js, True)
check("启动时加载世界设定", 'await this.api("/api/world")' in js, True)
check("词条可增可删（方法收一份表单，面板与预设弹窗共用）",
      "addTerm(form) {" in js and "removeTerm(form, index) {" in js
      and '@click="addTerm(form)"' in html and '@click="removeTerm(form, i)"' in html, True)
check("到上限后不能再加词条",
      ':disabled="form.terms.length >= limits.world_terms_max"' in html, True)
check("名称注明不发给模型", "只用于自己辨认，不发给模型" in html, True)
check("词库说明写清空行会被丢弃", "名词留空的行在保存时自动丢弃" in html, True)
# 竖排图标栏：宽度固定、竖排；图标是同一套 24px 线性图标，统一随按钮颜色走（currentColor）
rail_box_css = re.search(r"\.panel-rail \{[^}]*\}", css)
check("图标栏宽度固定", bool(rail_box_css) and "width: var(--rail-w);" in rail_box_css.group(0), True)
check("图标栏竖排", bool(rail_box_css) and "flex-direction: column;" in rail_box_css.group(0), True)
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
check("每个滚动型弹窗都有字段滚动区（角色 / 编辑消息 / 编辑预设 / 载入预设）",
      len(re.findall(r'class="modal-body', html)), 4)
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
check("搜索框在工具栏里",
      html.index('class="toolbar"') < html.index('class="search-box"'), True)
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
check("搜索框后面有清空键（常驻、没关键词时置灰）",
      'aria-label="清空搜索"' in html and ':disabled="!searchQuery" @click="clearSearch"' in html, True)
check("清空键不按状态出现/消失（只置灰）",
      'v-if="searchQuery"' in html, False)
check("搜索框与计数都不伸缩",
      ".search-box {\n  flex: none;" in css and "min-width: 42px;" in css, True)
# 按钮必须显式 opacity: 1——.icon-btn 默认是"悬停才显形"（给侧栏用的），
# 照搬过来会让按钮可点却看不见
check("搜索框按键可见", ".search-box .icon-btn {\n  flex: none;\n  opacity: 1;" in css, True)
check("搜索框在模型选择左边",
      html.index('class="search-box"') < html.index('class="model-select"'), True)
check("顶栏放不下时换行而不是溢出", "flex-wrap: wrap;" in css, True)

# ---- 图标上的未保存小点不能改变图标尺寸 ----
check("小点是绝对定位且不吃外边距",
      ".tab-dot {" in css and "position: absolute;" in css
      and "margin-left: 6px;" not in re.search(r"\.tab-dot \{[^}]*\}", css).group(0)
      and "top:" in re.search(r"\.tab-dot \{[^}]*\}", css).group(0)
      and "right:" in re.search(r"\.tab-dot \{[^}]*\}", css).group(0), True)

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
check("介绍浮层朝上弹（下方是会话列表，向下会遮住会话）", "bottom: calc(100% + 6px);" in _tip, True)
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

# ---- "我的设定"与"世界设定"的预设：一套实现 + kind 派发（DEVELOPMENT §2.3 / §2.4） ----
# 两种预设是同一套东西（挑一条、看详情、立即生效；另存、覆盖、删除），差别只是字段与接口，
# 所以 store 里一份实现按 kind 派发，组件也共用同一对弹窗——加一种预设只改 helpers 里的配置。
check("面板只显示当前预设名（两种各一行）",
      html.count('class="preset-current">当前预设：<b>{{ currentPresetLabel }}</b>') == 1
      and 'class="preset-current">当前世界预设：<b>{{ currentWorldPresetLabel }}</b>' in html, True)
check("两处面板各有三个入口键（载入 / 编辑 / 存为）",
      [html.count(f">{k}</button>") for k in ("载入预设…", "编辑预设…", "存为预设")] == [2, 2, 2], True)
check("载入 / 编辑 / 存为 的排列顺序",
      (html.index(">载入预设…</button>") < html.index(">编辑预设…</button>")
       < html.index(">存为预设</button>")), True)
check("面板上不放删除（不可逆操作收进弹窗）", ">删除预设</button>" in html, False)
check("载入弹窗有列表与详情",
      'class="preset-list"' in html and 'class="preset-detail"' in html
      and ">载入这条</button>" in html and "picked.identity" in html, True)
check("删除在编辑预设弹窗里", ">删除这条预设</button>" in html, True)
check("两个预设弹窗共用同一套两栏骨架（一份模板管两种预设）",
      html.count('class="modal-body preset-split"') == 2
      and html.count('class="preset-list"') == 2
      and html.count('class="preset-detail"') == 2, True)
check("两个预设弹窗同宽（且压得住 .modal.edit-modal 的写法）",
      ".modal.load-modal,\n.modal.preset-modal { width: 620px; }" in css, True)
# 同理：基础 `.modal-body` 是列布局且写在文件后部，两栏要显式写复合选择器才并排
check("两栏用复合选择器压住 .modal-body 的列布局",
      ".modal-body.preset-split {" in css and "flex-direction: row;" in css, True)
check("弹窗标题与列表按 kind 决定",
      "kind.loadTitle" in html and "kind.editTitle" in html
      and "v-for=\"p in presets\"" in html and "kind.sub(p)" in html, True)
check("世界预设有自己的详情字段（描述/规则/词库）",
      "<dt>世界名称</dt>" in html and "<dt>词库</dt>" in html, True)
check("没有预设时给出提示", "还没有预设" in html and "还没有世界预设" in html, True)
check("预设方法齐全（kind 参数化的那几个）",
      all(k in js for k in ("async loadPresets(kind = \"profile\") {", "async writeCurrent(kind, values, presetId) {",
                            "async applyPreset(kind, id) {", "openLoadModal(kind) {",
                            "closeLoadModal() {", "pickLoadPreset(id) {", "async confirmLoadPreset() {",
                            "async savePreset(kind) {", "openPresetModal(kind) {", "editPickPreset(id) {",
                            "async savePresetModal() {", "async deletePresetInModal() {")), True)
check("kind 配置表在 helpers 里（加一种预设只动配置）",
      "export const PRESET_KINDS = {" in js and "profile: {" in js and "world: {" in js
      and 'listKey: "worldPresets"' in js and 'currentKey: "currentWorldPresetId"' in js, True)
check("预设列表的字段名从配置里取（不写死 profilePresets）",
      "const k = kindOf(kind);" in js and "store[k.listKey]" in js, True)
# 载入 = 立即生效（写当前生效的那份），所以要带一次"覆盖"确认；删除也要确认
_write = js[js.index("async writeCurrent(kind, values, presetId) {"):js.index("async applyPreset(kind, id) {")]
_confirm = js[js.index("async confirmLoadPreset() {"):js.index("async savePreset(kind) {")]
check("载入前对未保存改动要确认", "await this.ask(" in _confirm, True)
check("载入走同一条“立即生效”路径", "await this.applyPreset(kind, p.id)" in _confirm, True)
check("立即生效写到配置里的那个接口",
      "this.api(k.base" in _write and 'this.jsonOpts("PUT", values)' in _write, True)
check("立即生效后当前那份与表单一起更新",
      "store[rowKey(kind)] = saved" in _write
      and "store[formKey(kind)] = this.snapshot(saved)" in _write, True)
check("立即生效后记住当前预设", "store[k.currentKey] = presetId" in _write, True)
check("当前预设名带“已修改”判定",
      "currentPresetLabel = computed" in js and "currentWorldPresetLabel = computed" in js
      and "（已修改）" in js, True)
check("启动时两种预设列表都拉一次",
      'await this.loadPresets("profile");' in js and 'await this.loadPresets("world");' in js, True)
check("删除预设要确认（两种都有文案）", "删除预设「" in js and "删除世界预设「" in js, True)
check("预设样式在", ".preset-row {" in css and ".preset-current {" in css
      and ".preset-item {" in css and ".preset-detail {" in css, True)
check("世界面板也有一行当前世界预设与三个键",
      ">当前世界预设：" in html and html.count("openLoadModal('world')") == 1
      and "openPresetModal('world')" in html and "savePreset('world')" in html, True)
check("我的设定面板的键带着自己的 kind",
      "openLoadModal('profile')" in html and "openPresetModal('profile')" in html
      and "savePreset('profile')" in html, True)

# ---- 预设绑定：身份与世界跟着角色走（DEVELOPMENT §2.3 / §2.4） ----
# 一份预设可以被多个角色共用，所以绑定存在角色那侧（characters.profile_id / world_id），
# 两个预设弹窗只负责显示"这条预设给了哪些角色"，改绑在「编辑角色」里
check("两个预设弹窗都显示绑定角色",
      html.count("presetBindLabel(p)") == 2 and "presetBindLabel(picked)" in html, True)
check("列表里有绑定那一行", html.count('class="preset-item-bind"') == 2 and ".preset-item-bind {" in css, True)
check("绑定文案函数在（没绑就是「未绑定」）",
      "presetBindLabel(p) {" in js and '"未绑定"' in js, True)
check("角色弹窗里有身份与世界两个下拉",
      'v-model="charModal.form.profile_id"' in html and 'v-model="charModal.form.world_id"' in html
      and '<option :value="null">不绑定（不用预设）</option>' in html
      and '<option :value="null">不绑定（不用世界设定）</option>' in html, True)
check("下拉列出所有预设", 'v-for="p in profilePresets" :key="p.id" :value="p.id"' in html
      and 'v-for="p in worldPresets" :key="p.id" :value="p.id"' in html, True)
check("绑定项与角色字段分开", ".field-bind {" in css and 'class="field field-bind"' in html, True)
# 两个绑定字段只能加在弹窗表单里：右侧面板的 charForm 用的是同一个 emptyCharForm()，
# 多带一个 null 就等于"一保存角色设定就把两个绑定都解了"
_char_form = js[js.index("export const emptyCharForm = () =>"):js.index("export const emptyCharModal = () =>")]
check("面板表单不带绑定字段", ("profile_id" in _char_form) or ("world_id" in _char_form), False)
check("弹窗表单带两个绑定字段", "profile_id: null, world_id: null" in js, True)
check("打开角色弹窗时带上两个绑定",
      "profile_id: c.profile_id ?? null" in js and "world_id: c.world_id ?? null" in js, True)
check("打开角色弹窗时确保两种预设都加载过",
      'if (!this.profilePresets.length) this.loadPresets("profile");' in js
      and 'if (!this.worldPresets.length) this.loadPresets("world");' in js, True)
# 校准规则：绑了预设就用它；没绑就不用预设（当前正用着预设时清空）；
# 已经就是那一条则什么都不做（面板上临时手改过的内容要留住）；找不到预设时一律不动
_sync = js[js.index("async syncBinding(kind, boundId) {"):js.index("presetBindLabel(p) {")]
check("打开会话时校准", "await this.syncCharacterBindings();" in js, True)
_after_char = js[js.index("async afterCharacterChange() {"):]
_after_char = _after_char[: _after_char.index("});")]
check("改完角色设定（绑定可能变了）也校准",
      "await this.syncCharacterBindings();" in _after_char, True)
check("角色会话校准两个绑定", 'await this.syncBinding("profile", c.profile_id);' in js
      and 'await this.syncBinding("world", c.world_id);' in js, True)
check("导演会话按会话自己的世界校准",
      'if (s && s.mode === "director") await this.syncBinding("world", s.world_id);' in js, True)
check("已经是这条预设就不再覆盖", "if (store[k.currentKey] === bound.id) return;" in _sync, True)
check("没绑且本来就没用预设就不动", "if (!store[k.currentKey]) return;" in _sync, True)
check("没绑时清空（不用预设）", 'await this.writeCurrent(kind, k.empty(), "");' in _sync, True)
check("找不到那条预设时按“没绑”处理（保守，不乱清）",
      "const bound = boundId ? store[k.listKey].find((p) => p.id === boundId) : null;" in _sync, True)
check("面板上有没保存的改动时不校准（别冲掉正在编辑的内容）",
      "if (dirtyOf(kind)) return;" in _sync, True)
check("导演会话换世界会写会话本身",
      '"PATCH", { world_id: worldId }' in js
      and 'await this.syncBinding("world", saved.world_id);' in js, True)

# ---- 世界设定：面板表单 + 导演会话选世界 + 词库编辑器共用（DEVELOPMENT §2.4） ----
check("世界面板有本会话的世界下拉（仅导演模式）",
      'v-if="isDirectorMode"' in html and "setSessionWorld($event.target.value" in html, True)
check("新建会话弹窗里按模式换字段",
      "v-if=\"mode !== 'director'\"" in html and "<option :value=\"null\">不用世界设定</option>" in html, True)
check("新建导演会话会带上世界",
      "world_id: m.worldId ?? null" in js and "characterMode ? {} : { world_id: m.worldId ?? null }" in js, True)
check("词库编辑器抽成组件、面板与预设弹窗共用",
      "components/TermEditor.vue" in VUE_ORDER and html.count("<TermEditor") == 2
      and "defineProps({ form: { type: Object, required: true } })" in html, True)
check("词条增删都作用在传进来的表单上",
      "@click=\"addTerm(form)\"" in html and "@click=\"removeTerm(form, i)\"" in html, True)

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
      "pointer-events: none;" in _shared_tip and "background: #3a4252;" in _shared_tip, True)
check("v-hint 浮层定位与层级",
      "position: fixed;" in _hint_css and "z-index: 1500;" in _hint_css, True)
# 浮层层级表必须单调递增：普通遮罩 < 裁剪遮罩 < 确认框 < 提示浮层。
# 确认框可能从任何弹窗里弹出来（删除预设、载入预设覆盖…），级别不够就会被上层弹窗盖住，
# 用户"点确认"实际点到那个弹窗的遮罩上，反而把它关掉——之前就是这么坏的。
_z = {}
for _sel, _name in ((".modal-mask", "遮罩"), (".crop-mask", "裁剪"), (".confirm-mask", "确认框"),
                    (".hint-tip", "提示")):
    _m = re.search(r"^" + re.escape(_sel) + r"\s*\{[^}]*z-index:\s*(\d+)", css, re.M)
    if not _m:  # .modal-mask 的规则里 z-index 不在最前面
        _m = re.search(r"^" + re.escape(_sel) + r"\s*\{([^}]*)\}", css, re.M)
        _n = re.search(r"z-index:\s*(\d+)", _m.group(1)) if _m else None
        _z[_name] = int(_n.group(1)) if _n else 0
    else:
        _z[_name] = int(_m.group(1))
check("层级表单调递增（遮罩 < 裁剪 < 确认框 < 提示）",
      [_z["遮罩"] < _z["裁剪"] < _z["确认框"] < _z["提示"]], [True])
# 同级按 DOM 顺序决胜，所以确认框在 App.vue 里也排在最后
_app = dict(zip(VUE_ORDER, vue_sources))["App.vue"]
check("ConfirmModal 在根组件里排在最后",
      _app.index("<ConfirmModal />") > max(
          _app.index(f"<{m} />") for m in ("CharacterModal", "NewSessionModal", "EditMessageModal",
                                          "CropModal", "PresetModal", "LoadPresetModal")), True)
check("确认框有专属遮罩类", 'class="modal-mask confirm-mask"' in html, True)
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
      "@click=\"openLoadModal('profile')\"" in _pp and "loadPreset() {" in _pp, False)
check("预设的编辑走独立弹窗",
      "@click=\"openPresetModal('profile')\"" in _pp
      and (frontend / "src/components/modals/PresetModal.vue").exists(), True)
check("存为预设只新建、编辑预设才覆盖",
      'store.jsonOpts("POST", store[formKey(kind)])' in store_js
      and "`${k.presets}/${store.presetModal.id}`" in store_js
      and 'store.jsonOpts("PUT", form)' in store_js, True)
check("覆盖接口在", "@router.put(\"/profile/presets/{preset_id}\")" in
      (ROOT / "app/routes/profile.py").read_text(encoding="utf-8"), True)

# ---- 两侧气泡同一种白底 ----
_bub = css_rule(".msg.user .bubble")
check("用户气泡改成白底 + 边框",
      "background: var(--panel);" in _bub and "border: 1px solid var(--border);" in _bub, True)
check("用户气泡不再用强调色实底",
      "var(--user-bubble)" in css or "color: #fff;" in _bub, False)

# ---- 桌面端（Electron 壳）专属界面（DEVELOPMENT §7.4） ----
# 同一份前端：壳在 preload 里注入 window.dshDesktop，于是多出"配置 / 手机视图"两个键；
# 网页端与手机浏览器没有这个对象，那两个键根本不渲染
check("挂载前先认壳的标记（第一屏不闪桌面键）",
      "initDesktop()" in js and "initDesktop" in re.search(
          r'import \{([^}]*)\} from "./store.js"', main_js).group(1), True)
_comp = dict(zip(VUE_ORDER, vue_sources))
_topbar = _comp["components/TopBar.vue"]
_panel = _comp["components/Panel.vue"]
_config = _comp["components/ConfigPanel.vue"]
readme = (ROOT / "README.md").read_text(encoding="utf-8")
shell_js = (ROOT / "desktop" / "main.js").read_text(encoding="utf-8")
preload_js = (ROOT / "desktop" / "preload.js").read_text(encoding="utf-8")

# 顶栏只留「手机视图」（在主题键旁）；「配置」搬到右侧图标列**最低栏**（rail 底部），
# 而没有会话时整条图标列不存在（Panel.vue 以 activeSession 为条件）——所以顶栏还留了一个
# 只在 !activeSession 时出现的兜底 ⚙，否则空状态那一屏就再也进不去配置
check("顶栏只留手机视图键（配置键已搬走）",
      'aria-label="收纳成手机视图"' in _topbar
      and 'class="icon-btn desktop-btn"' in _topbar, True)
check("顶栏兜底配置键只在没有会话时出现",
      _topbar.count('v-if="isDesktop && !desktopPhoneView && !activeSession"') == 1
      and _topbar.count('aria-label="配置"') == 1, True)
check("配置键在图标列最低栏（margin-top:auto 顶到底）",
      'class="rail-btn rail-config"' in _panel
      and ".rail-config { margin-top: auto; }" in css, True)
check("面板挂在图标列左下（无会话时挂顶栏）",
      '<ConfigPanel v-if="isDesktop && !desktopPhoneView && desktopConfigOpen" class="at-rail" />' in _panel
      and ('<ConfigPanel v-if="isDesktop && !desktopPhoneView && !activeSession '
           '&& desktopConfigOpen" />') in _topbar, True)
check("配置面板内容齐全（开关 / 状态 / 二维码 / 地址 / 手机视图 / 防火墙 / 日志）",
      all(k in _config for k in ('class="dc-switch"', 'class="dc-status"', 'class="dc-qr"',
                                 'class="dc-url"', 'class="dc-label"', "togglePhoneView",
                                 "copyFirewallCmd", "openLog")), True)
check("二维码是 qrcode 画在 canvas 上（不手搓、不用 v-html）",
      "QRCode.toCanvas(" in _config and "v-html" not in _config, True)
check("二维码只在取到地址时画，局域网关着时置灰",
      "if (lanUrl.value) paint();" in _config and ':class="{dim: !lanEnabled}"' in _config, True)
check("配置面板层级在浮层与弹窗之间",
      ".desktop-config {" in css and "z-index: 600;" in css
      and css.index("z-index: 600;") < css.index(".modal-mask {"), True)
check("面板贴图标列时向左展开",
      ".desktop-config.at-rail {" in css and "right: calc(100% + 10px);" in css, True)
# 桌面键曾被 .icon-btn 的 opacity:0 与"没有固有尺寸的内联 SVG"叠成看不见的 10px 方块（实测踩到），
# 所以尺寸与可见性必须写死，别让它悄悄退回去
_desktop_btn_css = css_code[css_code.index(".desktop-btn {"):css_code.index(".desktop-btn.on")]
check("桌面键的尺寸与可见性写死",
      "opacity: 1;" in _desktop_btn_css and "width: 34px;" in _desktop_btn_css
      and ".desktop-btn svg { display: block; width: 18px; height: 18px; }" in css, True)
check("防火墙命令与 README 同源（改一处必须改另一处）",
      "netsh advfirewall firewall add rule" in js and "OllamaAgent 局域网访问" in js
      and "netsh advfirewall firewall add rule" in readme
      and "OllamaAgent 局域网访问" in readme, True)
check("开关写的是后端设置里的 lan_enabled",
      'jsonOpts("PUT", { lan_enabled: !this.lanEnabled })' in js
      and "this.lanEnabled = !!s.lan_enabled;" in js, True)
check("初始状态从 /api/settings 读回来",
      "this.disableThinking = !!s.disable_thinking;" in js
      and "this.lanEnabled = !!s.lan_enabled;" in js, True)
check("手机视图交给壳去缩窗口，页面只跟着隐藏桌面键",
      "window.dshDesktop.togglePhoneView()" in js and "api.onPhoneView(" in js
      and "this.desktopPhoneView = !!on;" in js, True)
check("桌面键与配置面板的样式在", ".desktop-btn {" in css and ".dc-switch.on .dc-knob {" in css, True)
# 壳侧：宽度锁死（min==max，按窗口尺寸算，要补边框差）、高度留自由；退出恢复桌面尺寸。
# 早先手机尺寸被当成桌面尺寸存进 desktop.json，导致"在手机视图下退出后窗口再也回不到大尺寸"
check("壳把手机视图宽度锁死、高度留自由",
      "PHONE_WIDTH + frameW" in shell_js and "setMaximumSize(0, 0)" in shell_js
      and "setContentSize(PHONE_WIDTH," in shell_js, True)
check("桌面尺寸与手机高度分开存",
      "phoneHeight: win.getContentSize()[1]" in shell_js and "persistWindowState()" in shell_js, True)
check("壳日志能从面板里打开",
      "openLog:" in preload_js and 'ipcMain.handle("desktop:open-log"' in shell_js, True)

# ---- 移动端适配（DEVELOPMENT §7.1 / §9.6：三断点 + 抽屉/底部弹层 + 触屏约定） ----
_mobile = css[css.index("@media (max-width: 640px) {"):]
check("viewport 带 viewport-fit（刘海屏 safe-area 生效）", "viewport-fit=cover" in html, True)
check("安全区变量在", "--sat: env(safe-area-inset-top, 0px);" in css
      and "--sab: env(safe-area-inset-bottom, 0px);" in css, True)
check("聚焦不放大 / 滚动不透传", "-webkit-text-size-adjust: 100%;" in css
      and "overscroll-behavior: none;" in css, True)
check("手机断点在（≤640px 单栏）", "@media (max-width: 640px) {" in css, True)
check("紧凑桌面断点在（641-900px）", "@media (min-width: 641px) and (max-width: 900px) {" in css, True)
# 左侧栏 → 抽屉：fixed + 平移藏起，mobile-open 滑出；手机端忽略桌面 collapsed 的 0 宽
check("手机断点下侧栏变抽屉",
      "position: fixed;" in _mobile and "transform: translateX(-100%);" in _mobile
      and ".sidebar.mobile-open { transform: translateX(0); }" in css, True)
check("手机断点下侧栏忽略桌面收起",
      ".sidebar.collapsed {\n    width: min(80vw, 320px);" in css, True)
# 右侧面板 → 底部弹层：fixed 底部 + 平移藏起，mobile-open 滑出；图标栏横排当标签
check("手机断点下面板变底部弹层",
      "transform: translateY(105%);" in css and ".panel.mobile-open { transform: translateY(0); }" in css
      and "border-radius: 16px 16px 0 0;" in css, True)
check("手机断点下面板收起不缩内容（弹层整体开合）",
      ".panel.collapsed .panel-box { width: 100%; }" in css, True)
check("手机断点下图标栏横排到弹层顶部",
      "order: -1;" in _mobile and "flex-direction: row;" in _mobile, True)
# 三个浮层共用的遮罩
check("遮罩在根组件（任一浮层打开就显示）",
      'v-if="mobileMask" class="mobile-mask"' in html and '@click="closeMobileLayers"' in html, True)
check("遮罩桌面隐藏、手机显示",
      ".mobile-mask,\n.mobile-search-btn," in css
      and ".mobile-mask {\n    position: fixed;\n    inset: 0;" in css
      and "z-index: 900;" in css and "display: block;" in css, True)
# store 的移动端状态与方法
for _key in ("mobileSideOpen", "mobilePanelOpen", "mobileMoreOpen", "mobileSearchOpen"):
    check(f"store 有 {_key}", f"{_key}: false," in store_js, True)
check("mobileMask 计算属性在", "mobileMask: computed" in store_js, True)
check("closeMobileLayers 在", "closeMobileLayers() {" in store_js, True)
# 顶栏手机精简：汉堡开抽屉 + 放大镜折叠搜索 + 更多菜单
_tb = dict(zip(VUE_ORDER, vue_sources))["components/TopBar.vue"]
check("汉堡在手机断点打开抽屉", "@click=\"toggleSide\"" in _tb and "toggleSide() {" in _tb, True)
check("放大镜与更多入口在", 'mobile-search-btn' in _tb and 'mobile-more-btn' in _tb, True)
# 面板有顶栏直达入口（不再只藏在更多菜单里）+ 弹层固定高度（标签切换不跳变）
check("顶栏有面板直达按钮", 'class="icon-btn mobile-panel-btn"' in _tb
      and "toggleMobilePanel" in _tb and "mobilePanelOpen" in _tb, True)
check("弹层手机端固定高度", "height: 65vh;" in _mobile, True)
check("折叠搜索条在（只保留输入/清空/计数，↑↓ 不重复）",
      'class="mobile-search"' in _tb and "mobileSearchOpen" in _tb, True)
check("更多菜单收纳模型/思考/主题", 'class="mobile-more"' in _tb
      and "mobile-model" in _tb and "mobile-think" in _tb and "mobile-theme" in _tb, True)
check("更多菜单共用主题切换", "THEME_UI[theme].label" in _tb, True)
# 底部弹层的入口：面板走顶栏直达按钮；更多菜单里不再放"面板"行（避免重复入口）
check("更多菜单不再有面板行（面板走顶栏直达）",
      'mobile-panel-btn' in _tb and "面板：{{ mobilePanelOpen" not in _tb, True)
check("toggleMobilePanel 在 store（无会话时提示、不开空遮罩）",
      "toggleMobilePanel() {" in store_js and "store.mobilePanelOpen = !store.mobilePanelOpen;" in store_js
      and "flashHint" in store_js, True)
# 手机端进入会话后抽屉自动收回（openSession 里置 false）
check("openSession 后手机端关抽屉", "store.mobileSideOpen = false;" in store_js, True)
# 面板：手机端 mobile-open 绑定 + 图标点击走 onRailClick（只切页）
_pn = dict(zip(VUE_ORDER, vue_sources))["components/Panel.vue"]
check("面板绑定 mobile-open", "'mobile-open': mobilePanelOpen" in _pn, True)
check("图标点击在手机断点只切页", "onRailClick(tab) {" in store_js
      and "window.innerWidth <= 640" in store_js, True)
# 细节：沉浸输入堆叠 / 去头像列 / 操作条常显 / 弹窗全屏
check("沉浸输入两栏改上下堆叠",
      ".input-row { flex-direction: column; align-items: stretch; }" in _mobile, True)
check("发送键放大到 44px", "height: 44px;" in _mobile, True)
check("底部辅助按键收纳（⋯ 展开才显示背景切换/继续/跳底）",
      ".aux-toggle {" in _mobile
      and ".inputbar:not(.aux-open) .jump-btn," in _mobile, True)
check("收纳态情境一起收进⋯（只留话语框＋发送键）",
      ".inputbar:not(.aux-open) .scenario-field { display: none; }" in _mobile, True)
check("情境栏不再有独立折叠（统一由⋯收纳键控制）",
      "scen-fold" not in _input_bar and "scenOpen" not in _input_bar, True)
check("消息区头像恢复（40px）", ".msg-side { display: flex; }" in _mobile
      and ".msg-side .avatar.lg { width: 40px; height: 40px;" in _mobile, True)
check("附加属性浮层手机端收拢", ".attr-panel { font-size: 13px;" in _mobile
      and ".attr-body { gap: 5px;" in _mobile, True)
check("气泡放宽近全宽", ".bubble-wrap { max-width: 100%; }" in _mobile, True)
check("消息操作条手机常显（没有 hover）", ".msg-actions { opacity: 1; }" in _mobile, True)
check("弹窗手机全屏化", ".modal {\n    width: 100%;" in _mobile
      and "height: 100dvh;" in _mobile and "border-radius: 0;" in _mobile, True)
check("预设两栏在手机改回上下堆叠",
      ".modal-body.preset-split { flex-direction: column; }" in _mobile, True)
# 触屏降级：v-hint 在 pointer: coarse 下改点击显示
check("v-hint 触屏降级为点击显示", "(pointer: coarse)" in
      (frontend / "src/composables/hint.js").read_text(encoding="utf-8"), True)

print()
if FAILED:
    print(f"失败 {len(FAILED)} 项：{FAILED}")
    sys.exit(1)
print("前端结构与命名用例全部通过")
