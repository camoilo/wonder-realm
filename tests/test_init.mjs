/**
 * 初始化的容错测试（Node 直接跑，不需要浏览器）。
 *
 * 背景（DEVELOPMENT 10.48 / 10.49）：用户清空数据库时应用正在运行，接口全部 500，
 * 而 init() 把 /api/settings 放在第一步，它一失败就 return —— 后面的模型列表、角色
 * 列表、会话列表一个都不拉，界面看起来就是"前端连不上后端"。这里把 /api/settings
 * 打成 500，断言"其余步骤照样完成"，并且失败的那一步要显示出来。
 *
 * 注意：store.js import 了 vue，所以跑这个测试前要先装前端依赖（cd frontend && npm install）。
 * 跑法：node tests/test_init.mjs
 */
import { store } from "../frontend/src/store.js";

globalThis.document = {
  querySelector: () => null,
  querySelectorAll: () => [],
  addEventListener: () => {},
  removeEventListener: () => {},
};
globalThis.window = globalThis;

const FAILED = [];
function check(name, got, want) {
  const ok = JSON.stringify(got) === JSON.stringify(want);
  if (!ok) FAILED.push(name);
  console.log(`[${ok ? "ok" : "FAIL"}] ${name}: ${JSON.stringify(got)}` +
              (ok ? "" : ` != ${JSON.stringify(want)}`));
}

const MODELS = [{ name: "m1", thinking: false }];
const CHARACTERS = [{ id: 1, name: "甲", avatar: "", locked: 0, backgrounds: [] }];
let settingsFails = true;

function json(body, status = 200) {
  return {
    ok: status < 400,
    status,
    json: async () => body,
  };
}

globalThis.fetch = async (url) => {
  const path = String(url).split("?")[0];
  switch (path) {
    case "/api/limits": return json({});
    case "/api/profile": return json({ name: "", identity: "", appearance: "", avatar: "" });
    case "/api/profile/presets": return json([]);
    case "/api/world": return json({ name: "", description: "", rules: "", terms: [] });
    case "/api/models": return json(MODELS);
    case "/api/characters": return json(CHARACTERS);
    case "/api/sessions": return json([]);
    case "/api/gen-settings": return json({ fields: [], defaults: {} });
    case "/api/settings":
      return settingsFails
        ? json({ detail: "unable to open database file" }, 500)
        : json({ model: "m1", memory_model: "", disable_thinking: false });
    default:
      throw new Error(`测试桩没覆盖 ${url}`);
  }
};

// ---- 场景一：设置接口 500（就是删库后的样子） ----
let threw = "";
try {
  await store.init();
} catch (e) {
  threw = e.message;
}
check("初始化本身不抛异常（initApp 没 await 它）", threw, "");
check("设置挂了，角色列表照样加载", store.characters.length, 1);
check("设置挂了，角色名也拿到了", store.characters[0].name, "甲");
check("设置挂了，会话列表照样加载", store.sessions, []);
check("设置挂了，模型列表照样加载", store.models.length, 1);
check("设置读不到时当前模型保持为空", store.currentModel, "");
check("顶栏提示指出了没加载上的一步", store.initError, "初始化未完成：设置没加载上");
check("底部错误条带上了后端原话", store.error.includes("unable to open database file"), true);

// ---- 场景二：一切正常时不留任何提示 ----
settingsFails = false;
store.initError = "";
store.error = "";
store.characters = [];
store.sessions = [];
store.currentModel = "";
await store.init();
check("正常时没有初始化提示", store.initError, "");
check("正常时没有错误条", store.error, "");
check("正常时读到当前模型", store.currentModel, "m1");
check("正常时角色列表在", store.characters.length, 1);

console.log();
if (FAILED.length) {
  console.log(`失败 ${FAILED.length} 项：${JSON.stringify(FAILED)}`);
  process.exit(1);
}
console.log("初始化容错用例全部通过");
