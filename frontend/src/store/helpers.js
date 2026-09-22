// 模块级常量与纯函数：模式表、空的表单工厂、图片编解码等（不碰 store、不碰 Vue）。
// 这里的东西被 state.js 与各领域模块 import，所以顶层声明统一 export。
export const MODES = {
  chat: { label: "聊天模式", character: true },
  immersive: { label: "沉浸模式", character: true },
  director: { label: "导演模式", character: false },
};

// 与后端 parser.py 保持同一套标记识别（理由见那里的注释）：宽容认标记，
// 但只认这几种词，大小写与全角括号都接受
export const SCENARIO_TAGS = ["SCENARIO", "SCENERY", "SCENE", "NARRATION", "SETTING", "CONTEXT"];
export const DIALOG_TAGS = ["DIALOG", "DIALOGUE", "SPEECH", "TALK"];
export const ALL_TAG_SRC = SCENARIO_TAGS.concat(DIALOG_TAGS).join("|");
export const TAG_SRC = "[\\[【]\\s*(?:" + ALL_TAG_SRC + ")\\s*[\\]】]";
export const SEGMENT_RE = new RegExp(
  "[\\[【]\\s*(" + ALL_TAG_SRC + ")\\s*[\\]】]\\s*(.*?)(?=\\n?" + TAG_SRC + "|$)",
  "gis"
);
export const isScenarioTag = (tag) => SCENARIO_TAGS.includes(String(tag).toUpperCase());

// "还原"键的解除武装计时器。放模块级而不是 data 里：定时器句柄不需要响应式
export const revertTimers = {};

// 导演模式"继续"按钮发出的内容：等同于用户手打一条"继续"
export const CONTINUE_PROMPT = "继续";

// 自定义头像：浏览器内先校验，再让用户拖动裁剪成正方形，最后缩到 256px 重编码为 JPEG 上传。
// 前端就把图处理好，后端不必收原始文件（省掉 multipart 依赖），也保证存进库的
// 永远是我们自己编码的位图而不是用户原始字节。
export const AVATAR_OUT_PX = 256; // 输出正方形的边长
export const CROP_VIEW_PX = 280; // 裁剪取景框的显示边长（正方形）
export const CROP_MAX_ZOOM = 3;
export const AVATAR_MAX_UPLOAD = 10 * 1024 * 1024; // 单文件上限
export const AVATAR_MIN_SIDE = 256; // 原图最短边下限：不小于输出边长，保证永远不会被放大
export const AVATAR_MAX_PIXELS = 40 * 1000 * 1000; // 原图像素总量上限
export const AVATAR_QUALITY = 0.85;

// 对话区背景图：不裁剪，只等比缩到长边不超过 BG_MAX_PX（不放大），重编码为 JPEG。
export const BG_MAX_COUNT = 5;
export const BG_MAX_PX = 1920;
export const BG_MIN_LONG_SIDE = 640; // 长边下限：再小铺在对话区只会糊成一片
export const BG_QUALITY = 0.85;
export const BG_MAX_UPLOAD = 10 * 1024 * 1024;

// 裁剪用的解码结果放在模块级而不是 data 里：Image 对象不需要（也不该）被 Vue 代理，
// drawImage 直接吃原始对象最稳。

// 选文件后立刻做的校验：返回错误文案，空串表示通过
export const fileTypeSizeError = (type, size, maxBytes) => {
  if (!type || !type.startsWith("image/")) return "请选择图片文件（jpg/png/webp 等）";
  if (size > maxBytes)
    return `图片太大（上限 ${Math.round(maxBytes / 1024 / 1024)}MB），请先压缩或换一张`;
  return "";
};

export const avatarFileError = (type, size) => fileTypeSizeError(type, size, AVATAR_MAX_UPLOAD);
export const backgroundFileError = (type, size) => fileTypeSizeError(type, size, BG_MAX_UPLOAD);

// 解码出真实分辨率后再校验一次
export const avatarImageError = (w, h) => {
  if (!w || !h) return "这个文件不是能识别的图片";
  if (Math.min(w, h) < AVATAR_MIN_SIDE)
    return `图片太小（至少 ${AVATAR_MIN_SIDE}×${AVATAR_MIN_SIDE}），放大后会糊`;
  if (w * h > AVATAR_MAX_PIXELS) return "图片分辨率过高，请先缩小再上传";
  return "";
};

export const backgroundImageError = (w, h) => {
  if (!w || !h) return "这个文件不是能识别的图片";
  if (Math.max(w, h) < BG_MIN_LONG_SIDE)
    return `图片太小（长边至少 ${BG_MIN_LONG_SIDE}px），铺在对话区会糊`;
  return "";
};

