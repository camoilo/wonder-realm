// 前端的全部状态与逻辑。
//
// 这一层是从原来的 Vue 选项对象机械搬过来的：data → reactive(store)、methods → store 上的函数、
// computed → computed() 后挂到 store 上（reactive 对象访问 ref 会自动解包）。**函数体一字未改**，
// 只把成员访问从组件实例改成了 store，这样拆组件时不必重写逻辑、也能和迁移前逐行对照。
//
// 组件一律 `import { store } from "../store.js"` 然后在模板里写 store.xxx：显式、无隐式注入。
import { computed, nextTick, reactive, watch } from "vue";

export const MODES = {
  character_chat: { label: "角色对话", character: true },
  character_scenario: { label: "角色情境", character: true },
  free_scenario: { label: "自由情境", character: false },
};

// 与后端 parser.py 保持同一套标记识别（理由见那里的注释）：宽容认标记，
// 但只认这几种词，大小写与全角括号都接受
const SCENARIO_TAGS = ["SCENARIO", "SCENERY", "SCENE", "NARRATION", "SETTING", "CONTEXT"];
const DIALOG_TAGS = ["DIALOG", "DIALOGUE", "SPEECH", "TALK"];
const ALL_TAG_SRC = SCENARIO_TAGS.concat(DIALOG_TAGS).join("|");
const TAG_SRC = "[\\[【]\\s*(?:" + ALL_TAG_SRC + ")\\s*[\\]】]";
const SEGMENT_RE = new RegExp(
  "[\\[【]\\s*(" + ALL_TAG_SRC + ")\\s*[\\]】]\\s*(.*?)(?=\\n?" + TAG_SRC + "|$)",
  "gis"
);
const isScenarioTag = (tag) => SCENARIO_TAGS.includes(String(tag).toUpperCase());

// "还原"键的解除武装计时器。放模块级而不是 data 里：定时器句柄不需要响应式
const revertTimers = {};

// 自由情境"继续"按钮发出的内容：等同于用户手打一条"继续"
const CONTINUE_PROMPT = "继续";

// 自定义头像：浏览器内先校验，再让用户拖动裁剪成正方形，最后缩到 256px 重编码为 JPEG 上传。
// 前端就把图处理好，后端不必收原始文件（省掉 multipart 依赖），也保证存进库的
// 永远是我们自己编码的位图而不是用户原始字节。
const AVATAR_OUT_PX = 256; // 输出正方形的边长
const CROP_VIEW_PX = 280; // 裁剪取景框的显示边长（正方形）
const CROP_MAX_ZOOM = 3;
const AVATAR_MAX_UPLOAD = 10 * 1024 * 1024; // 单文件上限
const AVATAR_MIN_SIDE = 256; // 原图最短边下限：不小于输出边长，保证永远不会被放大
const AVATAR_MAX_PIXELS = 40 * 1000 * 1000; // 原图像素总量上限
const AVATAR_QUALITY = 0.85;

// 对话区背景图：不裁剪，只等比缩到长边不超过 BG_MAX_PX（不放大），重编码为 JPEG。
const BG_MAX_COUNT = 5;
const BG_MAX_PX = 1920;
const BG_MIN_LONG_SIDE = 640; // 长边下限：再小铺在对话区只会糊成一片
const BG_QUALITY = 0.85;
const BG_MAX_UPLOAD = 10 * 1024 * 1024;

// 裁剪用的解码结果放在模块级而不是 data 里：Image 对象不需要（也不该）被 Vue 代理，
// drawImage 直接吃原始对象最稳。
let cropImage = null;

// 选文件后立刻做的校验：返回错误文案，空串表示通过
const fileTypeSizeError = (type, size, maxBytes) => {
  if (!type || !type.startsWith("image/")) return "请选择图片文件（jpg/png/webp 等）";
  if (size > maxBytes)
    return `图片太大（上限 ${Math.round(maxBytes / 1024 / 1024)}MB），请先压缩或换一张`;
  return "";
};

const avatarFileError = (type, size) => fileTypeSizeError(type, size, AVATAR_MAX_UPLOAD);
const backgroundFileError = (type, size) => fileTypeSizeError(type, size, BG_MAX_UPLOAD);

// 解码出真实分辨率后再校验一次
const avatarImageError = (w, h) => {
  if (!w || !h) return "这个文件不是能识别的图片";
  if (Math.min(w, h) < AVATAR_MIN_SIDE)
    return `图片太小（至少 ${AVATAR_MIN_SIDE}×${AVATAR_MIN_SIDE}），放大后会糊`;
  if (w * h > AVATAR_MAX_PIXELS) return "图片分辨率过高，请先缩小再上传";
  return "";
};

const backgroundImageError = (w, h) => {
  if (!w || !h) return "这个文件不是能识别的图片";
  if (Math.max(w, h) < BG_MIN_LONG_SIDE)
    return `图片太小（长边至少 ${BG_MIN_LONG_SIDE}px），铺在对话区会糊`;
  return "";
};

// 等比缩到长边不超过 max，且只缩不放（小图保持原尺寸）
const fitSize = (w, h, max) => {
  if (!w || !h) return { w: 1, h: 1 };
  const scale = Math.min(1, max / Math.max(w, h));
  return { w: Math.max(1, Math.round(w * scale)), h: Math.max(1, Math.round(h * scale)) };
};

// 整张画进画布并重编码为 JPEG 的 data URL。先铺白底：
// 带透明通道的 PNG/WebP 直接转 JPEG，透明处会变成黑块。
const encodeJpeg = (img, w, h, quality) => {
  const canvas = document.createElement("canvas");
  canvas.width = w;
  canvas.height = h;
  const ctx = canvas.getContext("2d");
  ctx.fillStyle = "#fff";
  ctx.fillRect(0, 0, w, h);
  ctx.drawImage(img, 0, 0, w, h);
  return canvas.toDataURL("image/jpeg", quality);
};

// "铺满"取景框所需的基础缩放：取长短边的较大者，保证两个方向都不留空
const coverScale = (w, h, view) => Math.max(view / w, view / h);

// 把偏移限制在"图片始终盖满取景框"的范围内。这一步是正确性的关键：
// 一旦图片边缘跑进取景框内，裁出来就会带空白边。
const clampOffset = (v, drawn, view) => Math.min(0, Math.max(view - drawn, v));

// 取景框状态 → 原图上的取样矩形（纯函数，便于单测）
const cropSourceRect = (natW, natH, view, zoom, x, y) => {
  const s = coverScale(natW, natH, view) * zoom;
  return { sx: -x / s, sy: -y / s, side: view / s };
};

// 以取景框中心为锚点缩放，返回夹好边界的新偏移（纯函数，便于单测）。
// 不锚定的话放大时图片会往左上跑，观感很跳。
const zoomAroundCenter = (natW, natH, view, fromZoom, toZoom, x, y) => {
  const unit = coverScale(natW, natH, view);
  const prev = unit * fromZoom;
  const next = unit * toZoom;
  const cx = (view / 2 - x) / prev; // 取景框中心对应的原图坐标
  const cy = (view / 2 - y) / prev;
  return {
    x: clampOffset(view / 2 - cx * next, natW * next, view),
    y: clampOffset(view / 2 - cy * next, natH * next, view),
  };
};

const readAsDataURL = (file) =>
  new Promise((resolve, reject) => {
    const reader = new FileReader();
    reader.onerror = () => reject(new Error("read-failed"));
    reader.onload = () => resolve(reader.result);
    reader.readAsDataURL(file);
  });

const loadImage = (src) =>
  new Promise((resolve, reject) => {
    const img = new Image();
    img.onload = () => resolve(img);
    img.onerror = () => reject(new Error("decode-failed"));
    img.src = src;
  });

const emptyCharForm = () => ({
  name: "",
  appearance: "",
  personality: "",
  speech_style: "",
  backstory: "",
  avatar: "",
  // 对话区背景图（data URL 数组）。放在表单里是必须的：新建角色时还没有 id、
  // 没法立即上传，而且面板是整体提交的，漏了它就会把背景一次性清空。
  backgrounds: [],
});

// 探索模式下对用户隐藏、也不允许改写的三个字段（与后端 character_gen.HIDDEN_FIELDS 一致）
const LOCKED_FIELDS = ["personality", "speech_style", "backstory"];

// "我的设定"（用户本人）。全局单行，与角色无关；三项都可以留空
const emptyProfile = () => ({ name: "", identity: "", appearance: "", avatar: "" });

// "世界设定"。全局一份，与角色/会话无关；四项都可以留空。
// terms 是词库：[{term, meaning}]，顺序就是注入提示词的顺序。
const emptyWorld = () => ({ name: "", description: "", rules: "", terms: [] });

const emptyGenerator = () => ({
  hint: "",
  mode: "open", // open = 全部直接展示；explore = 只公开姓名与外观
  busy: false,
  error: "",
  draftId: null, // 服务端草稿 id：探索模式下隐藏的字段只存在服务端
});

// 用工厂函数而不是到处写字面量：漏一个键就会出现"某状态下少个字段"的怪问题
// （之前 charSaved 初始化没和表单默认值对齐，面板一打开就显示"未保存"）
const emptyCharModal = () => ({
  visible: false,
  editingId: null,
  form: emptyCharForm(),
  gen: emptyGenerator(),
  locked: false,
  // 保存失败要在弹窗里说：底部错误条只在会话打开时渲染，新建角色时它根本不在
  saveError: "",
});


