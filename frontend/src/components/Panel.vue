<template>
<aside class="panel" :class="{collapsed: panelCollapsed}" v-if="activeSession">
    <div class="panel-inner">
      <!-- 面板里没有标题行、也没有关闭键：开关只有一个，就在顶栏最右那一格，
           位置不随面板开合变化（见 10.46）。所以标签栏是面板最上面的一行 -->
      <!-- 标签栏放在滚动容器**外面**：面板内容一长，滚轮往下滚时标签会被顶出视野、
           得再滚回顶部才能切标签。放在外面就永远贴在面板顶部。
           （整个 aside 本来就是 v-if="activeSession"，这里不必再判一次） -->
      <div class="panel-tabs">
        <button class="panel-tab" :class="{on: panelTab === 'gen'}"
                @click="panelTab = 'gen'">生成要求<span v-if="genDirty" class="tab-dot"></span></button>
        <!-- 世界设定是全局的，三种模式都用得上（自由情境也发生在某个世界里），所以不判模式 -->
        <button class="panel-tab" :class="{on: panelTab === 'world'}"
                @click="panelTab = 'world'">世界设定<span v-if="worldDirty" class="tab-dot"></span></button>
        <button v-if="activeSession.character" class="panel-tab" :class="{on: panelTab === 'char'}"
                @click="panelTab = 'char'">角色设定<span v-if="charDirty" class="tab-dot"></span></button>
        <button v-if="activeSession.character" class="panel-tab" :class="{on: panelTab === 'profile'}"
                @click="panelTab = 'profile'">我的设定<span v-if="profileDirty" class="tab-dot"></span></button>
        <button v-if="memoryScope" class="panel-tab" :class="{on: panelTab === 'memory'}"
                @click="panelTab = 'memory'">{{ memoryScope.label }}<span v-if="memoryDirty" class="tab-dot"></span></button>
      </div>
      <div class="panel-body">
        <div class="panel-tab-pane" v-show="panelTab === 'gen'">
          <div v-for="f in fieldsOf(activeSession.mode)" :key="f.key" class="field">
            <span class="field-label">{{ f.label }}</span>
            <div v-if="f.type === 'radio'" class="radio-row">
              <label v-for="opt in f.options" :key="opt[0]" class="radio-item" :class="{on: genForm[f.key] === opt[0]}">
                <input type="radio" :name="f.key" :value="opt[0]" v-model="genForm[f.key]">{{ opt[1] }}
              </label>
            </div>
            <div v-else-if="f.type === 'tags'" class="tags-box">
              <div class="tag-chips">
                <span v-for="p in f.presets" :key="p" class="chip-btn"
                      :class="{on: (genForm[f.key] || []).includes(p)}" @click="toggleTag(f.key, p)">{{ p }}</span>
              </div>
              <div class="tag-custom">
                <span v-for="t in customTags(f)" :key="t" class="tag">{{ t }}<button class="tag-x" @click="removeTag(f.key, t)">&times;</button></span>
                <input class="tag-input" v-model="tagDraft[f.key]" :placeholder="f.placeholder"
                       :maxlength="f.max" @keydown.enter.prevent="addTag(f.key)" @blur="addTag(f.key)">
              </div>
            </div>
            <div v-else class="input-wrap">
              <div class="counted">
                <textarea v-if="f.type === 'textarea'" v-model="genForm[f.key]" rows="2"
                          :maxlength="f.max" :placeholder="f.placeholder"></textarea>
                <input v-else type="text" v-model="genForm[f.key]" :maxlength="f.max" :placeholder="f.placeholder">
                <span class="char-count" :class="{near: isNear(genForm[f.key], f.max), inline: f.type !== 'textarea'}">{{ len(genForm[f.key]) }}/{{ f.max }}</span>
              </div>
              <button v-if="genForm[f.key]" class="clear-btn" title="清空这一栏" tabindex="-1"
                      @click="genForm[f.key] = ''">✕</button>
            </div>
            <span v-if="f.hint" class="field-hint">{{ f.hint }}</span>
          </div>
        </div>
        <!-- 世界设定：全局一份，三种模式都注入。名称只给自己辨认、**不进提示词**；
             描述 / 规则 / 词库会写进提示词（位置在角色设定之前），所以都带限额与计数 -->
        <div class="panel-tab-pane" v-show="panelTab === 'world'">
          <label class="field">世界名称
            <div class="counted">
              <input v-model="worldForm.name" type="text" :maxlength="limits.world_name"
                     placeholder="只用于自己辨认，不发给模型">
              <span class="char-count inline"
                    :class="{near: isNear(worldForm.name, limits.world_name)}">{{ len(worldForm.name) }}/{{ limits.world_name }}</span>
            </div>
          </label>
          <label class="field">描述
            <div class="counted">
              <textarea v-model="worldForm.description" rows="4" :maxlength="limits.world_description"
                        placeholder="这个世界的详细信息：地理、时代、势力、氛围…"></textarea>
              <span class="char-count"
                    :class="{near: isNear(worldForm.description, limits.world_description)}">{{ len(worldForm.description) }}/{{ limits.world_description }}</span>
            </div>
          </label>
          <label class="field">规则
            <div class="counted">
              <textarea v-model="worldForm.rules" rows="4" :maxlength="limits.world_rules"
                        placeholder="独属于这个世界的规则：力量体系、禁忌、铁律…"></textarea>
              <span class="char-count"
                    :class="{near: isNear(worldForm.rules, limits.world_rules)}">{{ len(worldForm.rules) }}/{{ limits.world_rules }}</span>
            </div>
          </label>
          <div class="field">
            <span class="field-label">词库</span>
            <div v-for="(t, i) in worldForm.terms" :key="i" class="term-row">
              <div class="term-head">
                <span class="term-index">词条 {{ i + 1 }}</span>
                <button type="button" class="term-del" title="删除这一条"
                        @click="removeTerm(i)">删除</button>
              </div>
              <div class="counted">
                <input v-model="t.term" type="text" :maxlength="limits.world_term" placeholder="专有名词">
                <span class="char-count inline"
                      :class="{near: isNear(t.term, limits.world_term)}">{{ len(t.term) }}/{{ limits.world_term }}</span>
              </div>
              <div class="counted">
                <textarea v-model="t.meaning" rows="2" :maxlength="limits.world_term_meaning"
                          placeholder="它的含义（可留空）"></textarea>
                <span class="char-count"
                      :class="{near: isNear(t.meaning, limits.world_term_meaning)}">{{ len(t.meaning) }}/{{ limits.world_term_meaning }}</span>
              </div>
            </div>
            <button type="button" class="ghost-btn full"
                    :disabled="worldForm.terms.length >= limits.world_terms_max"
                    @click="addTerm">＋ 添加词条</button>
            <p class="hint">
              最多 {{ limits.world_terms_max }} 条，按这里的顺序注入；名词留空的行在保存时自动丢弃。
            </p>
          </div>
          <p class="hint">名称只给自己看；描述、规则、词库会写进三种模式的提示词（在角色设定之前）。</p>
        </div>
        <div v-if="activeSession.character" class="panel-tab-pane"
             v-show="panelTab === 'char'">
          <div class="avatar-pick">
            <span class="avatar xl">
              <img v-if="charForm.avatar" :src="charForm.avatar" alt="">
              <template v-else>{{ (charForm.name || "?").slice(0, 1) }}</template>
            </span>
            <div class="avatar-pick-actions">
              <label class="ghost-btn file-btn">{{ charForm.avatar ? "更换头像" : "上传头像" }}
                <input type="file" accept="image/*" @change="pickAvatar($event, 'panel')">
              </label>
              <button v-if="charForm.avatar" class="ghost-btn" @click="clearAvatar('panel')">移除头像</button>
            </div>
          </div>
          <p v-if="avatarError" class="avatar-error">{{ avatarError }}</p>
          <div class="bg-pick">
            <div class="bg-pick-head">
              <span class="field-label">对话背景</span>
              <span class="hint">{{ (charForm.backgrounds || []).length }} / {{ bgMax }}</span>
            </div>
            <div class="bg-thumbs">
              <div v-for="(bg, i) in charForm.backgrounds" :key="i" class="bg-thumb"
                   :class="{ dragging: bgDragging('panel', i), over: bgDropTarget('panel', i) }"
                   draggable="true" title="拖动可调整顺序"
                   @dragstart="bgDragStart($event, 'panel', i)"
                   @dragover.prevent="bgDragOver($event, 'panel', i)"
                   @drop.prevent="bgDrop($event, 'panel', i)"
                   @dragend="bgDragEnd">
                <img :src="bg" alt="" draggable="false">
                <span class="bg-num">{{ i + 1 }}</span>
                <button type="button" class="bg-del" title="移除这张" @click="removeBackground('panel', i)">×</button>
                <div class="bg-move">
                  <button type="button" :disabled="i === 0" title="前移"
                          @click="moveBackground('panel', i, i - 1)">‹</button>
                  <button type="button" :disabled="i === (charForm.backgrounds || []).length - 1" title="后移"
                          @click="moveBackground('panel', i, i + 1)">›</button>
                </div>
              </div>
              <label v-if="(charForm.backgrounds || []).length < bgMax"
                     class="bg-add" :class="{disabled: bgBusy}">
                {{ bgBusy ? "处理中…" : "＋" }}
                <input type="file" accept="image/*" multiple :disabled="bgBusy"
                       @change="addBackgrounds($event, 'panel')">
              </label>
            </div>
            <p v-if="bgError" class="avatar-error">{{ bgError }}</p>
          </div>
          <label class="field">姓名
            <div class="counted">
              <input v-model="charForm.name" type="text" :maxlength="limits.name">
              <span class="char-count inline" :class="{near: isNear(charForm.name, limits.name)}">{{ len(charForm.name) }}/{{ limits.name }}</span>
            </div>
          </label>
          <label class="field">外观
            <div class="counted">
              <textarea v-model="charForm.appearance" rows="3" :maxlength="limits.appearance"
                        placeholder="年龄、身形、衣着、标志性特征"></textarea>
              <span class="char-count" :class="{near: isNear(charForm.appearance, limits.appearance)}">{{ len(charForm.appearance) }}/{{ limits.appearance }}</span>
            </div>
          </label>
          <template v-if="!charLocked">
            <label class="field">性格
              <div class="counted">
                <textarea v-model="charForm.personality" rows="3" :maxlength="limits.personality"></textarea>
                <span class="char-count" :class="{near: isNear(charForm.personality, limits.personality)}">{{ len(charForm.personality) }}/{{ limits.personality }}</span>
              </div>
            </label>
            <label class="field">语言风格
              <div class="counted">
                <textarea v-model="charForm.speech_style" rows="3" :maxlength="limits.speech_style"
                          placeholder="口癖、语气、用词习惯"></textarea>
                <span class="char-count" :class="{near: isNear(charForm.speech_style, limits.speech_style)}">{{ len(charForm.speech_style) }}/{{ limits.speech_style }}</span>
              </div>
            </label>
            <label class="field">背景故事
              <div class="counted">
                <textarea v-model="charForm.backstory" rows="4" :maxlength="limits.backstory"></textarea>
                <span class="char-count" :class="{near: isNear(charForm.backstory, limits.backstory)}">{{ len(charForm.backstory) }}/{{ limits.backstory }}</span>
              </div>
            </label>
          </template>
          <div v-else class="locked-box">
            <div class="locked-title">🔒 性格 / 语言风格 / 背景故事 已锁定</div>
            <p class="hint">这三项照常参与生成，但不会显示，可以在对话中慢慢了解。</p>
            <button class="ghost-btn" @click="unlockCharacter('panel')">公开角色设定</button>
          </div>
        </div>
        <!-- 我的设定：用户本人。姓名与身份会进角色两模式的提示词，头像与名字显示在
             自己消息的气泡旁；自由情境模式用不到它，所以那个模式下不出现这个标签 -->
        <div v-if="activeSession.character" class="panel-tab-pane" v-show="panelTab === 'profile'">
          <!-- 预设：选中即把那一份设定填进表单（不直接覆盖已保存的当前设定，
               仍走底部"保存当前配置"），所以载入后会出现"未保存"提示 -->
          <div class="preset-row">
            <select class="preset-select" v-model="presetPick" @change="loadPreset">
              <option value="">从预设载入…</option>
              <option v-for="p in profilePresets" :key="p.id" :value="p.id">
                {{ p.name }}{{ p.identity ? " · " + p.identity : "" }}
              </option>
            </select>
            <button class="ghost-btn" :disabled="!profileForm.name.trim()"
                    title="把当前这几项存成一条预设，之后可从下拉里一键载入"
                    @click="savePreset">存为预设</button>
            <button v-if="presetPick" class="ghost-btn" title="删除选中的这条预设"
                    @click="removePreset">删除预设</button>
          </div>
          <p v-if="presetError" class="avatar-error">{{ presetError }}</p>
          <p v-if="!profilePresets.length" class="hint">
            还没有预设：填好下面几项后点「存为预设」，以后就能从下拉里一键载入（含头像）。
          </p>
          <div class="avatar-pick">
            <span class="avatar xl">
              <img v-if="profileForm.avatar" :src="profileForm.avatar" alt="">
              <template v-else>{{ (profileForm.name || "我").slice(0, 1) }}</template>
            </span>
            <div class="avatar-pick-actions">
              <label class="ghost-btn file-btn">{{ profileForm.avatar ? "更换头像" : "上传头像" }}
                <input type="file" accept="image/*" @change="pickAvatar($event, 'profile')">
              </label>
              <button v-if="profileForm.avatar" class="ghost-btn" @click="clearAvatar('profile')">移除头像</button>
            </div>
          </div>
          <p v-if="avatarError" class="avatar-error">{{ avatarError }}</p>
          <label class="field">名字
            <div class="counted">
              <input v-model="profileForm.name" type="text" :maxlength="limits.user_name"
                     placeholder="角色对你的称呼">
              <span class="char-count inline" :class="{near: isNear(profileForm.name, limits.user_name)}">{{ len(profileForm.name) }}/{{ limits.user_name }}</span>
            </div>
          </label>
          <label class="field">身份
            <div class="counted">
              <textarea v-model="profileForm.identity" rows="3" :maxlength="limits.identity"
                        placeholder="你是谁：如「被卷入事件的见习侦探」"></textarea>
              <span class="char-count" :class="{near: isNear(profileForm.identity, limits.identity)}">{{ len(profileForm.identity) }}/{{ limits.identity }}</span>
            </div>
          </label>
          <label class="field">外观
            <div class="counted">
              <textarea v-model="profileForm.appearance" rows="3" :maxlength="limits.user_appearance"
                        placeholder="年龄、身形、衣着等"></textarea>
              <span class="char-count" :class="{near: isNear(profileForm.appearance, limits.user_appearance)}">{{ len(profileForm.appearance) }}/{{ limits.user_appearance }}</span>
            </div>
          </label>
          <p class="hint">「身份」与「外观」会写进角色两模式的提示词，让角色知道你是谁；自由情境模式不使用这些内容。</p>
        </div>
        <div v-if="memoryScope" class="panel-tab-pane" v-show="panelTab === 'memory'">
          <p class="memory-meta">
            已归档 {{ memoryData.message_count }} 条消息<template v-if="memoryData.updated_at"> · 更新于 {{ memoryData.updated_at }}</template>
            <a class="refresh-link" @click="loadMemory">刷新</a>
            <span v-if="memoryData.compress_failed" class="warn-text">上次压缩失败</span>
          </p>
          <div class="counted">
            <textarea class="memory-text" v-model="memoryText" rows="10" :maxlength="limits.memory"
                      placeholder="暂无记忆，随对话自动沉淀"></textarea>
            <span class="char-count" :class="{near: isNear(memoryText, limits.memory)}">{{ len(memoryText) }}/{{ limits.memory }}</span>
          </div>
        </div>
      </div>
      <!-- 保存与"未保存 / 还原"常驻在面板底部（滚动容器之外）：内容再长也不会跟着滚走，
           也不会被内容量挤位置。三个标签共用这一个按钮，保存谁由当前标签决定 -->
      <div class="panel-footer">
        <div v-if="activeTabDirty" class="panel-tab-actions">
          <span class="dirty-flag">未保存</span>
          <button class="revert-btn" :class="{armed: revertArm[panelTab]}"
                  :title="revertArm[panelTab] ? '再点一次即还原到上次保存的内容' : '还原到上次保存的内容'"
                  @click="armRevert(panelTab)">{{ revertArm[panelTab] ? "确认还原？" : "还原" }}</button>
        </div>
        <button class="primary-btn full" :disabled="saveDisabled" @click="saveCurrentTab">保存当前配置</button>
        <p class="hint">保存后立即生效，只影响后续生成</p>
      </div>
    </div>
  </aside>
