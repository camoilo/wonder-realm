/**
 * 弹窗"点窗口外关闭"的判定测试（Node 直接跑，不需要浏览器）。
 *
 * 背景：用 @click.self 会把"在弹窗里选文字、拖到遮罩外松开"误判成点了窗口外，窗口被关掉。
 * 判据必须换成"按下（mousedown）是否落在遮罩上"。这里把四种真实情形都跑一遍。
 *
 * 跑法：node tests/test_mask_close.mjs
 */
import { useMaskClose } from "../frontend/src/composables/maskClose.js";

const FAILED = [];
function check(name, got, want) {
  const ok = JSON.stringify(got) === JSON.stringify(want);
  if (!ok) FAILED.push(name);
  console.log(`[${ok ? "ok" : "FAIL"}] ${name}: ${JSON.stringify(got)}` +
              (ok ? "" : ` != ${JSON.stringify(want)}`));
}

const MASK = { tag: "mask" };
const INNER = { tag: "inner" };

/** 走一遍"按下 → 松开 → click"，返回关闭次数。三个 target 说明鼠标落在哪里。 */
function drag(downTarget, upTarget, clickTarget) {
  let closed = 0;
  const { onMaskDown, onMaskUp, onMaskClick } = useMaskClose(() => { closed++; });
  const ev = (t) => ({ target: t, currentTarget: MASK });
  onMaskDown(ev(downTarget));
  onMaskUp(ev(upTarget));
  onMaskClick(ev(clickTarget));
  return closed;
}

check("按下与松开都在遮罩上 → 关闭", drag(MASK, MASK, MASK), 1);
check("按下在弹窗里（选文字）、松开拖到遮罩 → 不关", drag(INNER, MASK, MASK), 0);
check("按下在弹窗里、click 却落在遮罩 → 不关", drag(INNER, INNER, MASK), 0);
check("按下在遮罩、松开拖回弹窗里 → 不关", drag(MASK, INNER, MASK), 0);
check("按下在遮罩、click 落在弹窗内容上 → 不关", drag(MASK, MASK, INNER), 0);
check("在弹窗里按下并松开（正常操作）→ 不关", drag(INNER, INNER, INNER), 0);

// 状态不能残留：先来一次"选了文字"的拖拽，再正常点一次窗口外，第二次必须能关
{
  let closed = 0;
  const { onMaskDown, onMaskUp, onMaskClick } = useMaskClose(() => { closed++; });
  const ev = (t) => ({ target: t, currentTarget: MASK });
  onMaskDown(ev(INNER));
  onMaskUp(ev(MASK));
  onMaskClick(ev(MASK));
  onMaskDown(ev(MASK));
  onMaskUp(ev(MASK));
  onMaskClick(ev(MASK));
  check("上一次拖拽不残留，下一次点窗口外仍能关", closed, 1);
}

// 鼠标移出窗口后松开：浏览器不派发 click，所以不会关（这里只验证前面的 mousedown 不留后患）
{
  let closed = 0;
  const { onMaskDown, onMaskClick } = useMaskClose(() => { closed++; });
  const ev = (t) => ({ target: t, currentTarget: MASK });
  onMaskDown(ev(MASK));
  check("鼠标移出窗口松开（没有 click）→ 不关", closed, 0);
  onMaskClick({ target: MASK, currentTarget: MASK });
  check("随后真的点了窗口外 → 关", closed, 1);
}

console.log();
if (FAILED.length) {
  console.log(`失败 ${FAILED.length} 项：${JSON.stringify(FAILED)}`);
  process.exit(1);
}
console.log("弹窗关闭判定用例全部通过");
