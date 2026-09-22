/**
 * 会话内搜索的纯逻辑测试（Node 直接跑：不需要浏览器，也不需要装任何依赖）。
 *
 * app.js 现在是一个普通的 ES 模块，导出选项对象 appOptions（不再在顶层调用 Vue.createApp）。
 * 这里把它的 data / computed / methods 拼成一个"假实例"来调用——
 * 标记、计数、环形跳转这些逻辑就能像普通函数一样断言，不必真开浏览器。
 *
 * 跑法：node tests/test_search.mjs
 */
import { appOptions } from "../frontend/src/app.js";

// scrollToHit 之类的方法会摸 document / window：给最小替身即可（这些赋值在调用前生效就行，
// 不必像以前的 CJS 版本那样在 require 之前——app.js 的模块作用域不再碰浏览器 API）
globalThis.document = { querySelector: () => null, querySelectorAll: () => [] };
globalThis.window = globalThis;

const FAILED = [];
function check(name, got, want) {
  const ok = JSON.stringify(got) === JSON.stringify(want);
  if (!ok) FAILED.push(name);
  console.log(`[${ok ? "ok" : "FAIL"}] ${name}: ${JSON.stringify(got)}` +
              (ok ? "" : ` != ${JSON.stringify(want)}`));
}

// 拼一个够用的假实例：data 里的初值 + computed + 绑定了 this 的 methods
const data = appOptions.data();
const ctx = { ...data, $nextTick: (fn) => fn() };
for (const [k, fn] of Object.entries(appOptions.computed || {})) {
  Object.defineProperty(ctx, k, { get: () => fn.call(ctx) });
}
for (const [k, fn] of Object.entries(appOptions.methods || {})) {
  ctx[k] = (...a) => fn.apply(ctx, a);
}
// 监听器也挂上：测试要能直接触发它们（如"命中数变少时把序号夹回范围"）
ctx.watch = appOptions.watch || {};

// ---- 文本切块：渲染与搜索共用同一种切法 ----
const multi = { id: 1, content: "[SCENARIO]雨夜\n[DIALOG]你好", scenario: "MULTI" };
check("MULTI 切成情境+话语两块", ctx.textParts(multi).map((p) => p.kind), ["scenario", "dialog"]);
check("MULTI 的文本取自分段", ctx.textParts(multi).map((p) => p.text), ["雨夜", "你好"]);
const plain = { id: 2, content: "普通正文", scenario: "" };
check("非 MULTI 只有正文块", ctx.textParts(plain).map((p) => p.kind), ["text"]);
const withScen = { id: 3, content: "正文", scenario: "情境" };
check("情境+正文两块", ctx.textParts(withScen).map((p) => p.kind), ["scenario", "text"]);
check("渲染不含标记本身", ctx.textParts(multi).some((p) => p.text.includes("SCENARIO")), false);

// ---- 命中标记与全局序号 ----
ctx.messages = [
  { id: 10, role: "user", content: "今天下雨了，雨很大", scenario: "" },
  { id: 11, role: "assistant", content: "雨停了再说", scenario: "窗外的雨还在下" },
];
ctx.showArchived = false;
ctx.searchQuery = "雨";
let parts = ctx.partsOf(ctx.messages[0]);
let hits = parts[0].pieces.filter((p) => p.hit);
check("第一条消息命中数", hits.length, 2);
check("命中序号从 0 开始", hits.map((p) => p.index), [0, 1]);
check("命中片段就是关键词", hits.map((p) => p.text), ["雨", "雨"]);
check("非命中片段拼回原文",
      parts[0].pieces.map((p) => p.text).join(""), "今天下雨了，雨很大");
check("全部命中总数", ctx.searchTotal, 4);
parts = ctx.partsOf(ctx.messages[1]);
hits = parts.flatMap((p) => p.pieces.filter((x) => x.hit));
check("第二条消息（含情境）的序号接在后面", hits.map((p) => p.index), [2, 3]);
check("情境块也参与搜索", parts[0].kind, "scenario");

// ---- 大小写不敏感 + 元字符按字面 ----
ctx.messages = [{ id: 20, role: "user", content: "Hello hello HELLO", scenario: "" }];
ctx.searchQuery = "hello";
check("大小写不敏感", ctx.searchTotal, 3);
ctx.messages = [{ id: 21, role: "user", content: "axb a.b", scenario: "" }];
ctx.searchQuery = "a.b";
check("元字符按字面匹配", ctx.searchTotal, 1);
check("元字符命中位置正确",
      ctx.partsOf(ctx.messages[0])[0].pieces.filter((p) => p.hit).map((p) => p.text), ["a.b"]);
ctx.searchQuery = "   ";
check("只有空白视为没有搜索", ctx.searchTotal, 0);
check("空白时不建计划", Object.keys(ctx.searchPlan.parts).length, 0);

// ---- 空关键词：仍要能渲染出整段文本 ----
ctx.searchQuery = "";
parts = ctx.partsOf(ctx.messages[0]);
check("空关键词时不标黄", parts[0].pieces.every((p) => !p.hit), true);
check("空关键词时文本完整", parts[0].pieces.map((p) => p.text).join(""), "axb a.b");

// ---- 环形跳转 ----
ctx.messages = [{ id: 30, role: "user", content: "aaa", scenario: "" }];
ctx.searchQuery = "a";
ctx.searchIndex = 0;
check("三处命中", ctx.searchTotal, 3);
ctx.searchNext();
check("下一个", ctx.searchIndex, 1);
ctx.searchNext();
ctx.searchNext();
check("到尾再下一个绕回开头", ctx.searchIndex, 0);
ctx.searchPrev();
check("到头再上一个绕到末尾", ctx.searchIndex, 2);
ctx.searchQuery = "aa";
ctx.searchIndex = 1;
ctx.watch.searchTotal.call(ctx, 1);
check("命中变少时序号夹回", ctx.searchIndex, 0);
ctx.searchIndex = 2;
ctx.clearSearch();
check("清空搜索", [ctx.searchQuery, ctx.searchIndex], ["", 0]);

// ---- 只搜显示中的消息（归档折叠时不参与） ----
ctx.messages = [
  { id: 40, role: "user", content: "归档里的雨", scenario: "", archived: 1 },
  { id: 41, role: "user", content: "当前的雨", scenario: "" },
];
ctx.searchQuery = "雨";
ctx.showArchived = false;
check("归档未展开时不搜", ctx.searchTotal, 1);
check("序号只算显示中的", ctx.partsOf(ctx.messages[1])[0].pieces.filter((p) => p.hit)[0].index, 0);
ctx.showArchived = true;
check("展开归档后一起搜", ctx.searchTotal, 2);

console.log();
if (FAILED.length) {
  console.log(`失败 ${FAILED.length} 项：${JSON.stringify(FAILED)}`);
  process.exit(1);
}
console.log("会话内搜索用例全部通过");
