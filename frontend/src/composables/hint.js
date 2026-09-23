// 悬停/聚焦提示的统一实现（`v-hint` 指令 + App.vue 里的单例浮层）。
//
// 为什么不用原生 title：延迟约一秒、样式跟浏览器走、不能换行，与界面其它部分不是一个语言。
// 为什么用指令而不是包一层组件：提示挂在按钮、图标、缩略图等**各种元素**上，包组件会多一层
// DOM、改变 flex/grid 布局；指令只加事件监听，结构一点不动。
//
// 定位：默认贴在目标下方居中，下方放不下就翻到上方，左右夹取到视口内；浮层 pointer-events:
// none，所以它不会截住鼠标、也不会把触发它的 mouseleave 提前引爆。
import { nextTick, ref } from "vue";

export const hintText = ref("");
export const hintStyle = ref({});

const GAP = 8;      // 浮层与目标的间距
const MARGIN = 8;   // 距视口边缘至少留这么多
let current = null; // 当前正在显示的那个元素（只可能有一个）

// 触屏设备（手机/平板）没有 hover，v-hint 降级为"点一下看提示、再点一下或点别处关闭"。
// 用 pointer: coarse 判断，与 CSS 触屏适配同一套语义（模拟器切触屏时也即时生效）
const coarsePointer = typeof window !== "undefined"
  && window.matchMedia("(pointer: coarse)").matches;

function textOf(el) {
  return String(el.__hintValue ?? "").trim();
}

function place(el) {
  const r = el.getBoundingClientRect();
  const cx = r.left + r.width / 2;
  // 第一趟先按"居中"放下去，好让浮层渲染出来、量到自己的宽度
  hintStyle.value = {
    left: `${Math.round(cx)}px`,
    top: `${Math.round(r.bottom + GAP)}px`,
    transform: "translateX(-50%)",
  };
  // 量到宽度后换成明确的左上角坐标：**最终位置不用 transform**——动画或别的规则
  // 一旦碰 transform，居中就会被带偏（曾用 translateY 做入场动画，直接把居中顶掉了）
  nextTick(() => {
    const tip = document.querySelector(".hint-tip");
    if (!tip || current !== el) return;
    const t = tip.getBoundingClientRect();
    const left = Math.min(Math.max(cx - t.width / 2, MARGIN), window.innerWidth - MARGIN - t.width);
    let top = r.bottom + GAP;
    if (top + t.height > window.innerHeight - MARGIN) {
      top = Math.max(MARGIN, r.top - t.height - GAP); // 下方放不下就翻到上方
    }
    hintStyle.value = { left: `${Math.round(left)}px`, top: `${Math.round(top)}px` };
  });
}

function show(el) {
  const text = textOf(el);
  if (!text) return;
  current = el;
  hintText.value = text;
  place(el);
}

function hide(el) {
  if (current !== el) return;
  current = null;
  hintText.value = "";
}

// 滚动或改窗口大小时位置就过时了，直接收起来（比跟着挪更不打扰）
function hideAll() {
  if (!current) return;
  current = null;
  hintText.value = "";
}

if (typeof window !== "undefined") {
  window.addEventListener("scroll", hideAll, true);
  window.addEventListener("resize", hideAll);
  // 触屏降级：点提示元素之外任意处关闭（bubble 阶段晚于元素自己的 click 切换，
  // 所以"再点一下同一个元素"由 __hintToggle 处理，这里只管点别处）
  if (coarsePointer) {
    document.addEventListener("click", (e) => {
      if (current && !current.contains(e.target)) hideAll();
    });
  }
}

export const hintDirective = {
  mounted(el, binding) {
    el.__hintValue = binding.value;
    el.__hintShow = () => show(el);
    el.__hintHide = () => hide(el);
    // 触屏（手机/平板）没有 hover：降级为"点一下看提示、再点一下或点别处关闭"。
    // 桌面照旧用悬停/聚焦。判断走 pointer: coarse，与 CSS 的触屏适配同一套语义
    if (coarsePointer) {
      el.__hintToggle = () => (current === el ? hide(el) : show(el));
      el.addEventListener("click", el.__hintToggle);
    } else {
      el.addEventListener("mouseenter", el.__hintShow);
      el.addEventListener("mouseleave", el.__hintHide);
      el.addEventListener("focus", el.__hintShow);
      el.addEventListener("blur", el.__hintHide);
    }
  },
  updated(el, binding) {
    // 文案是动态的（如"关闭背景 / 显示背景"）：如果正显示着，跟着换掉
    el.__hintValue = binding.value;
    if (current === el) {
      const text = textOf(el);
      if (!text) hideAll();
      else {
        hintText.value = text;
        place(el);
      }
    }
  },
  unmounted(el) {
    if (coarsePointer) {
      el.removeEventListener("click", el.__hintToggle);
    } else {
      el.removeEventListener("mouseenter", el.__hintShow);
      el.removeEventListener("mouseleave", el.__hintHide);
      el.removeEventListener("focus", el.__hintShow);
      el.removeEventListener("blur", el.__hintHide);
    }
    if (current === el) hideAll();
  },
};