// 对话滚动容器：ChatArea.vue 挂载后写进来（原来走组件实例的 refs.chatBox）
let chatBoxEl = null;

export function setChatBox(el) {
  chatBoxEl = el;
}

// ---- 状态（原 data()）----
export const store = reactive({
      MODES,
      mode: "character_chat",
      models: [],
      currentModel: "",
      modelWarning: "",
      // 是否禁用思考模式（全局偏好，存库；模型不支持思考时这个开关不起作用）
      disableThinking: false,
      characters: [],
      sessions: [],
      expandedChars: {},
      activeSessionId: null,
      activeSession: null,
      activeByMode: {}, // 各模式各自打开的会话 id，切换模式 Tab 时用来恢复
      messages: [],
      input: "",
      streaming: false,
      streamText: "",
      thinkPhase: false,
      abortCtrl: null,
      stopped: false,
      error: "",
      sideCollapsed: false,
      panelCollapsed: false,
      charForm: emptyCharForm(),
      // 当前会话角色的三个隐藏字段是否锁定（决定面板显示字段还是锁定占位块）
      charLocked: false,
      charModal: emptyCharModal(),
      newSessionModal: { visible: false, characterId: null, title: "" },
      renaming: false,
      renameText: "",
      editingId: null,
      editForm: {
        content: "",
        scenario: "",
        hasScenario: false,
        keepScenario: null,
        contentLabel: "消息内容",
        contentPlaceholder: "",
        contentHint: "",
      },
      deleteMenuId: null,
      lastFailedUser: null,
      confirmBox: { visible: false, text: "", resolve: null },
      showArchived: false,
      memoryData: { content: "", message_count: 0, updated_at: null, compress_failed: false },
      memoryText: "",
      genFields: [],
      genDefaults: {},
      genForm: {},
      // 最近一次保存（或载入）后的快照，用来判断面板里是否有"未保存"的修改。
      // 初值必须与上面各表单的初值一致，否则还没载入任何会话就会被判成"已修改"
      genSaved: {},
      charSaved: emptyCharForm(),
      memorySaved: "",
      // "还原"键的两次点击状态：第一次只是武装，再点一次才真的回退
      revertArm: { gen: false, char: false, profile: false, memory: false, world: false },
      // 头像校验/裁剪的就地提示（底部错误条在没打开会话时不渲染，不能承担这个角色）
      avatarError: "",
      // 右侧面板各分区的收起状态（true = 已折叠）。纯界面偏好，不持久化
      panelTab: "gen", // 右侧面板当前显示哪个标签：gen / world / char / profile / memory
      // 会话内搜索：关键词与当前命中序号（0 基）。命中位置由 searchPlan 现算，不另存
      searchQuery: "",
      searchIndex: 0,
      // 我的设定：`profile` 是服务端最近一次确认的状态（消息区显示头像与名字用它），
      // `profileForm` 是正在编辑的表单，两者不一致就是"未保存"
      profile: emptyProfile(),
      profileForm: emptyProfile(),
      // 预设库（同一张表里 id>1 的行）与下拉当前选中项。载入预设只填表单、不直接落库，
      // 仍然走底部"保存当前配置"，所以载入后会出现"未保存"提示
      profilePresets: [],
      presetPick: "",
      presetError: "",
      // 世界设定：全局一份，三种模式都注入提示词（名称只给自己看、不进提示词）。
      // 与"我的设定"同样的两份：`world` 是服务端确认过的状态，`worldForm` 是正在编辑的表单
      world: emptyWorld(),
      worldForm: emptyWorld(),
      // 各输入框的字数上限。与后端 app/limits.py 一致，init() 时用 /api/limits 覆盖，
      // 这里的默认值只是兜底（拿不到接口也不至于没有限制）
      limits: {
        message: 2000, scenario: 2000, name: 20, appearance: 600, personality: 600,
        speech_style: 600, backstory: 1200, genre: 60, extra: 500, hint: 200,
        memory: 2000, title: 40, user_name: 20, identity: 300, user_appearance: 600,
        world_name: 40, world_description: 2000, world_rules: 2000, world_term: 30,
        world_term_meaning: 150, world_terms_max: 30,
      },
      // 对话区背景：图片、当前第几张、上限、就地提示
      bgImages: [],
      bgIndex: 0,
      // 临时关掉背景显示（不持久化：切会话或刷新后恢复），见 10.32
      bgHidden: false,
      bgMax: BG_MAX_COUNT,
      bgError: "",
      bgBusy: false,
      // 拖动排序时的状态：正在拖的是哪一处列表的第几张、当前悬停在哪一张上。
      // 注意别把字段名取成与方法同名（如 bgDragOver）——data 与方法共用一个命名空间，
      // 字段会盖住方法，模板里的事件处理器就会变成"调用一个对象"。
      bgDrag: { target: null, index: null },
      bgHover: { target: null, index: null },
      crop: {
        visible: false,
        target: "modal",
        src: "",
        view: CROP_VIEW_PX,
        natW: 0,
        natH: 0,
        zoom: 1,
        maxZoom: CROP_MAX_ZOOM,
        x: 0,
        y: 0,
        dragging: false,
      },
      tagDraft: {},
});

