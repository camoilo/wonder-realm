// 会话内搜索：命中计划、计数、环形跳转与滚动定位。
//
// 只依赖 state.js（唯一的 reactive 对象），不 import 别的领域模块 —— 依赖是星形的，
// 所以不存在循环依赖；跨领域的调用都走 store.xxx（运行时才解析）。
import { store } from "./state.js";
import { computed, nextTick } from "vue";

Object.assign(store, {
  escapeRegExp(s) {
    return s.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
  },
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
  scrollToHit() {
    nextTick(() => {
      const el = document.querySelector(".search-hit.current");
      if (el) el.scrollIntoView({ block: "center", behavior: "smooth" });
    });
  },
});

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
