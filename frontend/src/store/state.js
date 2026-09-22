// reactive 状态（原来的 data()）+ 对话滚动容器的引用。
//
// 状态**集中在这里**（一个 reactive 对象），行为按领域分在 store/*.js 里：这样"有哪些状态"只有一个地方要看，
// 而"做什么"按功能分文件。各领域模块只 import 这个文件。
import { reactive } from "vue";
import { BG_MAX_COUNT, CROP_MAX_ZOOM, CROP_VIEW_PX, MODES, emptyCharForm, emptyCharModal, emptyProfile, emptyWorld } from "./helpers.js";

export const store = reactive({
      MODES,
      mode: "chat",
      models: [],
      currentModel: "",
      modelWarning: "",
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
      // 初始化时有哪几步没加载上（顶栏常驻提示用；底部错误条只在打开会话时才渲染）
      initError: "",
      sideCollapsed: false,
      panelCollapsed: false,
      charForm: emptyCharForm(),
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
      genSaved: {},
      charSaved: emptyCharForm(),
      memorySaved: "",
      revertArm: { gen: false, char: false, profile: false, memory: false, world: false },
      avatarError: "",
      panelTab: "gen", // 右侧面板当前显示哪个标签：gen / world / char / profile / memory
      searchQuery: "",
      searchIndex: 0,
      profile: emptyProfile(),
      profileForm: emptyProfile(),
      profilePresets: [],
      presetPick: "",
      presetError: "",
      world: emptyWorld(),
      worldForm: emptyWorld(),
      limits: {
        message: 2000, scenario: 2000, name: 20, appearance: 600, personality: 600,
        speech_style: 600, backstory: 1200, genre: 60, extra: 500, hint: 200,
        memory: 2000, title: 40, user_name: 20, identity: 300, user_appearance: 600,
        world_name: 40, world_description: 2000, world_rules: 2000, world_term: 30,
        world_term_meaning: 150, world_terms_max: 30,
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