// ---- 方法（原 methods）----
Object.assign(store, {
    // 把失败响应统一转成 Error，并带上状态码：
    // 调用方据此区分“服务端明确拒绝（如角色已删除）”与“连接中断”，提示才不会误导
    async httpError(resp) {
      let msg = `请求失败（${resp.status}）`;
      try {
        const j = await resp.json();
        if (j.detail) msg = typeof j.detail === "string" ? j.detail : JSON.stringify(j.detail);
      } catch (e) {}
      const err = new Error(msg);
      err.httpStatus = resp.status;
      return err;
    },

    async api(path, opts = {}) {
      const resp = await fetch(path, opts);
      if (!resp.ok) throw await store.httpError(resp);
      return resp.json();
    },

    jsonOpts(method, body) {
      return {
        method,
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(body),
      };
    },

    // 字数提示用的两个小工具：输入框右下角显示 已用/上限，接近上限时变色。
    // 真正的拦截由 maxlength（前端）与 schemas 的 max_length（后端 422）负责，
    // 这里只负责显示
    len(value) {
      return (value || "").length;
    },
    isNear(value, max) {
      return !!max && (value || "").length >= max * 0.9;
    },

    // 消息上方那一行显示的"说话人"：角色两模式下模型消息用角色名、用户消息用"我的设定"
    // 里的名字；自由情境模式两边都没有名字（那一行只剩时间）
    msgName(m) {
      if (!store.activeChar) return "";
      return m.role === "assistant" ? store.activeChar.name : store.profile.name || "";
    },

    // 消息的时间。created_at 存的就是本地时间、格式固定为 "2026-09-21T12:34:45"
    // （database.now() 用 isoformat(timespec="seconds")），所以直接切片比 new Date()
    // 再格式化更稳：不走时区解析、不依赖浏览器对 ISO 串的解释，老数据也不会解析失败
    timeOf(m) {
      const s = (m && m.created_at) || "";
      return s.length >= 19 ? s.slice(11, 19) : "";
    },
    fullTimeOf(m) {
      const s = (m && m.created_at) || "";
      return s ? s.replace("T", " ") : "";
    },

    // 标签页兜底：切到没有该标签的会话或模式（自由情境没有角色设定、未选会话没有记忆）
    // 时回到"生成要求"，否则面板会是一片空白
    fixPanelTab() {
      const hasChar = !!(store.activeSession && store.activeSession.character);
      if (store.panelTab === "char" && !hasChar) store.panelTab = "gen";
      if (store.panelTab === "memory" && !store.memoryScope) store.panelTab = "gen";
    },

    // 键顺序无关的快照比对：重建表单后键序可能不同，直接 JSON.stringify 会误判为已修改
    sameSnapshot(a, b) {
      const keys = (o) =>
        Object.keys(o || {})
          .filter((k) => o[k] !== undefined)
          .sort();
      const ka = keys(a);
      const kb = keys(b);
      if (ka.length !== kb.length || ka.some((k, i) => k !== kb[i])) return false;
      return ka.every((k) => JSON.stringify(a[k]) === JSON.stringify(b[k]));
    },

    snapshot(o) {
      return JSON.parse(JSON.stringify(o || {}));
    },

    disarmRevert(section) {
      clearTimeout(revertTimers[section]);
      delete revertTimers[section];
      store.revertArm[section] = false;
    },

    // 还原键：第一次点击只"武装"（按钮变成确认字样），再点一次才真的回退，避免误触丢改动
    armRevert(section) {
      if (store.revertArm[section]) {
        store.revertSection(section);
        return;
      }
      store.revertArm[section] = true;
      clearTimeout(revertTimers[section]);
      // 几秒内没有第二次点击就自动解除，免得一直停在"待确认"状态
      revertTimers[section] = setTimeout(() => store.disarmRevert(section), 5000);
    },

    // 回退到最近一次保存（或载入）时的快照；没保存过的会话即回到默认值
    revertSection(section) {
      store.disarmRevert(section);
      if (section === "gen") store.genForm = store.snapshot(store.genSaved);
      else if (section === "char") store.charForm = store.snapshot(store.charSaved);
      else if (section === "profile") store.profileForm = store.snapshot(store.profile);
      else if (section === "world") store.worldForm = store.snapshot(store.world);
      else if (section === "memory") store.memoryText = store.memorySaved;
    },

    onDocumentClick() {
      // 删除菜单与触发它的按钮都做了 stopPropagation，能走到这里就说明点的是别处
      store.deleteMenuId = null;
    },

    onDocumentKeydown(e) {
      if (e.key !== "Escape") return;
      // 裁剪弹窗叠在最上层，Esc 先关它
      if (store.crop.visible) {
        store.cancelCrop();
        return;
      }
      store.deleteMenuId = null;
      if (store.editingId !== null) store.cancelEdit();
    },

    cancelEdit() {
      store.editingId = null;
    },

    ask(text) {
      return new Promise((resolve) => {
        store.confirmBox = { visible: true, text, resolve };
      });
    },

    answerConfirm(val) {
      store.confirmBox.visible = false;
      if (store.confirmBox.resolve) store.confirmBox.resolve(val);
    },

    // SSE 用 POST，EventSource 不支持，改用 fetch + ReadableStream 手动解析
    async ssePost(url, body, handlers, signal) {
      const opts = store.jsonOpts("POST", body);
      if (signal) opts.signal = signal;
      const resp = await fetch(url, opts);
      if (!resp.ok) throw await store.httpError(resp);
      const reader = resp.body.getReader();
      const decoder = new TextDecoder();
      let buf = "";
      while (true) {
        const { done, value } = await reader.read();
        if (done) break;
        buf += decoder.decode(value, { stream: true });
        let idx;
        while ((idx = buf.indexOf("\n\n")) >= 0) {
          const block = buf.slice(0, idx);
          buf = buf.slice(idx + 2);
          let event = "message";
          let data = "";
          for (const line of block.split("\n")) {
            if (line.startsWith("event:")) event = line.slice(6).trim();
            else if (line.startsWith("data:")) data += line.slice(5).trim();
          }
          if (data && handlers[event]) handlers[event](JSON.parse(data));
        }
      }
    },

    async init() {
      let ollamaOk = true;
      // 字数上限以后端为准；拿不到就沿用 data 里的兜底值，不影响使用
      try {
        store.limits = await store.api("/api/limits");
      } catch (e) {
        /* 用兜底值 */
      }
      // "我的设定"是全局的，只在启动时取一次；保存后由 saveProfile 刷新
      try {
        const p = await store.api("/api/profile");
        store.profile = p;
        store.profileForm = store.snapshot(p);
        await store.loadPresets();
      } catch (e) {
        /* 拿不到就用空值，面板里照样能填 */
      }
      // "世界设定"同样是全局的，也只在启动时取一次；保存后由 saveWorld 刷新
      try {
        const w = await store.api("/api/world");
        store.world = w;
        store.worldForm = store.snapshot(w);
      } catch (e) {
        /* 拿不到就用空值 */
      }
      try {
        store.models = await store.api("/api/models");
      } catch (e) {
        ollamaOk = false;
        store.modelWarning = "无法连接 Ollama，请确认服务已启动";
      }
      try {
        const s = await store.api("/api/settings");
        store.currentModel = s.model;
        store.disableThinking = !!s.disable_thinking;
      } catch (e) {
        store.error = e.message;
        return;
      }
      if (ollamaOk) {
        if (store.models.length === 0) {
          store.modelWarning = "Ollama 中还没有可用模型，请先拉取一个";
        } else if (!store.currentModel) {
          // 首次使用不预选模型：给一句提示，但不拦着用户浏览界面
          store.modelWarning = "还没有选择模型，生成前请先在左边选一个";
        } else if (!store.models.some((m) => m.name === store.currentModel)) {
          store.modelWarning = `所选模型 ${store.currentModel} 未安装，请在右侧重新选择`;
        }
      }
      await store.refreshCharacters();
      await store.refreshSessions();
      try {
        const form = await store.api("/api/gen-settings");
        store.genFields = form.fields;
        store.genDefaults = form.defaults;
      } catch (e) {
        /* 表单定义拉取失败时生成要求区留空 */
      }
    },

    async refreshCharacters() {
      store.characters = await store.api("/api/characters");
    },

    async refreshSessions() {
      // 只拉当前模式的会话：角色对话与角色情境的会话列表相互隔离，互不可见
      store.sessions = await store.api(`/api/sessions?mode=${store.mode}`);
    },

    async switchMode(key) {
      if (key === store.mode) return;
      if (store.streaming) {
        store.error = "正在生成中，请等待完成后再切换模式";
        return;
      }
      store.activeByMode[store.mode] = store.activeSessionId; // 记住本模式正看哪条
      store.mode = key;
      store.error = "";
      try {
        await store.refreshSessions();
      } catch (e) {
        store.error = e.message;
        return;
      }
      const remembered = store.activeByMode[key];
      if (remembered && store.sessions.some((s) => s.id === remembered)) {
        await store.openSession(remembered); // 切回来仍停在原来那条会话
        return;
      }
      // 该模式没有可恢复的会话：清空对话区，另一模式的会话不残留
      store.activeSessionId = null;
      store.activeSession = null;
      store.messages = [];
      store.showArchived = false;
      store.resetBackgrounds();
      store.initGenForm();
    },

    fieldsOf(mode) {
      return store.genFields[mode] || [];
    },

    initGenForm() {
      const mode = store.activeSession ? store.activeSession.mode : store.mode;
      const merged = { ...(store.genDefaults[mode] || {}) };
      const stored = (store.activeSession && store.activeSession.gen_settings) || {};
      for (const k of Object.keys(stored)) {
        if (stored[k] !== null && stored[k] !== "") merged[k] = stored[k];
      }
      for (const f of store.fieldsOf(mode)) {
        if (f.type === "tags" && !Array.isArray(merged[f.key])) merged[f.key] = [];
        if (f.type === "radio" && !merged[f.key]) {
          merged[f.key] = (f.options && f.options[0] && f.options[0][0]) || "";
        }
      }
      store.genForm = merged;
      store.genSaved = store.snapshot(merged);
    },

    toggleTag(key, tag) {
      const list = store.genForm[key] || [];
      const i = list.indexOf(tag);
      if (i >= 0) list.splice(i, 1);
      else list.push(tag);
      store.genForm[key] = [...list];
    },

    addTag(key) {
      const draft = (store.tagDraft[key] || "").trim();
      if (draft && !(store.genForm[key] || []).includes(draft)) {
        store.genForm[key] = [...(store.genForm[key] || []), draft];
      }
      store.tagDraft[key] = "";
    },

    removeTag(key, tag) {
      store.genForm[key] = (store.genForm[key] || []).filter((t) => t !== tag);
    },

    customTags(field) {
      return (store.genForm[field.key] || []).filter(
        (t) => !(field.presets || []).includes(t)
      );
    },

    async saveGenSettings() {
      const payload = {};
      for (const f of store.fieldsOf(store.activeSession.mode)) {
        payload[f.key] = store.genForm[f.key];
      }
      try {
        store.activeSession = await store.api(
          `/api/sessions/${store.activeSessionId}`,
          store.jsonOpts("PATCH", { gen_settings: payload })
        );
        store.initGenForm();
      } catch (e) {
        store.error = e.message;
      }
    },

    // 把带标记的全文切成 [{type, text}]。标记之外的裸文本按话语算——模型常把台词
    // 写在第一个标记之前，丢掉它就等于把角色说的话吞了（与 parser.py 的容错一致）
    segmentsOf(m) {
      const text = m.content || "";
      const segs = [];
      SEGMENT_RE.lastIndex = 0;
      let last = 0;
      let match;
      let sawTag = false;
      while ((match = SEGMENT_RE.exec(text)) !== null) {
        sawTag = true;
        const head = text.slice(last, match.index).trim();
        if (head) segs.push({ type: "dialog", text: head });
        const body = match[2].trim();
        if (body) {
          segs.push({ type: isScenarioTag(match[1]) ? "scenario" : "dialog", text: body });
        }
        last = SEGMENT_RE.lastIndex;
      }
      const tail = text.slice(last).trim();
      if (tail) segs.push({ type: "dialog", text: tail });
      if (segs.length) return segs;
      // 只有空标记：没有可渲染的内容，别把裸标记当正文显示
      return sawTag ? [] : [{ type: "dialog", text }];
    },

    // 一条消息要渲染（也参与搜索）的文本块。MULTI 走分段，其余是"情境 + 正文"。
    // 渲染与搜索共用它，两边的切法才不会不一致（否则命中数会对不上看到的字）
    textParts(m) {
      if (m.scenario === "MULTI") {
        return store.segmentsOf(m).map((s) => ({ kind: s.type, text: s.text }));
      }
      const out = [];
      if (m.scenario) out.push({ kind: "scenario", text: m.scenario });
      out.push({ kind: "text", text: m.content || "" });
      return out;
    },

    // 模板用的分块：有搜索计划就取它（带命中标记），否则退回纯文本块
    partsOf(m) {
      const planned = store.searchPlan.parts[m.id];
      if (planned) return planned;
      return store.textParts(m).map((p) => ({
        kind: p.kind,
        pieces: [{ text: p.text, hit: false }],
      }));
    },

    // 关键词按字面搜，正则元字符要转义，否则搜 "a.b" 会命中 "axb"
    escapeRegExp(s) {
      return s.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
    },

    // ---- 会话内搜索 ----
    searchNext() {
      store.searchStep(1);
    },
    searchPrev() {
      store.searchStep(-1);
    },
    searchStep(step) {
      const total = store.searchTotal;
      if (!total) return;
      // 环形移动：走到头再点就绕回另一端
      store.searchIndex = ((store.searchIndex + step) % total + total) % total;
      store.scrollToHit();
    },
    clearSearch() {
      store.searchQuery = "";
      store.searchIndex = 0;
    },
    // 把当前命中滚到视野中间。等 Vue 把 .current 类挂上去之后再找元素
    scrollToHit() {
      nextTick(() => {
        const el = document.querySelector(".search-hit.current");
        if (el) el.scrollIntoView({ block: "center", behavior: "smooth" });
      });
    },

    toggleChar(id) {
      store.expandedChars[id] = !store.expandedChars[id];
    },

    sessionsOf(cid) {
      return store.sessions.filter((s) => s.character_id === cid);
    },

    async openSession(id) {
      if (store.streaming) {
        store.error = "正在生成中，请等待完成后再切换会话";
        return;
      }
      try {
        const session = await store.api(`/api/sessions/${id}`);
        if (session.mode !== store.mode) {
          // 列表已按模式过滤，正常点不到这里；防御性拦截，避免跨模式查看
          store.error = `该会话属于「${MODES[session.mode].label}」模式，请切换模式后再打开`;
          return;
        }
        store.activeSession = session;
        store.activeSessionId = id;
        store.activeByMode[session.mode] = id;
        store.messages = await store.api(`/api/sessions/${id}/messages`);
        // 背景图单独取（只有角色两模式有）
        if (session.character_id) await store.loadBackgrounds(session.character_id);
        else store.resetBackgrounds();
        if (session.character_id) {
          store.expandedChars[session.character_id] = true;
        }
        store.error = "";
        store.scrollBottom();
      } catch (e) {
        store.error = e.message;
      }
    },

    async newSession() {
      if (store.mode === "free_scenario") {
        try {
          const s = await store.api(
            "/api/sessions",
            store.jsonOpts("POST", { mode: "free_scenario" })
          );
          await store.refreshSessions();
          await store.openSession(s.id);
        } catch (e) {
          store.error = e.message;
        }
        return;
      }
      if (store.characters.length === 0) {
        store.openCharacterModal();
        return;
      }
      store.newSessionModal = {
        visible: true,
        characterId: store.characters[0].id,
        title: "",
      };
    },

    async confirmNewSession() {
      try {
        const s = await store.api(
          "/api/sessions",
          store.jsonOpts("POST", {
            mode: store.mode,
            character_id: store.newSessionModal.characterId,
            title: store.newSessionModal.title,
          })
        );
        store.newSessionModal.visible = false;
        await store.refreshSessions();
        await store.openSession(s.id);
      } catch (e) {
        store.error = e.message;
      }
    },

    async createSessionForCharacter(cid) {
      try {
        const s = await store.api(
          "/api/sessions",
          store.jsonOpts("POST", { mode: store.mode, character_id: cid })
        );
        await store.refreshSessions();
        await store.openSession(s.id);
      } catch (e) {
        store.error = e.message;
      }
    },

    async removeSession(s) {
      if (store.streaming) {
        store.error = "正在生成中，请等待完成后再删除会话";
        return;
      }
      if (!(await store.ask(`删除会话「${s.title}」？其全部消息将一并删除。`))) return;
      try {
        await store.api(`/api/sessions/${s.id}`, { method: "DELETE" });
        if (store.activeSessionId === s.id) {
          store.activeSessionId = null;
          store.activeSession = null;
          store.messages = [];
          store.resetBackgrounds();
        }
        await store.refreshSessions();
      } catch (e) {
        store.error = e.message;
      }
    },

    // 选文件后先校验，通过就进裁剪；任何一步不过都在头像处就地提示
    // （不用底部错误条：它在没打开会话时不渲染，用户会看不到原因）
    // target: "modal"（新建/编辑角色弹窗）或 "panel"（右侧面板角色设定）
    async pickAvatar(e, target) {
      const file = e.target.files && e.target.files[0];
      e.target.value = ""; // 清掉，才能连续两次选同一个文件
      if (!file) return;
      store.avatarError = "";
      const early = avatarFileError(file.type, file.size);
      if (early) {
        store.avatarError = early;
        return;
      }
      let src;
      try {
        src = await readAsDataURL(file);
      } catch (err) {
        store.avatarError = "读取文件失败，请重试";
        return;
      }
      let img;
      try {
        img = await loadImage(src);
      } catch (err) {
        store.avatarError = "这个文件不是能识别的图片";
        return;
      }
      const later = avatarImageError(img.naturalWidth, img.naturalHeight);
      if (later) {
        store.avatarError = later;
        return;
      }
      cropImage = img;
      const natW = img.naturalWidth;
      const natH = img.naturalHeight;
      const s = coverScale(natW, natH, CROP_VIEW_PX);
      store.crop = {
        visible: true,
        target,
        src,
        view: CROP_VIEW_PX,
        natW,
        natH,
        zoom: 1,
        maxZoom: CROP_MAX_ZOOM,
        // 初始居中
        x: (CROP_VIEW_PX - natW * s) / 2,
        y: (CROP_VIEW_PX - natH * s) / 2,
        dragging: false,
      };
    },

    // 拖动：记录按下时的指针位置与图片偏移，移动时按位移换算新偏移并夹住边界
    cropDown(e) {
      const c = store.crop;
      if (!c.visible) return;
      c.dragging = true;
      store._drag = { px: e.clientX, py: e.clientY, x0: c.x, y0: c.y };
      e.currentTarget.setPointerCapture?.(e.pointerId);
    },

    cropMove(e) {
      const c = store.crop;
      if (!c.dragging || !store._drag) return;
      const d = store._drag;
      const s = coverScale(c.natW, c.natH, c.view) * c.zoom;
      c.x = clampOffset(d.x0 + (e.clientX - d.px), c.natW * s, c.view);
      c.y = clampOffset(d.y0 + (e.clientY - d.py), c.natH * s, c.view);
    },

    cropUp(e) {
      store.crop.dragging = false;
      store._drag = null;
      e.currentTarget.releasePointerCapture?.(e.pointerId);
    },

    // 缩放时以取景框中心为锚点，图片不会突然跳走
    setCropZoom(z) {
      const c = store.crop;
      if (!c.visible) return;
      const to = Math.min(c.maxZoom, Math.max(1, Number(z) || 1));
      const next = zoomAroundCenter(c.natW, c.natH, c.view, c.zoom, to, c.x, c.y);
      c.zoom = to;
      c.x = next.x;
      c.y = next.y;
    },

    cancelCrop() {
      store.crop.visible = false;
      cropImage = null;
    },

    confirmCrop() {
      const c = store.crop;
      if (!cropImage) {
        store.cancelCrop();
        return;
      }
      const { sx, sy, side } = cropSourceRect(c.natW, c.natH, c.view, c.zoom, c.x, c.y);
      const canvas = document.createElement("canvas");
      canvas.width = AVATAR_OUT_PX;
      canvas.height = AVATAR_OUT_PX;
      const ctx = canvas.getContext("2d");
      // 先铺白底：带透明通道的 PNG/WebP 转 JPEG 时，透明处会变黑块
      ctx.fillStyle = "#fff";
      ctx.fillRect(0, 0, AVATAR_OUT_PX, AVATAR_OUT_PX);
      try {
        ctx.drawImage(cropImage, sx, sy, side, side, 0, 0, AVATAR_OUT_PX, AVATAR_OUT_PX);
        const dataUrl = canvas.toDataURL("image/jpeg", AVATAR_QUALITY);
        store.avatarForm(c.target).avatar = dataUrl;
        store.avatarError = "";
        store.cancelCrop();
      } catch (err) {
        // 引用了外部资源（或跨域）的图片会污染画布，toDataURL 会抛 SecurityError
        store.avatarError = "这张图片无法处理（可能引用了外部资源），请换一张";
      }
    },

    // 头像归属的表单对象：角色弹窗 / 右侧面板角色设定 / 我的设定（用户资料）。
    // 裁剪与移除都通过它写回，不必在每处再写一遍 target 判断
    avatarForm(target) {
      if (target === "profile") return store.profileForm;
      return target === "modal" ? store.charModal.form : store.charForm;
    },

    clearAvatar(target) {
      store.avatarError = "";
      store.avatarForm(target).avatar = "";
    },

    // ---------- 对话区背景图 ----------
    resetBackgrounds() {
      store.bgImages = [];
      store.bgIndex = 0;
      // "关闭背景"是临时的：换会话/角色就恢复显示
      store.bgHidden = false;
      store.bgError = "";
    },

    // 载入当前会话角色的背景图。syncForm=true 时同步写进右侧面板的 charForm——
    // 否则在面板里一按保存就会把这组图整体提交成空。
    async loadBackgrounds(cid, syncForm = true) {
      try {
        const resp = await store.api(`/api/characters/${cid}/backgrounds`);
        store.bgImages = resp.images || [];
        store.bgMax = resp.max || BG_MAX_COUNT;
        if (store.bgIndex >= store.bgImages.length) store.bgIndex = 0;
        if (syncForm && store.activeChar && store.activeChar.id === cid) {
          store.charForm.backgrounds = [...store.bgImages];
          // 只同步基线里的 backgrounds，不要整体重拍快照：
          // 那会把面板里其它尚未保存的改动一并标记成"已保存"
          if (store.charSaved) store.charSaved.backgrounds = [...store.bgImages];
        }
      } catch (e) {
        store.bgImages = [];
      }
    },

    // 角色弹窗里可能要编辑的不是当前会话的角色，所以单独取
    async loadModalBackgrounds(cid) {
      try {
        const resp = await store.api(`/api/characters/${cid}/backgrounds`);
        if (store.charModal.editingId === cid) {
          store.charModal.form.backgrounds = resp.images || [];
          store.bgMax = resp.max || BG_MAX_COUNT;
        }
      } catch (e) {
        /* 取不到就按空处理，保存时以表单为准 */
      }
    },

    prevBg() {
      const n = store.bgImages.length;
      if (n > 1) store.bgIndex = (store.bgIndex - 1 + n) % n;
    },

    nextBg() {
      const n = store.bgImages.length;
      if (n > 1) store.bgIndex = (store.bgIndex + 1) % n;
    },

    bgList(target) {
      return (target === "modal" ? store.charModal.form.backgrounds : store.charForm.backgrounds) || [];
    },

    setBgList(target, list) {
      if (target === "modal") store.charModal.form.backgrounds = list;
      else store.charForm.backgrounds = list;
    },

    // target: "modal"（角色弹窗）或 "panel"（右侧面板角色设定）
    async addBackgrounds(e, target) {
      const files = Array.from(e.target.files || []);
      e.target.value = ""; // 清掉，才能连续两次选同一个文件
      if (!files.length) return;
      const list = store.bgList(target);
      const room = store.bgMax - list.length;
      store.bgError = "";
      if (room <= 0) {
        store.bgError = `最多只能放 ${store.bgMax} 张背景图`;
        return;
      }
      // 一次性可能选好几张大图，逐张缩放编码会占用一段时间，
      // 期间给个"处理中"状态并把按钮禁掉，避免重复点击
      store.bgBusy = true;
      const added = [];
      let problem = "";
      try {
        for (const file of files.slice(0, room)) {
          const early = backgroundFileError(file.type, file.size);
          if (early) {
            problem = early;
            continue;
          }
          let img;
          try {
            img = await loadImage(await readAsDataURL(file));
          } catch (err) {
            problem = "有文件不是能识别的图片，已跳过";
            continue;
          }
          const later = backgroundImageError(img.naturalWidth, img.naturalHeight);
          if (later) {
            problem = later;
            continue;
          }
          const { w, h } = fitSize(img.naturalWidth, img.naturalHeight, BG_MAX_PX);
          try {
            added.push(encodeJpeg(img, w, h, BG_QUALITY));
          } catch (err) {
            problem = "有图片无法处理（可能引用了外部资源），已跳过";
          }
          await new Promise((r) => setTimeout(r, 0)); // 让出主线程，界面不至于卡住
        }
      } finally {
        store.bgBusy = false;
      }
      if (added.length) store.setBgList(target, [...list, ...added]);
      if (files.length > room) problem = `最多 ${store.bgMax} 张，多选的已忽略`;
      store.bgError = problem;
    },

    removeBackground(target, i) {
      const list = [...store.bgList(target)];
      list.splice(i, 1);
      store.setBgList(target, list);
      store.bgError = "";
    },

    // 背景排序：把第 from 张移到第 to 张的位置。顺序就是对话里上一张/下一张的顺序，
    // 第一张是打开会话时默认显示的那张
    moveBackground(target, from, to) {
      const list = [...store.bgList(target)];
      if (from === to || from < 0 || to < 0 || from >= list.length || to >= list.length) return;
      const [item] = list.splice(from, 1);
      list.splice(to, 0, item);
      store.setBgList(target, list);
      store.bgError = "";
    },

    bgDragStart(e, target, i) {
      store.bgDrag = { target, index: i };
      store.bgHover = { target: null, index: null };
      if (e.dataTransfer) {
        e.dataTransfer.effectAllowed = "move";
        // Firefox 不设数据就不启动拖拽
        try {
          e.dataTransfer.setData("text/plain", String(i));
        } catch (err) {
          /* 忽略：设不上也不影响其它浏览器 */
        }
      }
    },

    bgDragOver(e, target, i) {
      if (store.bgDrag.index === null || store.bgDrag.target !== target) return;
      store.bgHover = { target, index: i };
    },

    bgDrop(e, target, i) {
      // 先把状态取出来再清空：moveBackground 里要用
      const drag = store.bgDrag;
      store.bgDragEnd();
      if (!drag.target || drag.target !== target || drag.index === null) return;
      store.moveBackground(target, drag.index, i);
    },

    bgDragEnd() {
      store.bgDrag = { target: null, index: null };
      store.bgHover = { target: null, index: null };
    },

    bgDragging(target, i) {
      return store.bgDrag.target === target && store.bgDrag.index === i;
    },

    bgDropTarget(target, i) {
      return store.bgHover.target === target && store.bgHover.index === i;
    },

    openCharacterModal(c = null) {
      store.avatarError = ""; // 换一个角色就清掉上一次的提示
      store.bgError = "";
      if (c) {
        store.charModal = {
          ...emptyCharModal(),
          visible: true,
          editingId: c.id,
          form: {
            name: c.name,
            appearance: c.appearance,
            personality: c.personality || "",
            speech_style: c.speech_style || "",
            backstory: c.backstory || "",
            avatar: c.avatar || "",
            backgrounds: [], // 背景图不随角色列表下发，下面单独取
          },
          locked: !!c.locked,
        };
        store.loadModalBackgrounds(c.id);
      } else {
        store.charModal = { ...emptyCharModal(), visible: true };
      }
    },

    // 让模型生成一份角色设定。开放模式把结果填进表单；探索模式只有姓名与外观，
    // 另外三项留在服务端草稿里（前端拿不到），保存时以草稿为准
    async generateCharacter() {
      const gen = store.charModal.gen;
      if (gen.busy) return;
      gen.busy = true;
      gen.error = "";
      try {
        const r = await store.api(
          "/api/characters/generate",
          store.jsonOpts("POST", { hint: gen.hint, mode: gen.mode })
        );
        store.avatarError = "";
        store.charModal.form.name = r.name || "";
        store.charModal.form.appearance = r.appearance || "";
        for (const k of LOCKED_FIELDS) {
          store.charModal.form[k] = r[k] || "";
        }
        store.charModal.locked = !!r.locked;
        gen.draftId = r.draft_id;
      } catch (e) {
        gen.error = e.message;
      } finally {
        gen.busy = false;
      }
    },

    // 换一个 / 换模式：清掉草稿与那三个字段，回到"重新生成"的状态
    resetGeneratedDraft() {
      const gen = store.charModal.gen;
      gen.draftId = null;
      gen.error = "";
      store.charModal.locked = false;
      for (const k of LOCKED_FIELDS) store.charModal.form[k] = "";
    },

    // 公开角色设定：单向、永久。确认后本地同步这三个字段，避免出现假的"未保存"
    async unlockCharacter(target) {
      const cid = target === "panel"
        ? (store.activeChar && store.activeChar.id)
        : store.charModal.editingId;
      if (!cid) return;
      const ok = await store.ask(
        "公开后将永久取消锁定，性格 / 语言风格 / 背景故事会显示出来并可以修改，且无法再锁回去。确定要公开吗？"
      );
      if (!ok) return;
      try {
        const c = await store.api(`/api/characters/${cid}/unlock`, { method: "POST" });
        const i = store.characters.findIndex((x) => x.id === cid);
        if (i >= 0) store.characters[i] = { ...store.characters[i], ...c };
        if (target === "panel") {
          for (const k of LOCKED_FIELDS) {
            store.charForm[k] = c[k] || "";
            // 快照一起写：这两处都是刚拿到的原值，不该被判成"未保存"
            store.charSaved[k] = c[k] || "";
          }
          store.charLocked = false;
          if (store.activeSession && store.activeSession.character) {
            Object.assign(store.activeSession.character, c);
          }
        } else {
          for (const k of LOCKED_FIELDS) store.charModal.form[k] = c[k] || "";
          store.charModal.locked = false;
        }
      } catch (e) {
        store.error = e.message;
      }
    },

    async saveCharacterModal() {
      // 背景图不属于角色接口的字段，单独整体提交，所以先从角色载荷里摘出去
      const { backgrounds, ...charPayload } = store.charModal.form;
      store.charModal.saveError = "";
      if (store.charModal.gen.draftId) charPayload.draft_id = store.charModal.gen.draftId;
      try {
        let cid = store.charModal.editingId;
        if (cid) {
          delete charPayload.draft_id; // 编辑已有角色时不该带草稿
          await store.api(`/api/characters/${cid}`, store.jsonOpts("PUT", charPayload));
        } else {
          const c = await store.api("/api/characters", store.jsonOpts("POST", charPayload));
          cid = c.id;
          store.expandedChars[c.id] = true;
        }
        await store.api(
          `/api/characters/${cid}/backgrounds`,
          store.jsonOpts("PUT", { images: backgrounds || [] })
        );
        store.charModal.visible = false;
        await store.afterCharacterChange();
      } catch (e) {
        // 弹窗里就地提示：例如应用重启导致探索模式的草稿失效，用户需要知道要重新生成
        store.charModal.saveError = e.message;
        store.error = e.message;
      }
    },

    async saveCharacterDrawer() {
      const { backgrounds, ...charPayload } = store.charForm;
      try {
        const cid = store.activeSession.character.id;
        await store.api(`/api/characters/${cid}`, store.jsonOpts("PUT", charPayload));
        await store.api(
          `/api/characters/${cid}/backgrounds`,
          store.jsonOpts("PUT", { images: backgrounds || [] })
        );
        await store.afterCharacterChange();
      } catch (e) {
        store.error = e.message;
      }
    },

    // 面板底部那个"保存当前配置"：几个标签各管各的数据，按钮只按当前标签转发。
    // 这样底部只要一个常驻按钮，不必在每个标签内容里各放一个
    saveCurrentTab() {
      if (store.panelTab === "world") return store.saveWorld();
      if (store.panelTab === "char") return store.saveCharacterDrawer();
      if (store.panelTab === "profile") return store.saveProfile();
      if (store.panelTab === "memory") return store.saveMemory();
      return store.saveGenSettings();
    },

    // ---- 世界设定（全局一份，三种模式都注入） ----
    // 加一条空词条：界面上先出现输入框，名词留空的行保存时由后端丢弃
    addTerm() {
      if (store.worldForm.terms.length >= store.limits.world_terms_max) return;
      store.worldForm.terms.push({ term: "", meaning: "" });
    },

    removeTerm(index) {
      store.worldForm.terms.splice(index, 1);
    },

    // 我的设定：整体覆盖式保存；成功后以服务端返回为准刷新基线与显示用的 profile
    async saveProfile() {
      try {
        const p = await store.api("/api/profile", store.jsonOpts("PUT", store.profileForm));
        store.profile = p;
        store.profileForm = store.snapshot(p);
      } catch (e) {
        store.error = e.message;
      }
    },

    // 世界设定：整体覆盖式保存。服务端会把"名词为空的行"丢掉、把文本 strip 掉，
    // 所以用返回结果刷新表单——用户会看到那行空词条自己消失了
    async saveWorld() {
      try {
        const w = await store.api("/api/world", store.jsonOpts("PUT", store.worldForm));
        store.world = w;
        store.worldForm = store.snapshot(w);
      } catch (e) {
        store.error = e.message;
      }
    },

    // ---- 我的设定的预设库 ----
    async loadPresets() {
      try {
        store.profilePresets = await store.api("/api/profile/presets");
        // 选中的那条可能已被删掉（比如另开一个标签页删的），清掉选择
        if (store.presetPick && !store.profilePresets.some((p) => p.id === store.presetPick)) {
          store.presetPick = "";
        }
      } catch (e) {
        store.presetError = e.message;
      }
    },

    // 载入预设：只把这四项填进表单。用户确认无误后再点底部保存——
    // 直接覆盖当前设定会让"选错了"变成不可撤销
    loadPreset() {
      store.presetError = "";
      if (!store.presetPick) return;
      const p = store.profilePresets.find((x) => x.id === store.presetPick);
      if (!p) return;
      store.profileForm = {
        name: p.name || "",
        identity: p.identity || "",
        appearance: p.appearance || "",
        avatar: p.avatar || "",
      };
    },

    async savePreset() {
      store.presetError = "";
      try {
        const p = await store.api(
          "/api/profile/presets",
          store.jsonOpts("POST", store.profileForm)
        );
        await store.loadPresets();
        store.presetPick = p.id; // 存完直接选中它，方便继续改或删
      } catch (e) {
        store.presetError = e.message;
      }
    },

    async removePreset() {
      const p = store.profilePresets.find((x) => x.id === store.presetPick);
      if (!p) return;
      if (!(await store.ask(`删除预设「${p.name}」？当前使用的设定不受影响。`))) return;
      store.presetError = "";
      try {
        await store.api(`/api/profile/presets/${p.id}`, { method: "DELETE" });
        store.presetPick = "";
        await store.loadPresets();
      } catch (e) {
        store.presetError = e.message;
      }
    },

    async removeCharacterFromModal() {
      const id = store.charModal.editingId;
      const c = store.characters.find((x) => x.id === id);
      if (!c) return;
      if (!(await store.ask(`删除角色「${c.name}」？其记忆将删除，已有会话保留但无法继续生成。`))) return;
      store.charModal.visible = false;
      await store.deleteCharacter(id);
    },

    async deleteCharacter(id) {
      try {
        await store.api(`/api/characters/${id}`, { method: "DELETE" });
        await store.afterCharacterChange();
      } catch (e) {
        store.error = e.message;
      }
    },

    async afterCharacterChange() {
      await store.refreshCharacters();
      await store.refreshSessions();
      if (store.activeSessionId) {
        store.activeSession = await store.api(`/api/sessions/${store.activeSessionId}`);
      }
      // 角色可能刚被保存或删除，背景图跟着刷新（没有角色就清空）
      if (store.activeChar) await store.loadBackgrounds(store.activeChar.id);
      else store.resetBackgrounds();
    },

    startRename() {
      if (!store.activeSession || store.renaming) return;
      store.renameText = store.activeSession.title;
      store.renaming = true;
      nextTick(() => {
        const el = document.querySelector(".title-input");
        if (el) el.focus();
      });
    },

    async saveRename() {
      if (!store.renaming) return;
      store.renaming = false;
      const title = store.renameText.trim();
      if (!title || title === store.activeSession.title) return;
      try {
        store.activeSession = await store.api(
          `/api/sessions/${store.activeSessionId}`,
          store.jsonOpts("PATCH", { title })
        );
        await store.refreshSessions();
      } catch (e) {
        store.error = e.message;
      }
    },

    async switchModel() {
      if (!store.currentModel) return;
      try {
        const s = await store.api(
          "/api/settings",
          store.jsonOpts("PUT", { model: store.currentModel })
        );
        store.currentModel = s.model;
        store.modelWarning = "";
      } catch (e) {
        // 顶栏直接提示并回退：底部错误条只在打开会话时才渲染，不能依赖它
        store.modelWarning = e.message;
        try {
          const s = await store.api("/api/settings");
          store.currentModel = s.model;
        } catch (_) {
          /* 读取失败就保持原选择 */
        }
      }
    },

    // 顶栏的思考模式开关。失败时同样在顶栏提示并回退，理由同 switchModel
    async toggleThinking() {
      try {
        const s = await store.api(
          "/api/settings",
          store.jsonOpts("PUT", { disable_thinking: !store.disableThinking })
        );
        store.disableThinking = !!s.disable_thinking;
        store.modelWarning = "";
      } catch (e) {
        store.modelWarning = e.message;
        try {
          const s = await store.api("/api/settings");
          store.disableThinking = !!s.disable_thinking;
        } catch (_) {
          /* 保持原状态 */
        }
      }
    },

    async loadMemory() {
      if (!store.memoryScope) return;
      const { type, id } = store.memoryScope;
      try {
        store.memoryData = await store.api(`/api/memories/${type}/${id}`);
        store.memoryText = store.memoryData.content;
        store.memorySaved = store.memoryText;
      } catch (e) {
        /* scope 不存在等场景：面板留空 */
      }
    },

    async saveMemory() {
      const { type, id } = store.memoryScope;
      try {
        store.memoryData = await store.api(
          `/api/memories/${type}/${id}`,
          store.jsonOpts("PUT", { content: store.memoryText })
        );
        store.memoryText = store.memoryData.content;
        store.memorySaved = store.memoryText; // 保存成功后"未保存"标识随之消失
      } catch (e) {
        store.error = e.message;
      }
    },

    async refreshMessages() {
      if (!store.activeSessionId || store.streaming) return;
      try {
        store.messages = await store.api(
          `/api/sessions/${store.activeSessionId}/messages`
        );
      } catch (e) {
        /* 会话已删等场景：静默 */
      }
    },

    scheduleMemoryRefresh() {
      // 压缩是后台任务，done 后延迟拉取一次归档状态与记忆
      const sid = store.activeSessionId;
      setTimeout(async () => {
        if (store.activeSessionId !== sid) return;
        await store.refreshMessages();
        if (store.memoryScope) await store.loadMemory();
      }, 12000);
    },

    beginStream() {
      store.stopped = false;
      store.abortCtrl = new AbortController();
      store.streaming = true;
      store.streamText = "";
      store.thinkPhase = false;
    },

    // 收尾流式状态；返回本次是否被用户主动停止
    endStream() {
      const stopped = store.stopped;
      store.streaming = false;
      store.streamText = "";
      store.thinkPhase = false;
      store.abortCtrl = null;
      store.stopped = false;
      store.scheduleMemoryRefresh();
      return stopped;
    },

    stop() {
      if (!store.streaming || !store.abortCtrl) return;
      store.stopped = true;
      store.abortCtrl.abort();
    },

    // 服务端在连接断开后才会把已生成的部分落库，轮询几次等它写进去
    async syncAfterStop() {
      const before = store.messages.length;
      for (let i = 0; i < 8; i++) {
        await new Promise((r) => setTimeout(r, 250));
        await store.refreshMessages();
        if (store.messages.length > before) return;
      }
    },

    canSendText(text) {
      return !!text && !store.streaming && !!store.activeSession && !store.orphanActive;
    },

    async send() {
      const text = store.input.trim();
      if (!store.canSendText(text)) return;
      store.input = ""; // 通过校验后才清空，发不出去时不会把草稿弄丢
      await store.runSend(text);
    },

    // 自由情境的"继续"：等价于自动发一条"继续"，让模型接着上一条回复往下写。
    // 不动输入框——里面可能是用户正在写的草稿，不能被这个按钮吞掉。
    async continueGeneration() {
      if (!store.canContinue) return;
      await store.runSend(CONTINUE_PROMPT);
    },

    // 发消息与"继续"共用的发送路径，避免两处各写一遍流式处理而走偏
    async runSend(text) {
      store.error = "";
      store.lastFailedUser = null;
      store.beginStream();
      store.messages.push({ id: "tmp-user", role: "user", content: text });
      store.scrollBottom();
      let userId = null;
      let failed = false;
      try {
        await store.ssePost(
          `/api/sessions/${store.activeSessionId}/chat`,
          { message: text },
          {
            meta: (d) => {
              userId = d.message_id;
              const m = store.messages.find((x) => x.id === "tmp-user");
              if (m) m.id = d.message_id;
            },
            status: (d) => {
              store.thinkPhase = d.phase === "thinking";
            },
            delta: (d) => {
              store.thinkPhase = false;
              store.streamText += d.text;
              store.scrollBottom();
            },
            done: (d) => {
              store.messages.push({
                id: d.message_id,
                role: "assistant",
                content: d.content,
                scenario: d.scenario,
              });
            },
            error: (d) => {
              store.error = d.message;
              if (userId) store.lastFailedUser = { id: userId, text };
            },
          },
          store.abortCtrl.signal
        );
      } catch (e) {
        // 用户点「停止」导致的中断不算错误：部分内容已由服务端落库
        if (!store.stopped) {
          store.error = e.httpStatus ? e.message : `连接中断：${e.message}`;
          if (userId) store.lastFailedUser = { id: userId, text };
          // user 消息压根没落库（如角色已删除被拒），界面上那条是乐观渲染的，需要撤掉
          else failed = true;
        }
      }
      const stopped = store.endStream();
      if (stopped) await store.syncAfterStop();
      else if (failed) await store.refreshMessages();
      await store.refreshSessions();
      store.scrollBottom();
    },

    async retryFailed() {
      const { id, text } = store.lastFailedUser;
      store.lastFailedUser = null;
      store.error = "";
      try {
        await store.api(`/api/messages/${id}`, { method: "DELETE" });
        store.messages = store.messages.filter((m) => m.id !== id);
      } catch (e) {
        store.error = e.message;
        return;
      }
      store.input = text;
      await store.send();
    },

    async copyText(m) {
      try {
        await navigator.clipboard.writeText(m.content);
      } catch (e) {
        store.error = "复制失败，请手动选择复制";
      }
    },

    startEdit(m) {
      store.deleteMenuId = null;
      store.editingId = m.id;
      const mode = store.activeSession.mode;
      const isMulti = m.scenario === "MULTI";
      // 角色情境模式：无论当前有没有情境都给出情境输入框，方便手动补上
      const hasScenario = mode === "character_scenario";
      store.editForm = {
        content: m.content,
        scenario: m.scenario && !isMulti ? m.scenario : "",
        hasScenario,
        keepScenario: isMulti ? "MULTI" : null,
        contentLabel: hasScenario ? "话语内容" : "消息内容",
        contentPlaceholder: hasScenario ? "这一幕里该角色说出的话" : "消息正文",
        contentHint: isMulti
          ? "自由情境的消息用 [SCENARIO] 标记情境说明、[DIALOG] 标记对话，保留这两个标记即可继续分段显示。"
          : "",
      };
      // 打开后按内容把输入框撑到实际高度，长消息不会被塞进一个小框里
      nextTick(() => {
        document
          .querySelectorAll(".edit-modal textarea")
          .forEach((el) => store.autoGrowEl(el));
      });
    },

    autoGrow(e) {
      store.autoGrowEl(e.target);
    },

    autoGrowEl(el) {
      if (!el) return;
      el.style.height = "auto";
      el.style.height = Math.min(el.scrollHeight + 2, 460) + "px";
    },

    async saveEdit() {
      // 编辑弹窗在消息列表之外，靠 editingId 找回目标消息
      const m = store.messages.find((x) => x.id === store.editingId);
      if (!m) {
        store.editingId = null;
        return;
      }
      const payload = { content: store.editForm.content.trim() };
      if (store.editForm.hasScenario) {
        payload.scenario = store.editForm.scenario.trim() || null; // 清空即不再显示情境块
      } else {
        payload.scenario = store.editForm.keepScenario || null;
      }
      try {
        const updated = await store.api(
          `/api/messages/${m.id}`,
          store.jsonOpts("PUT", payload)
        );
        const idx = store.messages.findIndex((x) => x.id === m.id);
        if (idx >= 0) store.messages.splice(idx, 1, updated);
        store.editingId = null;
        await store.refreshSessions();
      } catch (e) {
        store.error = e.message;
      }
    },

    async removeMessage(m, cascade) {
      store.deleteMenuId = null;
      const tip = cascade
        ? "将删除该消息及其之后的所有消息，继续？"
        : "确认删除这条消息？";
      if (!(await store.ask(tip))) return;
      try {
        await store.api(`/api/messages/${m.id}?cascade=${cascade}`, { method: "DELETE" });
        if (cascade) {
          const idx = store.messages.findIndex((x) => x.id === m.id);
          store.messages = store.messages.slice(0, idx);
        } else {
          store.messages = store.messages.filter((x) => x.id !== m.id);
        }
        await store.refreshSessions();
      } catch (e) {
        store.error = e.message;
      }
    },

    async regenerate(m) {
      if (store.streaming) {
        store.error = "正在生成中，请稍候";
        return;
      }
      // 用户消息本身是这一轮的输入，必须保留，只删它之后的；assistant 消息则连它一起替换
      const isUser = m.role === "user";
      const tip = isUser
        ? "将为这条消息重新生成回复，其后的消息会被删除，继续？"
        : "重新生成将删除该消息及其之后的所有消息，继续？";
      if (!(await store.ask(tip))) return;
      store.deleteMenuId = null;
      store.error = "";
      store.lastFailedUser = null;
      const idx = store.messages.findIndex((x) => x.id === m.id);
      store.messages = store.messages.slice(0, isUser ? idx + 1 : idx);
      store.beginStream();
      store.scrollBottom();
      let failed = false;
      try {
        await store.ssePost(`/api/messages/${m.id}/regenerate`, {}, {
          status: (d) => {
            store.thinkPhase = d.phase === "thinking";
          },
          delta: (d) => {
            store.thinkPhase = false;
            store.streamText += d.text;
            store.scrollBottom();
          },
          done: (d) => {
            store.messages.push({
              id: d.message_id,
              role: "assistant",
              content: d.content,
              scenario: d.scenario,
            });
          },
          error: (d) => {
            store.error = d.message;
          },
        }, store.abortCtrl.signal);
      } catch (e) {
        if (!store.stopped) {
          failed = true;
          store.error = e.httpStatus ? e.message : `连接中断：${e.message}`;
        }
      }
      const stopped = store.endStream();
      if (stopped) await store.syncAfterStop();
      // 服务端校验不过时不会删消息，这里拉一次把上面乐观截断的界面还原回来
      else if (failed) await store.refreshMessages();
      await store.refreshSessions();
      store.scrollBottom();
    },

    scrollBottom() {
      nextTick(() => {
        const el = chatBoxEl;
        if (el) el.scrollTop = el.scrollHeight;
      });
    },

    // 发送键右侧的"↓"键：平滑滚到最新消息。与 scrollBottom() 分开是有意的——
    // 那个是流式输出时"跟着新内容即时贴底"，每来一小段就调用一次，必须瞬时、
    // 不能有动画，否则会一直追着一段没走完的平滑滚动跑。
    jumpToBottom() {
      const el = chatBoxEl;
      if (!el) return;
      if (typeof el.scrollTo === "function") {
        el.scrollTo({ top: el.scrollHeight, behavior: "smooth" });
      } else {
        el.scrollTop = el.scrollHeight; // 兜底：极老的浏览器不支持带 options 的 scrollTo
      }
    },
});

