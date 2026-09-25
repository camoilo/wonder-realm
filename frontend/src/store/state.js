// reactive 状态（原来的 data()）+ 对话滚动容器的引用。
//
// 状态**集中在这里**（一个 reactive 对象），行为按领域分在 store/*.js 里：这样"有哪些状态"只有一个地方要看，
// 而"做什么"按功能分文件。各领域模块只 import 这个文件。
import { reactive } from "vue";
import { ATTR_TYPES, BG_MAX_COUNT, CROP_MAX_ZOOM, CROP_VIEW_PX, MODES, emptyCharForm, emptyCharModal, emptyProfile, emptyWorld } from "./helpers.js";

export const store = reactive({
      MODES,
      ATTR_TYPES,
      mode: "chat",
      models: [],
      currentModel: "",
      modelWarning: "",
      ollamaBusy: false,   // 「重试」正在让后端再确保一次 Ollama
      disableThinking: false,
      characters: [],
      sessions: [],
      expandedChars: {},
      activeSessionId: null,
      activeSession: null,
      activeByMode: {}, // 各模式各自打开的会话 id，切换模式 Tab 时用来恢复
      messages: [],
      input: "",
      // 沉浸模式输入区左边那一栏（场景 / 动作 / 心理），可选；其它模式不使用
      inputScenario: "",
      streaming: false,
      streamText: "",
      thinkPhase: false,
      abortCtrl: null,
      stopped: false,
      error: "",
      // 初始化时有哪几步没加载上（顶栏常驻提示用；底部错误条只在打开会话时才渲染）
      initError: "",
      sideCollapsed: false,
      // 右侧面板**默认收起**：没打开会话时它本来就没内容（整条只有图标列），而"打开会话就自己
      // 展开"会很顶人。要看设定点一下图标列即可。
      panelCollapsed: true,
      // 手机断点（≤640px）下的抽屉 / 底部面板 / 更多菜单开关；桌面端不使用
      mobileSideOpen: false,
      mobilePanelOpen: false,
      mobileMoreOpen: false,
      // 会话内搜索框的展开开关：**双端都用**——顶栏只留一个放大镜，
      // 点它才弹出搜索条（桌面端也一样，见 DEVELOPMENT §9.6）
      searchOpen: false,
      // 「隐藏对话」：把消息流整块藏起来、只留背景（三个模式通用，见 §9）
      chatHidden: false,
      // 手机端顶栏那个全屏键的状态（浏览器全屏，桌面端没有这个键）
      isFullscreen: false,
      theme: "light", // 当前主题 light / dark；"选一个存本地"见 store/ui.js 的 setTheme
      // 桌面端（Electron 壳，见 DEVELOPMENT §3.3）：壳在 preload 里注入 window.dshDesktop，
      // 网页端（含手机浏览器）没有它 —— 于是桌面专属的那两个键根本不会渲染
      isDesktop: false,
      // 壳用的是自绘标题栏（Windows 的 Window Controls Overlay）：顶栏要当拖拽区、
      // 右上角要给系统那三个按钮留宽度（见 DEVELOPMENT 3.3）
      wco: false,
      // 壳把窗口缩成手机尺寸时为 true：页面按窄屏断点走手机布局，桌面专属键隐藏
      desktopPhoneView: false,
      desktopConfigOpen: false, // 「配置」弹出的小面板（标题栏那个 ⚙，见 3.3 / 7.1）
      lanEnabled: false,        // 后端"推送局域网"开关（读 /api/settings 带回）
      lanBusy: false,
      lanUrl: "",               // 局域网地址（壳按网卡算出来给的，用于复制与二维码）
      lanCopied: false,
      firewallCopied: false,    // 「复制防火墙命令」的短暂反馈
      charForm: emptyCharForm(),
      charLocked: false,
      charModal: emptyCharModal(),
      // 附加属性编辑里的就地提示（"给「好感」选个类型"这种），与 presetError 同一个路子
      attrError: "",
      // 顶栏那个附加属性键弹出的下拉是否收起（键永远在顶栏，面板默认不开——它现在是浮层，
      // 默认展开会平白盖住消息）
      attrsCollapsed: true,
      newSessionModal: { visible: false, characterId: null, worldId: null, title: "" },
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
        // 附加属性：从这条消息现有的值初始化（没有的按定义补空行，方便用户直接填）
        attrs: [],
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
      genSaved: {},
      charSaved: emptyCharForm(),
      memorySaved: "",
      // 「还原」的两段式确认（第一次点变"确认还原？"）按区域各自记一个标记：
      // 面板那几页 + 两个编辑弹窗（角色弹窗 / 预设弹窗，见 §9）
      revertArm: {
        gen: false, char: false, profile: false, memory: false, world: false,
        charModal: false, presetModal: false,
      },
      avatarError: "",
      panelTab: "gen", // 右侧面板当前显示哪个标签：gen / world / char / profile / memory
      searchQuery: "",
      searchIndex: 0,
      profile: emptyProfile(),
      profileForm: emptyProfile(),
      profilePresets: [],
      // 当前使用的设定来自哪条预设（空 = 未选择预设），面板那行据此显示名字
      currentPresetId: "",
      presetError: "",
      // 绑定预设的弹窗：左边挑一条、右边看详情，确认后**绑定**（原「载入预设」，见 §2.3/§2.4）。
      // kind 决定这是"我的设定"还是"世界设定"的预设（两种共用这一对弹窗，见 helpers.PRESET_KINDS）
      bindModal: { visible: false, kind: "profile", pick: "" },
      // 编辑预设的弹窗：选要改哪条、也能新建（id=null = 还没落库），删除也在这里；
      // saved 是"打开/切到这条时的快照"，弹窗里的「未保存 / 还原」拿它比
      presetModal: {
        visible: false, kind: "profile", id: null, form: emptyProfile(),
        saved: null, saveError: "",
      },
      world: emptyWorld(),
      worldForm: emptyWorld(),
      worldPresets: [],
      // 当前世界来自哪条世界预设（空 = 未选择预设）
      currentWorldPresetId: "",
      limits: {
        message: 2000, scenario: 2000, name: 20, appearance: 600, personality: 600,
        speech_style: 600, backstory: 1200, genre: 60, extra: 500, hint: 200,
        memory: 2000, title: 40, user_name: 20, user_call_name: 20, identity: 300,
        user_appearance: 600,
        world_name: 40, world_description: 2000, world_rules: 2000, world_term: 30,
        world_term_meaning: 150, world_terms_max: 30,
        attr_name: 20, attr_hint: 200, attr_value: 100, attr_max: 8,
      },
      bgImages: [],
      bgIndex: 0,
      bgHidden: false,
      bgMax: BG_MAX_COUNT,
      bgError: "",
      bgBusy: false,
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

// 对话滚动容器：ChatArea.vue 挂载后写进来（原来走组件实例的 refs.chatBox）
let chatBoxEl = null;

export function setChatBox(el) {
  chatBoxEl = el;
}

export { chatBoxEl };