</template>

<script setup>
import { toRefs } from "vue";
import { store } from "../store.js";

// 模板用到的状态与计算属性（toRefs 后模板里仍是裸名字，读写都保持响应式）
const {
  activeSession,
  activeTabDirty,
  avatarError,
  bgBusy,
  bgError,
  bgMax,
  charDirty,
  charForm,
  charLocked,
  genDirty,
  genForm,
  limits,
  memoryData,
  memoryDirty,
  memoryScope,
  memoryText,
  panelCollapsed,
  panelTab,
  presetError,
  presetPick,
  profileDirty,
  profileForm,
  profilePresets,
  revertArm,
  saveDisabled,
  tagDraft,
  worldDirty,
  worldForm,
} = toRefs(store);

// 模板用到的方法（函数不是响应式的，直接解构）
const {
  addBackgrounds,
  addTag,
  addTerm,
  armRevert,
  bgDragEnd,
  bgDragOver,
  bgDragStart,
  bgDragging,
  bgDrop,
  bgDropTarget,
  clearAvatar,
  customTags,
  fieldsOf,
  isNear,
  len,
  loadMemory,
  loadPreset,
  moveBackground,
  pickAvatar,
  removeBackground,
  removePreset,
  removeTag,
  removeTerm,
  saveCurrentTab,
  savePreset,
  toggleTag,
  unlockCharacter,
} = store;
</script>