// ---- 计算属性（原 computed）----
store.isCharacterMode = computed(() => {
      return MODES[store.mode].character;
});

    // 当前会话绑定的角色（自由情境没有）。消息区的头像与名字都用它，省得模板里重复长条件
store.activeChar = computed(() => {
      return (store.activeSession && store.activeSession.character) || null;
});

    // 顶栏"思考模式"开关：只有思考型模型才让它可点
store.currentModelInfo = computed(() => {
      return store.models.find((m) => m.name === store.currentModel) || null;
});

store.currentModelSupportsThinking = computed(() => {
      if (!store.currentModel) return false; // 还没选模型：开关没有对象，置灰
      const info = store.currentModelInfo;
      return info ? !!info.thinking : true; // 模型列表还没到手时不置灰，免得闪一下
});

store.thinkToggleTitle = computed(() => {
      if (!store.currentModel) return "还没有选择模型，先在左边选一个";
      if (!store.currentModelSupportsThinking) return "当前模型不支持思考模式，这个开关对它没有作用";
      return store.disableThinking
        ? "思考模式已关闭，点击开启"
        : "思考模式已开启，点击关闭（能明显加快回复）";
});

    // 对话区背景：只有角色两模式、且该角色有背景图时才有；自由情境、未选会话、
    // 角色已删除都回落到空白背景。被"关闭背景"临时关掉时同样回落到空白