// 等比缩到长边不超过 max，且只缩不放（小图保持原尺寸）
export const fitSize = (w, h, max) => {
  if (!w || !h) return { w: 1, h: 1 };
  const scale = Math.min(1, max / Math.max(w, h));
  return { w: Math.max(1, Math.round(w * scale)), h: Math.max(1, Math.round(h * scale)) };
};

// 整张画进画布并重编码为 JPEG 的 data URL。先铺白底：
// 带透明通道的 PNG/WebP 直接转 JPEG，透明处会变成黑块。
export const encodeJpeg = (img, w, h, quality) => {
  const canvas = document.createElement("canvas");
  canvas.width = w;
  canvas.height = h;
  const ctx = canvas.getContext("2d");
  ctx.fillStyle = "#fff";
  ctx.fillRect(0, 0, w, h);
  ctx.drawImage(img, 0, 0, w, h);
  return canvas.toDataURL("image/jpeg", quality);
};

// "铺满"取景框所需的基础缩放：取长短边的较大者，保证两个方向都不留空
export const coverScale = (w, h, view) => Math.max(view / w, view / h);

// 把偏移限制在"图片始终盖满取景框"的范围内。这一步是正确性的关键：
// 一旦图片边缘跑进取景框内，裁出来就会带空白边。
export const clampOffset = (v, drawn, view) => Math.min(0, Math.max(view - drawn, v));

// 取景框状态 → 原图上的取样矩形（纯函数，便于单测）
export const cropSourceRect = (natW, natH, view, zoom, x, y) => {
  const s = coverScale(natW, natH, view) * zoom;
  return { sx: -x / s, sy: -y / s, side: view / s };
};

// 以取景框中心为锚点缩放，返回夹好边界的新偏移（纯函数，便于单测）。
// 不锚定的话放大时图片会往左上跑，观感很跳。
export const zoomAroundCenter = (natW, natH, view, fromZoom, toZoom, x, y) => {
  const unit = coverScale(natW, natH, view);
  const prev = unit * fromZoom;
  const next = unit * toZoom;
  const cx = (view / 2 - x) / prev; // 取景框中心对应的原图坐标
  const cy = (view / 2 - y) / prev;
  return {
    x: clampOffset(view / 2 - cx * next, natW * next, view),
    y: clampOffset(view / 2 - cy * next, natH * next, view),
  };
};

export const readAsDataURL = (file) =>
  new Promise((resolve, reject) => {
    const reader = new FileReader();
    reader.onerror = () => reject(new Error("read-failed"));
    reader.onload = () => resolve(reader.result);
    reader.readAsDataURL(file);
  });

export const loadImage = (src) =>
  new Promise((resolve, reject) => {
    const img = new Image();
    img.onload = () => resolve(img);
    img.onerror = () => reject(new Error("decode-failed"));
    img.src = src;
  });

export const emptyCharForm = () => ({
  name: "",
  appearance: "",
  personality: "",
  speech_style: "",
  backstory: "",
  avatar: "",
  // 对话区背景图（data URL 数组）。放在表单里是必须的：新建角色时还没有 id、
  // 没法立即上传，而且面板是整体提交的，漏了它就会把背景一次性清空。
  backgrounds: [],
});

// 探索模式下对用户隐藏、也不允许改写的三个字段（与后端 character_gen.HIDDEN_FIELDS 一致）
export const LOCKED_FIELDS = ["personality", "speech_style", "backstory"];

// "我的设定"（用户本人）。全局单行，与角色无关；三项都可以留空
export const emptyProfile = () => ({ name: "", identity: "", appearance: "", avatar: "" });

// "世界设定"。全局一份，与角色/会话无关；四项都可以留空。
// terms 是词库：[{term, meaning}]，顺序就是注入提示词的顺序。
export const emptyWorld = () => ({ name: "", description: "", rules: "", terms: [] });

export const emptyGenerator = () => ({
  hint: "",
  mode: "open", // open = 全部直接展示；explore = 只公开姓名与外观
  busy: false,
  error: "",
  draftId: null, // 服务端草稿 id：探索模式下隐藏的字段只存在服务端
});

// 用工厂函数而不是到处写字面量：漏一个键就会出现"某状态下少个字段"的怪问题
// （之前 charSaved 初始化没和表单默认值对齐，面板一打开就显示"未保存"）
export const emptyCharModal = () => ({
  visible: false,
  editingId: null,
  form: emptyCharForm(),
  gen: emptyGenerator(),
  locked: false,
  // 保存失败要在弹窗里说：底部错误条只在会话打开时渲染，新建角色时它根本不在
  saveError: "",
});
