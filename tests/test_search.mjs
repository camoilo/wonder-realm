/**
 * 会话内搜索的纯逻辑测试（Node 直接跑，不需要浏览器）。
 *
 * 拆成单文件组件后，逻辑全在 frontend/src/store.js 里（一个 reactive 对象），这里直接 import 它，
 * 像普通对象一样赋值/取值来断言——标记、计数、环形跳转都不必真开浏览器。
 *
 * 注意：store.js import 了 vue，所以跑这个测试前要先装前端依赖（cd frontend && npm install）。
 * 其余 Python 测试都不需要任何前端依赖。
 *
 * 跑法：node tests/test_search.mjs
 */
import { store, watchDefs } from "../frontend/src/store.js";

// scrollToHit 之类的方法会摸 document / window：给最小替身即可
globalThis.document = { querySelector: () => null, querySelectorAll: () => [] };
globalThis.window = globalThis;

const FAILED = [];
function check(name, got, want) {
  const ok = JSON.stringify(got) === JSON.stringify(want);
  if (!ok) FAILED.push(name);
  console.log(`[${ok ? "ok" : "FAIL"}] ${name}: ${JSON.stringify(got)}` +
              (ok ? "" : ` != ${JSON.stringify(want)}`));
}

// ---- 文本切块：渲染与搜索共用同一种切法 ----
const multi = { id: 1, content: "[SCENARIO]雨夜\n[DIALOG]你好", scenario: "MULTI" };
check("MULTI 切成情境+话语两块", store.textParts(multi).map((p) => p.kind), ["scenario", "dialog"]);
check("MULTI 的文本取自分段", store.textParts(multi).map((p) => p.text), ["雨夜", "你好"]);
const plain = { id: 2, content: "普通正文", scenario: "" };
check("非 MULTI 只有正文块", store.textParts(plain).map((p) => p.kind), ["text"]);
const withScen = { id: 3, content: "正文", scenario: "情境" };
check("情境+正文两块", store.textParts(withScen).map((p) => p.kind), ["scenario", "text"]);
check("渲染不含标记本身", store.textParts(multi).some((p) => p.text.includes("SCENARIO")), false);

// ---- 命中标记与全局序号 ----
store.messages = [
  { id: 10, role: "user", content: "今天下雨了，雨很大", scenario: "" },
  { id: 11, role: "assistant", content: "雨停了再说", scenario: "窗外的雨还在下" },
];
store.showArchived = false;
store.searchQuery = "雨";
let parts = store.partsOf(store.messages[0]);
let hits = parts[0].pieces.filter((p) => p.hit);
check("第一条消息命中数", hits.length, 2);
check("命中序号从 0 开始", hits.map((p) => p.index), [0, 1]);
check("命中片段就是关键词", hits.map((p) => p.text), ["雨", "雨"]);
check("非命中片段拼回原文",
      parts[0].pieces.map((p) => p.text).join(""), "今天下雨了，雨很大");
check("全部命中总数", store.searchTotal, 4);
parts = store.partsOf(store.messages[1]);
hits = parts.flatMap((p) => p.pieces.filter((x) => x.hit));
check("第二条消息（含情境）的序号接在后面", hits.map((p) => p.index), [2, 3]);
check("情境块也参与搜索", parts[0].kind, "scenario");

// ---- 大小写不敏感 + 元字符按字面 ----
store.messages = [{ id: 20, role: "user", content: "Hello hello HELLO", scenario: "" }];
store.searchQuery = "hello";
check("大小写不敏感", store.searchTotal, 3);
store.messages = [{ id: 21, role: "user", content: "axb a.b", scenario: "" }];
store.searchQuery = "a.b";
check("元字符按字面匹配", store.searchTotal, 1);
check("元字符命中位置正确",
      store.partsOf(store.messages[0])[0].pieces.filter((p) => p.hit).map((p) => p.text), ["a.b"]);
store.searchQuery = "   ";
check("只有空白视为没有搜索", store.searchTotal, 0);
check("空白时不建计划", Object.keys(store.searchPlan.parts).length, 0);

// ---- 空关键词：仍要能渲染出整段文本 ----
store.searchQuery = "";
parts = store.partsOf(store.messages[0]);
check("空关键词时不标黄", parts[0].pieces.every((p) => !p.hit), true);
check("空关键词时文本完整", parts[0].pieces.map((p) => p.text).join(""), "axb a.b");

// ---- 环形跳转 ----
store.messages = [{ id: 30, role: "user", content: "aaa", scenario: "" }];
store.searchQuery = "a";
store.searchIndex = 0;
check("三处命中", store.searchTotal, 3);
store.searchNext();
check("下一个", store.searchIndex, 1);
store.searchNext();
store.searchNext();
check("到尾再下一个绕回开头", store.searchIndex, 0);
store.searchPrev();
check("到头再上一个绕到末尾", store.searchIndex, 2);
store.searchQuery = "aa";
store.searchIndex = 1;
watchDefs.searchTotal.call(store, 1);
check("命中变少时序号夹回", store.searchIndex, 0);
store.searchIndex = 2;
store.clearSearch();
check("清空搜索", [store.searchQuery, store.searchIndex], ["", 0]);

// ---- 只搜显示中的消息（归档折叠时不参与） ----
store.messages = [
  { id: 40, role: "user", content: "归档里的雨", scenario: "", archived: 1 },
  { id: 41, role: "user", content: "当前的雨", scenario: "" },
];
store.searchQuery = "雨";
store.showArchived = false;
check("归档未展开时不搜", store.searchTotal, 1);
check("序号只算显示中的", store.partsOf(store.messages[1])[0].pieces.filter((p) => p.hit)[0].index, 0);
store.showArchived = true;
check("展开归档后一起搜", store.searchTotal, 2);

console.log();
if (FAILED.length) {
  console.log(`失败 ${FAILED.length} 项：${JSON.stringify(FAILED)}`);
  process.exit(1);
}
console.log("会话内搜索用例全部通过");