store.chatBgUrl = computed(() => {
      if (!store.activeChar || !store.bgImages.length || store.bgHidden) return "";
      const i = Math.min(Math.max(store.bgIndex, 0), store.bgImages.length - 1);
      return store.bgImages[i] || "";
});

    // 背景条：只要该角色有图就出现。**不能**跟着背景是否显示来决定——否则一关掉，
    // 连"重新显示"的按钮都没了，只能靠切会话或刷新恢复
store.showBgBar = computed(() => {
      return !!store.activeChar && store.bgImages.length > 0;
});

    // 裁剪弹窗里那张图的位移与缩放。transform 里 translate 在前、scale 在后，
    // 所以 (x, y) 就是"缩放后图片左上角"在取景框坐标系里的位置
store.cropImageStyle = computed(() => {
      const c = store.crop;
      const s = c.natW && c.natH ? coverScale(c.natW, c.natH, c.view) * c.zoom : 1;
      return {
        width: c.natW + "px",
        height: c.natH + "px",
        transform: `translate(${c.x}px, ${c.y}px) scale(${s})`,
        transformOrigin: "0 0",
      };
});

    // 当前取景框落在原图上的实际像素边长。放大后它可能小于输出边长，
    // 那就意味着要放大（画面变糊）——只在小于输出尺寸时提示，平时不打扰
