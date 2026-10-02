// 角色：编辑弹窗与面板表单、让模型生成、探索模式解锁、头像裁剪、对话背景。
//
// 只依赖 state.js（唯一的 reactive 对象），不 import 别的领域模块 —— 依赖是星形的，
// 所以不存在循环依赖；跨领域的调用都走 store.xxx（运行时才解析）。
import { store } from "./state.js";
import { computed } from "vue";
import { AVATAR_OUT_PX, AVATAR_QUALITY, BG_MAX_COUNT, BG_MAX_PX, BG_QUALITY, CROP_MAX_ZOOM, CROP_VIEW_PX, LOCKED_FIELDS, avatarFileError, avatarImageError, backgroundFileError, backgroundImageError, clampOffset, coverScale, cropSourceRect, emptyCharModal, encodeJpeg, fitSize, loadImage, readAsDataURL, zoomAroundCenter } from "./helpers.js";

// 本模块独有的可变私有状态（原来在 store.js 顶层；别放进 helpers，因为它是 let、会被赋值）
let cropImage = null;

Object.assign(store, {
  async pickAvatar(e, target) {
    const file = e.target.files && e.target.files[0];
    e.target.value = ""; // 清掉，才能连续两次选同一个文件
    if (!file) return;
    store.avatarError = "";
    const early = avatarFileError(file.type, file.size);
    if (early) {
      store.avatarError = early;
      return;
    }
    let src;
    try {
      src = await readAsDataURL(file);
    } catch (err) {
      store.avatarError = "读取文件失败，请重试";
      return;
    }
    let img;
    try {
      img = await loadImage(src);
    } catch (err) {
      store.avatarError = "这个文件不是能识别的图片";
      return;
    }
    const later = avatarImageError(img.naturalWidth, img.naturalHeight);
    if (later) {
      store.avatarError = later;
      return;
    }
    cropImage = img;
    const natW = img.naturalWidth;
    const natH = img.naturalHeight;
    const s = coverScale(natW, natH, CROP_VIEW_PX);
    store.crop = {
      visible: true,
      target,
      src,
      view: CROP_VIEW_PX,
      natW,
      natH,
      zoom: 1,
      maxZoom: CROP_MAX_ZOOM,
      // 初始居中
      x: (CROP_VIEW_PX - natW * s) / 2,
      y: (CROP_VIEW_PX - natH * s) / 2,
      dragging: false,
    };
  },
  cropDown(e) {
    const c = store.crop;
    if (!c.visible) return;
    c.dragging = true;
    store._drag = { px: e.clientX, py: e.clientY, x0: c.x, y0: c.y };
    e.currentTarget.setPointerCapture?.(e.pointerId);
  },
  cropMove(e) {
    const c = store.crop;
    if (!c.dragging || !store._drag) return;
    const d = store._drag;
    const s = coverScale(c.natW, c.natH, c.view) * c.zoom;
    c.x = clampOffset(d.x0 + (e.clientX - d.px), c.natW * s, c.view);
    c.y = clampOffset(d.y0 + (e.clientY - d.py), c.natH * s, c.view);
  },
  cropUp(e) {
    store.crop.dragging = false;
    store._drag = null;
    e.currentTarget.releasePointerCapture?.(e.pointerId);
  },
  setCropZoom(z) {
    const c = store.crop;
    if (!c.visible) return;
    const to = Math.min(c.maxZoom, Math.max(1, Number(z) || 1));
    const next = zoomAroundCenter(c.natW, c.natH, c.view, c.zoom, to, c.x, c.y);
    c.zoom = to;
    c.x = next.x;
    c.y = next.y;
  },
  cancelCrop() {
    store.crop.visible = false;
    cropImage = null;
  },
  confirmCrop() {
    const c = store.crop;
    if (!cropImage) {
      store.cancelCrop();
      return;
    }
    const { sx, sy, side } = cropSourceRect(c.natW, c.natH, c.view, c.zoom, c.x, c.y);
    const canvas = document.createElement("canvas");
    canvas.width = AVATAR_OUT_PX;
    canvas.height = AVATAR_OUT_PX;
    const ctx = canvas.getContext("2d");
    // 先铺白底：带透明通道的 PNG/WebP 转 JPEG 时，透明处会变黑块
    ctx.fillStyle = "#fff";
    ctx.fillRect(0, 0, AVATAR_OUT_PX, AVATAR_OUT_PX);
    try {
      ctx.drawImage(cropImage, sx, sy, side, side, 0, 0, AVATAR_OUT_PX, AVATAR_OUT_PX);
      const dataUrl = canvas.toDataURL("image/jpeg", AVATAR_QUALITY);
      store.avatarForm(c.target).avatar = dataUrl;
      store.avatarError = "";
      store.cancelCrop();
    } catch (err) {
      // 引用了外部资源（或跨域）的图片会污染画布，toDataURL 会抛 SecurityError
      store.avatarError = "这张图片无法处理（可能引用了外部资源），请换一张";
    }
  },
  avatarForm(target) {
    // 面板上的「我的设定」页只读（内容来自绑定的预设），所以没有 "profile" 这个目标了：
    // 换头像是"改预设内容"，只能在预设弹窗里做
    if (target === "preset") return store.presetModal.form;
    return target === "modal" ? store.charModal.form : store.charForm;
  },
  clearAvatar(target) {
    store.avatarError = "";
    store.avatarForm(target).avatar = "";
  },
  resetBackgrounds() {
    store.bgImages = [];
    store.bgIndex = 0;
    // "关闭背景"是临时的：换会话/角色就恢复显示
    store.bgHidden = false;
    store.bgError = "";
  },
  async loadBackgrounds(cid, syncForm = true) {
    try {
      const resp = await store.api(`/api/characters/${cid}/backgrounds`);
      store.bgImages = resp.images || [];
      store.bgMax = resp.max || BG_MAX_COUNT;
      if (store.bgIndex >= store.bgImages.length) store.bgIndex = 0;
      if (syncForm && store.activeChar && store.activeChar.id === cid) {
        store.charForm.backgrounds = [...store.bgImages];
        // 只同步基线里的 backgrounds，不要整体重拍快照：
        // 那会把面板里其它尚未保存的改动一并标记成"已保存"
        if (store.charSaved) store.charSaved.backgrounds = [...store.bgImages];
      }
    } catch (e) {
      store.bgImages = [];
    }
  },
  async loadModalBackgrounds(cid) {
    try {
      const resp = await store.api(`/api/characters/${cid}/backgrounds`);
      if (store.charModal.editingId === cid) {
        store.charModal.form.backgrounds = resp.images || [];
        store.bgMax = resp.max || BG_MAX_COUNT;
        // 背景图是"从别处取回来的"，不是用户改的：取完顺手把快照对齐，
        // 否则弹窗一打开就顶着"未保存"（见 charModal.saved 的用途）
        store.charModal.saved = store.snapshot(store.charModal.form);
      }
    } catch (e) {
      /* 取不到就按空处理，保存时以表单为准 */
    }
  },
  prevBg() {
    const n = store.bgImages.length;
    if (n > 1) store.bgIndex = (store.bgIndex - 1 + n) % n;
  },
  nextBg() {
    const n = store.bgImages.length;
    if (n > 1) store.bgIndex = (store.bgIndex + 1) % n;
  },
  bgList(target) {
    return (target === "modal" ? store.charModal.form.backgrounds : store.charForm.backgrounds) || [];
  },
  setBgList(target, list) {
    if (target === "modal") store.charModal.form.backgrounds = list;
    else store.charForm.backgrounds = list;
  },
  async addBackgrounds(e, target) {
    const files = Array.from(e.target.files || []);
    e.target.value = ""; // 清掉，才能连续两次选同一个文件
    if (!files.length) return;
    const list = store.bgList(target);
    const room = store.bgMax - list.length;
    store.bgError = "";
    if (room <= 0) {
      store.bgError = `最多只能放 ${store.bgMax} 张背景图`;
      return;
    }
    // 一次性可能选好几张大图，逐张缩放编码会占用一段时间，
    // 期间给个"处理中"状态并把按钮禁掉，避免重复点击
    store.bgBusy = true;
    const added = [];
    let problem = "";
    try {
      for (const file of files.slice(0, room)) {
        const early = backgroundFileError(file.type, file.size);
        if (early) {
          problem = early;
          continue;
        }
        let img;
        try {
          img = await loadImage(await readAsDataURL(file));
        } catch (err) {
          problem = "有文件不是能识别的图片，已跳过";
          continue;
        }
        const later = backgroundImageError(img.naturalWidth, img.naturalHeight);
        if (later) {
          problem = later;
          continue;
        }
        const { w, h } = fitSize(img.naturalWidth, img.naturalHeight, BG_MAX_PX);
        try {
          added.push(encodeJpeg(img, w, h, BG_QUALITY));
        } catch (err) {
          problem = "有图片无法处理（可能引用了外部资源），已跳过";
        }
        await new Promise((r) => setTimeout(r, 0)); // 让出主线程，界面不至于卡住
      }
    } finally {
      store.bgBusy = false;
    }
    if (added.length) store.setBgList(target, [...list, ...added]);
    if (files.length > room) problem = `最多 ${store.bgMax} 张，多选的已忽略`;
    store.bgError = problem;
  },
  removeBackground(target, i) {
    const list = [...store.bgList(target)];
    list.splice(i, 1);
    store.setBgList(target, list);
    store.bgError = "";
  },
  moveBackground(target, from, to) {
    const list = [...store.bgList(target)];
    if (from === to || from < 0 || to < 0 || from >= list.length || to >= list.length) return;
    const [item] = list.splice(from, 1);
    list.splice(to, 0, item);
    store.setBgList(target, list);
    store.bgError = "";
  },
  bgDragStart(e, target, i) {
    store.bgDrag = { target, index: i };
    store.bgHover = { target: null, index: null };
    if (e.dataTransfer) {
      e.dataTransfer.effectAllowed = "move";
      // Firefox 不设数据就不启动拖拽
      try {
        e.dataTransfer.setData("text/plain", String(i));
      } catch (err) {
        /* 忽略：设不上也不影响其它浏览器 */
      }
    }
  },
  bgDragOver(e, target, i) {
    if (store.bgDrag.index === null || store.bgDrag.target !== target) return;
    store.bgHover = { target, index: i };
  },
  bgDrop(e, target, i) {
    // 先把状态取出来再清空：moveBackground 里要用
    const drag = store.bgDrag;
    store.bgDragEnd();
    if (!drag.target || drag.target !== target || drag.index === null) return;
    store.moveBackground(target, drag.index, i);
  },
  bgDragEnd() {
    store.bgDrag = { target: null, index: null };
    store.bgHover = { target: null, index: null };
  },
  bgDragging(target, i) {
    return store.bgDrag.target === target && store.bgDrag.index === i;
  },
  bgDropTarget(target, i) {
    return store.bgHover.target === target && store.bgHover.index === i;
  },
  openCharacterModal(c = null) {
    store.avatarError = ""; // 换一个角色就清掉上一次的提示
    store.bgError = "";
    // 两个绑定下拉要列出所有预设：没加载过（或一条都没有）就顺手各拉一次
    if (!store.profilePresets.length) store.loadPresets("profile");
    if (!store.worldPresets.length) store.loadPresets("world");
    if (c) {
      store.charModal = {
        ...emptyCharModal(),
        visible: true,
        editingId: c.id,
        form: {
          name: c.name,
          appearance: c.appearance,
          personality: c.personality || "",
          speech_style: c.speech_style || "",
          backstory: c.backstory || "",
          avatar: c.avatar || "",
          backgrounds: [], // 背景图不随角色列表下发，下面单独取
          profile_id: c.profile_id ?? null, // 这个角色绑定的「我的设定」预设
          world_id: c.world_id ?? null, // 这个角色绑定的世界预设
        },
        locked: !!c.locked,
      };
      store.loadModalBackgrounds(c.id);
    } else {
      store.charModal = { ...emptyCharModal(), visible: true };
      // 新建：快照就是这份空表单
      store.charModal.saved = store.snapshot(store.charModal.form);
    }
  },
  async generateCharacter() {
    const gen = store.charModal.gen;
    if (gen.busy) return;
    gen.busy = true;
    gen.stopped = false;
    gen.error = "";
    gen.abortCtrl = new AbortController();
    try {
      const r = await store.api(
        "/api/characters/generate",
        store.jsonOpts("POST", { hint: gen.hint, mode: gen.mode }, gen.abortCtrl.signal)
      );
      store.avatarError = "";
      store.charModal.form.name = r.name || "";
      store.charModal.form.appearance = r.appearance || "";
      for (const k of LOCKED_FIELDS) {
        store.charModal.form[k] = r[k] || "";
      }
      store.charModal.locked = !!r.locked;
      gen.draftId = r.draft_id;
    } catch (e) {
      // 自己按的「停止」不算错误（草稿没生成出来，输入框里的提示词还在）
      if (!gen.stopped) gen.error = e.message;
    } finally {
      gen.busy = false;
      gen.abortCtrl = null;
    }
  },
  // 角色生成是普通请求（不是流）：中断这次请求即可，服务端那次调用会自己超时结束
  stopCharacterGenerate() {
    const gen = store.charModal.gen;
    if (!gen.busy || !gen.abortCtrl) return;
    gen.stopped = true;
    gen.abortCtrl.abort();
  },
  // 「停止所有生成」：本地这条流 + 角色生成 + 让服务端把它那边的流全部收尾
  // （手机与电脑同时开着时，一次就能全停）
  async stopAllGenerations() {
    store.stop();
    store.stopCharacterGenerate();
    try {
      await store.api("/api/generate/stop", { method: "POST" });
    } catch (e) {
      store.error = e.message;
    }
  },
  resetGeneratedDraft() {
    const gen = store.charModal.gen;
    gen.draftId = null;
    gen.error = "";
    store.charModal.locked = false;
    for (const k of LOCKED_FIELDS) store.charModal.form[k] = "";
  },
  async unlockCharacter(target) {
    const cid = target === "panel"
      ? (store.activeChar && store.activeChar.id)
      : store.charModal.editingId;
    if (!cid) return;
    const ok = await store.ask(
      "公开后将永久取消锁定，性格 / 语言风格 / 背景故事会显示出来并可以修改，且无法再锁回去。确定要公开吗？"
    );
    if (!ok) return;
    try {
      const c = await store.api(`/api/characters/${cid}/unlock`, { method: "POST" });
      const i = store.characters.findIndex((x) => x.id === cid);
      if (i >= 0) store.characters[i] = { ...store.characters[i], ...c };
      if (target === "panel") {
        for (const k of LOCKED_FIELDS) {
          store.charForm[k] = c[k] || "";
          // 快照一起写：这两处都是刚拿到的原值，不该被判成"未保存"
          store.charSaved[k] = c[k] || "";
        }
        store.charLocked = false;
        if (store.activeSession && store.activeSession.character) {
          Object.assign(store.activeSession.character, c);
        }
      } else {
        for (const k of LOCKED_FIELDS) store.charModal.form[k] = c[k] || "";
        store.charModal.locked = false;
      }
    } catch (e) {
      store.error = e.message;
    }
  },
  async saveCharacterModal() {
    // 背景图不属于角色接口的字段，单独整体提交，所以先从角色载荷里摘出去
    const { backgrounds, ...charPayload } = store.charModal.form;
    store.charModal.saveError = "";
    if (store.charModal.gen.draftId) charPayload.draft_id = store.charModal.gen.draftId;
    try {
      let cid = store.charModal.editingId;
      if (cid) {
        delete charPayload.draft_id; // 编辑已有角色时不该带草稿
        await store.api(`/api/characters/${cid}`, store.jsonOpts("PUT", charPayload));
      } else {
        const c = await store.api("/api/characters", store.jsonOpts("POST", charPayload));
        cid = c.id;
        store.expandedChars[c.id] = true;
      }
      await store.api(
        `/api/characters/${cid}/backgrounds`,
        store.jsonOpts("PUT", { images: backgrounds || [] })
      );
      store.charModal.visible = false;
      await store.afterCharacterChange();
    } catch (e) {
      // 弹窗里就地提示：例如应用重启导致探索模式的草稿失效，用户需要知道要重新生成
      store.charModal.saveError = e.message;
      store.error = e.message;
    }
  },
  async saveCharacterDrawer() {
    // 附加属性定义先校验再提交：填了名字却没选类型要挡下来（需求："类型必须选"），
    // 否则那一条会被后端当成"没命名"静默丢掉
    if (!store.validateAttrDefs(store.charForm)) return;
    const { backgrounds, ...charPayload } = store.charForm;
    charPayload.attr_defs = store.cleanAttrDefs(store.charForm);
    try {
      const cid = store.activeSession.character.id;
      await store.api(`/api/characters/${cid}`, store.jsonOpts("PUT", charPayload));
      await store.api(
        `/api/characters/${cid}/backgrounds`,
        store.jsonOpts("PUT", { images: backgrounds || [] })
      );
      await store.afterCharacterChange();
    } catch (e) {
      store.error = e.message;
    }
  },
  async afterCharacterChange() {
    await store.refreshCharacters();
    await store.refreshSessions();
    if (store.activeSessionId) {
      store.activeSession = await store.api(`/api/sessions/${store.activeSessionId}`);
    }
    // 角色可能刚被保存或删除，背景图跟着刷新（没有角色就清空）
    if (store.activeChar) await store.loadBackgrounds(store.activeChar.id);
    else store.resetBackgrounds();
    // 绑定可能刚改过：把"我的身份"与"世界"重新对齐到当前角色（见 DEVELOPMENT §2.3 / §2.4）
    await store.syncCharacterBindings();
  },
});

