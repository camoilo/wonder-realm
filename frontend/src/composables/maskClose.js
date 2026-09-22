// 弹窗"点遮罩关闭"的共用逻辑。
//
// 为什么不能只用 @click.self：click 的目标是 **mousedown 与 mouseup 的共同祖先**。
// 在弹窗里按住鼠标选文字、拖到遮罩上（或拖出窗口）再松开时，mousedown 的目标是输入框、
// mouseup 的目标是遮罩，于是 click 落到遮罩上，"点窗口外关闭"被误触发——用户选个文字
// 就把窗口关掉了。
//
// 真正的判据是"按下"的位置：只有 mousedown 本身就落在遮罩上，后续那次 click 才算点了外面。
// 三个处理函数配合覆盖这几种情形：
//   mousedown 在内容里（选文字、拖滚动条）→ 之后任何 click 都不关
//   mousedown 在遮罩、mouseup 也在遮罩       → 关（这才是"点窗口外"）
//   mousedown 在遮罩、mouseup 拖回内容里     → 不关（mouseup 复位）
//   mousedown 在遮罩、鼠标移出窗口松开       → 浏览器不派发 click，自然不关
import { ref } from "vue";

export function useMaskClose(onClose) {
  const armed = ref(false);
  return {
    onMaskDown(event) {
      armed.value = event.target === event.currentTarget;
    },
    onMaskUp(event) {
      if (event.target !== event.currentTarget) armed.value = false;
    },
    onMaskClick(event) {
      const hitMask = armed.value && event.target === event.currentTarget;
      armed.value = false;
      if (hitMask) onClose();
    },
  };
}
