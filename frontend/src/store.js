// 前端 store 的汇总入口（barrel）。
//
// 拆成 store/ 下的领域模块后，这里只负责：按顺序 import 它们（副作用是把方法/计算属性挂到 store 上）
// 再把组件需要的东西 re-export 出去 —— 组件的 `import { store } from "../store.js"` 不用改。
//
// 依赖是星形的：各领域模块只 import state.js，barrel 负责把它们组装起来。
import { store } from "./store/state.js";
import { disposeApp, initApp, registerWatchers, watchDefs } from "./store/api.js";
import "./store/session.js";
import "./store/chat.js";
import "./store/search.js";
import "./store/panel.js";
import "./store/character.js";
import "./store/profile.js";
import "./store/ui.js";
import { MODES } from "./store/helpers.js";
import { setChatBox } from "./store/state.js";

export { MODES, disposeApp, initApp, registerWatchers, setChatBox, store, watchDefs };