store.chatBgUrl = computed(() => {
      if (!store.activeChar || !store.bgImages.length || store.bgHidden) return "";
      const i = Math.min(Math.max(store.bgIndex, 0), store.bgImages.length - 1);
      return store.bgImages[i] || "";
});

// 角色编辑弹窗里"有没有改动"：拿当前表单和打开时的快照比（见 charModal.saved）。
// 弹窗里也带「未保存 / 还原」，手机上面板底部那排够不到时全靠它
store.charModalDirty = computed(() => {
      if (!store.charModal.visible || !store.charModal.saved) return false;
      return !store.sameSnapshot(store.charModal.form, store.charModal.saved);
});

store.showBgBar = computed(() => {
      return !!store.activeChar && store.bgImages.length > 0;
});

store.cropImageStyle = computed(() => {
      const c = store.crop;
      const s = c.natW && c.natH ? coverScale(c.natW, c.natH, c.view) * c.zoom : 1;
      return {
        width: c.natW + "px",
        height: c.natH + "px",
        transform: `translate(${c.x}px, ${c.y}px) scale(${s})`,
        transformOrigin: "0 0",
      };
});

store.cropSamplePx = computed(() => {
      const c = store.crop;
      if (!c.natW || !c.natH) return 0;
      const { side } = cropSourceRect(c.natW, c.natH, c.view, c.zoom, c.x, c.y);
      return Math.round(side);
});

store.charDirty = computed(() => {
      return !store.sameSnapshot(store.charForm, store.charSaved);
});