store.cropSamplePx = computed(() => {
      const c = store.crop;
      if (!c.natW || !c.natH) return 0;
      const { side } = cropSourceRect(c.natW, c.natH, c.view, c.zoom, c.x, c.y);
      return Math.round(side);
});

store.isFreeScenario = computed(() => {
      return !!store.activeSession && store.activeSession.mode === "free_scenario";
});

    // "继续"要有上一条回复可接才可用；生成中、角色已删时也不给用
store.canContinue = computed(() => {
      return (
        store.isFreeScenario &&
        !store.streaming &&
        !store.orphanActive &&
        store.messages.some((m) => m.role === "assistant")
      );
});

store.freeSessions = computed(() => {
      return store.sessions.filter((s) => s.mode === "free_scenario");
});

store.orphanSessions = computed(() => {
      return store.sessions.filter((s) => s.mode !== "free_scenario" && !s.character_id);
});

store.orphanActive = computed(() => {
      return (
        !!store.activeSession &&
        store.activeSession.mode !== "free_scenario" &&
        !store.activeSession.character
      );
});

store.memoryScope = computed(() => {
      if (!store.activeSession) return null;
      if (store.activeSession.mode === "free_scenario") {
        return { type: "session", id: store.activeSession.id, label: "会话记忆" };
      }
      if (store.activeSession.character) {
        return {
          type: "character",
          id: store.activeSession.character.id,
          label: "角色记忆",
        };
      }
      return null;
});

