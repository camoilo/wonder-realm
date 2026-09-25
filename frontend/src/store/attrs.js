// 附加属性（角色的动态状态：好感 / 心情 / 表情…，见 DEVELOPMENT §2.6）。
//
// 定义挂在角色上（`characters.attr_defs`，跟着角色表单整体提交），值挂在每条消息上
// （`messages.attrs`，模型每轮输出、用户在编辑面板里也能改）。
// 这里放三件事：定义的增删与校验、顶部浮层要用的"最新一份属性"、编辑面板的值初始化。
import { store } from "./state.js";
import { emptyAttrDef } from "./helpers.js";
import { computed } from "vue";

Object.assign(store, {
  // ---- 定义编辑器（角色设定标签页里那一节，与词库同样的交互）----
  addAttr(form) {
    if (form.attr_defs.length >= store.limits.attr_max) return;
    form.attr_defs.push(emptyAttrDef());
  },
  removeAttr(form, index) {
    form.attr_defs.splice(index, 1);
  },
  // 需求是"名称必须填、类型必须选"：名称为空的行保存时丢弃（与词条一致），
  // 但**填了名字却没选类型**要挡下来——静默丢掉一条真的定义比报错更让人困惑
  validateAttrDefs(form) {
    store.attrError = "";
    const bad = (form.attr_defs || []).find(
      (d) => d.name.trim() && !d.type
    );
    if (bad) {
      store.attrError = `给「${bad.name.trim()}」选个类型（文字型或百分比型）`;
      return false;
    }
    return true;
  },
  // 保存前的清理：把没命名的空行去掉（界面上刚点出来、还没填的行）
  cleanAttrDefs(form) {
    return (form.attr_defs || [])
      .filter((d) => d.name.trim() && d.type)
      .map((d) => ({ name: d.name.trim(), type: d.type, hint: (d.hint || "").trim() }));
  },
  // 编辑消息弹窗里的属性行：按**角色当前的定义**铺开，已有值就填上、没有就留空
  attrRowsFor(message) {
    const have = new Map(
      ((message && message.attrs) || []).map((a) => [a.name, a.value])
    );
    return (store.attrDefs || []).map((d) => ({
      name: d.name,
      type: d.type,
      // 百分比型用数字框，空值就用空串（一起提交时后端会当成"没设置"丢掉）
      value: have.has(d.name) ? String(have.get(d.name)) : "",
    }));
  },
  // 一条属性的值怎么显示（浮层与编辑面板都用这一处，免得两处口径不一）
  attrText(attr) {
    if (attr.type === "percent") {
      const n = Number(attr.value);
      return Number.isFinite(n) ? `${Math.round(n)}%` : "";
    }
    return String(attr.value ?? "");
  },
  attrPercent(attr) {
    const n = Number(attr.value);
    if (!Number.isFinite(n)) return 0;
    return Math.max(0, Math.min(100, n));
  },
});

// 角色当前的属性定义：跟着面板表单走（正在编辑的那份），没有角色就是空
store.attrDefs = computed(() => {
  return (store.charForm && store.charForm.attr_defs) || [];
});

// 顶部浮层显示哪一条消息的属性：**最近一条带属性的消息**。
// 不取"最新一条消息"——用户刚发完言那条没有属性，浮层会闪空（见 §2.6）。
store.latestAttrs = computed(() => {
  for (let i = store.messages.length - 1; i >= 0; i--) {
    const attrs = store.messages[i].attrs;
    if (attrs && attrs.length) return attrs;
  }
  return [];
});

// 顶栏那个属性入口什么时候出现：**选中会话 + 聊天/沉浸模式**就出现（与"有没有定义/值"无关）。
// 早先要求"有值才出现"，于是没配属性的角色在顶栏根本看不到这个功能——入口应该常驻，
// 没配就在下拉里说明"这个角色还没有定义附加属性"（见 §2.6）
store.showAttrPanel = computed(() => {
  return !!store.activeSession && !store.isDirectorMode;
});

// 编辑面板里那一节是否出现：只有聊天与沉浸两种模式、且角色定义了属性
store.showAttrInEditor = computed(() => {
  if (!store.activeSession || store.isDirectorMode) return false;
  return (store.attrDefs || []).length > 0;
});