store.archivedCount = computed(() => {
      return store.messages.filter((m) => m.archived).length;
});

    // 面板三块的"未保存"判定：各自与保存时的快照比对，改回原样就自动消失
store.genDirty = computed(() => {
      return !store.sameSnapshot(store.genForm, store.genSaved);
});

store.charDirty = computed(() => {
      return !store.sameSnapshot(store.charForm, store.charSaved);
});

store.memoryDirty = computed(() => {
      return store.memoryText !== store.memorySaved;
});

store.profileDirty = computed(() => {
      return !store.sameSnapshot(store.profileForm, store.profile);
});

store.worldDirty = computed(() => {
      return !store.sameSnapshot(store.worldForm, store.world);
});

store.anyDirty = computed(() => {
      return (
        store.genDirty || store.charDirty || store.profileDirty ||
        store.memoryDirty || store.worldDirty
      );
});

    // 当前标签是否有未保存改动：面板底部那一行"未保存 / 还原"按它显示。
    // 键名与 armRevert / revertArm 的取值一致（gen / world / char / profile / memory）
store.activeTabDirty = computed(() => {
      if (store.panelTab === "world") return store.worldDirty;
      if (store.panelTab === "char") return store.charDirty;
      if (store.panelTab === "profile") return store.profileDirty;
      if (store.panelTab === "memory") return store.memoryDirty;
      return store.genDirty;
});

    // 面板底部的保存键几个标签共用：只有角色设定要求姓名非空（后端也要求）；
    // 世界设定与"我的设定"一样可以全空保存
store.saveDisabled = computed(() => {
      return store.panelTab === "char" && !store.charForm.name.trim();
});

    // 用户消息要不要显示头像那一列：只在角色两模式（有 activeChar）、
    // 且用户至少设了名字或头像时才渲染，否则会留一个空白列
store.showUserSide = computed(() => {
      return !!store.activeChar && !!(store.profile.avatar || store.profile.name);
});

store.displayMessages = computed(() => {
      return store.showArchived
        ? store.messages
        : store.messages.filter((m) => !m.archived);
});

    // 会话内搜索的计划：把每条消息按"渲染块"切开，标出每块里命中的片段以及它们的
    // 全局序号。一次算完，模板按 id 取用——渲染时不必再关心"这是第几个命中"。
    // 只搜当前显示出来的消息（已归档且未展开的不参与），与用户看到的一致
store.searchPlan = computed(() => {
      const plan = { parts: {}, total: 0 };
      if (!store.searchQuery.trim()) return plan;
      // 转义后按正则搜：这样大小写不敏感，且命中位置直接是原串下标
      // （先用 toLowerCase 再 indexOf 在少数 Unicode 上会因长度变化而错位）
      const re = new RegExp(store.escapeRegExp(store.searchQuery.trim()), "gi");
      let n = 0;
      for (const m of store.displayMessages) {
        const parts = [];
        for (const p of store.textParts(m)) {
          const pieces = [];
          let last = 0;
          let hit;
          re.lastIndex = 0;
          while ((hit = re.exec(p.text)) !== null) {
            if (hit[0] === "") break; // 空匹配会死循环，理论上不会发生
            if (hit.index > last) pieces.push({ text: p.text.slice(last, hit.index), hit: false });
            pieces.push({ text: hit[0], hit: true, index: n++ });
            last = hit.index + hit[0].length;
          }
          pieces.push({ text: p.text.slice(last), hit: false });
          parts.push({ kind: p.kind, pieces });
        }
        plan.parts[m.id] = parts;
      }
      plan.total = n;
      return plan;
});

store.searchTotal = computed(() => {
      return store.searchPlan.total;
});

// ---- 侦听器（原 watch）----
// 注册在 App.vue 的 setup 里（那里有组件实例，卸载时自动清理）。
// 键支持点号路径（如 charModal.gen.mode），取值方式与 Vue 的 watch 一致。
export const watchDefs = {
    activeSessionId() {
      // 切换会话时右侧面板保持展开，只把内容刷新成新会话的
      store.showArchived = false;
      store.loadMemory();
      store.initGenForm();
    },
    activeSession(s) {
      if (s && s.character) {
        const c = s.character;
        store.charForm = {
          name: c.name,
          appearance: c.appearance,
          // 锁定的角色拿不到这三项（接口就不下发），留空即可：保存时后端也会忽略它们
          personality: c.personality || "",
          speech_style: c.speech_style || "",
          backstory: c.backstory || "",
          // 必须带上：面板是整体提交的，漏了它就会在保存角色设定时把头像一个不剩地清掉
          avatar: c.avatar || "",
          // 背景图不随角色下发，由 loadBackgrounds() 填充
          backgrounds: [],
        };
        store.charLocked = !!c.locked;
      } else {
        store.charForm = emptyCharForm();
        store.charLocked = false;
      }
      store.charSaved = store.snapshot(store.charForm); // 重新载入即视为已保存
      store.fixPanelTab();
    },
    // 生成前换了模式，之前那份结果就不适用了：探索模式的结果前端压根没拿到隐藏字段，
    // 开放模式的结果也不该直接变成"锁定"。清掉草稿，请用户重新生成
    "charModal.gen.mode"() {
      if (store.charModal.gen.draftId) store.resetGeneratedDraft();
    },
    panelCollapsed(collapsed) {      // 展开面板时重新拉一次记忆，避免收起期间的数据过期；
      // 但用户手上有未保存的编辑时不能覆盖掉
      if (!collapsed && !store.memoryDirty) store.loadMemory();
    },
    // 改动被撤销（标识消失）时顺手解除还原键的武装，免得下次单击就误回退
    genDirty(v) {
      if (!v) store.disarmRevert("gen");
    },
    charDirty(v) {
      if (!v) store.disarmRevert("char");
    },
    profileDirty(v) {
      if (!v) store.disarmRevert("profile");
    },
    // 换了关键词就从头开始数，并直接把第一处命中滚到眼前
    searchQuery() {
      store.searchIndex = 0;
      store.scrollToHit();
    },
    // 命中数变少（消息被编辑/删除、归档折叠）时把序号夹回范围内
    searchTotal(v) {
      if (store.searchIndex >= v) store.searchIndex = 0;
    },
    memoryDirty(v) {
      if (!v) store.disarmRevert("memory");
    },
};

export function registerWatchers() {
  for (const [path, handler] of Object.entries(watchDefs)) {
    const get = () => path.split(".").reduce((o, k) => (o == null ? o : o[k]), store);
    watch(get, handler);
  }
}

// ---- 生命周期（原 mounted / beforeUnmount）----
export async function initApp() {
    store.init();
    // 点空白处 / 按 Esc 关掉消息删除菜单与编辑弹窗，避免它们只能靠再次点按钮关闭
    document.addEventListener("click", store.onDocumentClick);
    document.addEventListener("keydown", store.onDocumentKeydown);
}

export function disposeApp() {
    document.removeEventListener("click", store.onDocumentClick);
    document.removeEventListener("keydown", store.onDocumentKeydown);
}
