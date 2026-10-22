<template>
  <Teleport to="body">
    <aside
        v-if="explain.visible"
        ref="root"
        class="selection-explain"
        :style="{ left: `${explain.left}px`, top: `${explain.top}px` }"
        role="dialog"
        aria-label="选中文字解释"
        @pointerdown.stop
    >
      <header class="selection-explain-header">
        <div class="selection-explain-title"><span class="selection-explain-mark">AI</span><span>选文解释</span></div>
        <span class="selection-model" :title="explain.model || ''">{{ explain.model || 'AI 解释可作为高亮备注' }}</span>
        <button type="button" class="selection-icon-button" aria-label="关闭解释" @click="$emit('close')"><el-icon><Close /></el-icon></button>
      </header>
      <div class="selection-quote" :title="explain.selection">“{{ explain.selection }}”</div>
      <div v-if="explain.loading" class="selection-explain-loading" role="status">
        <el-icon class="is-loading"><Loading /></el-icon><span>正在理解所选内容…</span>
      </div>
      <div v-else-if="explain.error" class="selection-explain-error">
        <span>{{ explain.error }}</span>
        <button v-if="explain.needsConfig" type="button" @click="$emit('configure')">前往 API配置</button>
        <button v-else type="button" @click="$emit('retry')">重新解释</button>
      </div>
      <div v-else class="selection-explain-answer">{{ explain.answer }}</div>

      <div v-if="selectionHighlight.open && !selectionHighlight.saved" class="selection-note-compose selection-highlight-compose">
        <label for="selection-highlight-remark">高亮备注（可选）</label>
        <textarea
            id="selection-highlight-remark"
            :value="selectionHighlight.remark"
            maxlength="12000"
            rows="4"
            placeholder="AI 解释会自动填入，也可以修改为自己的理解"
            @input="$emit('update-highlight-remark', eventValue($event))"
        ></textarea>
        <div>
          <span>{{ selectionHighlight.remark.length }} / 12000</span>
          <button type="button" @click="$emit('cancel-highlight')">取消</button>
          <button type="button" class="primary" :disabled="selectionHighlight.saving" @click="$emit('save-highlight')">
            {{ selectionHighlight.saving ? '保存中…' : '保存高亮' }}
          </button>
        </div>
      </div>

      <div v-if="explain.noteOpen && !explain.noteSaved" class="selection-note-compose">
        <label for="selection-note-remark">添加个人备注（可选）</label>
        <textarea
            id="selection-note-remark"
            :value="explain.noteRemark"
            maxlength="5000"
            rows="3"
            placeholder="记录你的理解、疑问或下一步行动"
            @input="$emit('update-note-remark', eventValue($event))"
        ></textarea>
        <div>
          <span>{{ explain.noteRemark.length }} / 5000</span>
          <button type="button" @click="$emit('cancel-note')">取消</button>
          <button type="button" class="primary" :disabled="explain.noteSaving" @click="$emit('save-note')">
            {{ explain.noteSaving ? '保存中…' : '保存笔记' }}
          </button>
        </div>
      </div>

      <footer v-if="explain.sourceAnchor" class="selection-explain-footer">
        <div class="selection-footer-actions">
          <button v-if="selectionHighlight.saved" type="button" class="highlight-saved" @click="$emit('show-highlight')">
            <el-icon><CollectionTag /></el-icon>已高亮 · 查看
          </button>
          <template v-else>
            <button type="button" :disabled="selectionHighlight.saving" @click="$emit('save-highlight')">
              <el-icon><CollectionTag /></el-icon>{{ selectionHighlight.saving ? '保存中…' : '保存高亮' }}
            </button>
            <button type="button" :disabled="selectionHighlight.saving" @click="$emit('toggle-highlight')">
              {{ selectionHighlight.open ? '收起备注' : '备注后高亮' }}
            </button>
          </template>
          <button v-if="explain.answer" type="button" @click="$emit('copy')">
            <el-icon><CopyDocument /></el-icon>{{ explain.copied ? '已复制' : '复制' }}
          </button>
          <button v-if="explain.answer && explain.noteSaved" type="button" class="note-saved" @click="$emit('show-notes')">
            <el-icon><Notebook /></el-icon>已加入 · 查看
          </button>
          <template v-else-if="explain.answer">
            <button type="button" :disabled="explain.noteSaving" @click="$emit('save-note')">
              <el-icon><Notebook /></el-icon>{{ explain.noteSaving ? '添加中…' : '一键添加' }}
            </button>
            <button type="button" :disabled="explain.noteSaving" @click="$emit('toggle-note')">
              {{ explain.noteOpen ? '收起备注' : '备注后添加' }}
            </button>
          </template>
        </div>
      </footer>
    </aside>
  </Teleport>
</template>

<script setup>
import { ref } from 'vue'
import { Close, CollectionTag, CopyDocument, Loading, Notebook } from '@element-plus/icons-vue'

defineProps({
  explain: { type: Object, required: true },
  selectionHighlight: { type: Object, required: true },
})
defineEmits([
  'close', 'configure', 'retry', 'save-highlight', 'cancel-highlight', 'toggle-highlight',
  'show-highlight', 'copy', 'save-note', 'cancel-note', 'toggle-note', 'show-notes',
  'update-highlight-remark', 'update-note-remark',
])

const root = ref()
const eventValue = event => event.target instanceof HTMLTextAreaElement ? event.target.value : ''
defineExpose({ element: root })
</script>

<style scoped>
.selection-explain {
  position: fixed;
  z-index: 4000;
  width: min(380px, calc(100vw - 24px));
  max-height: min(560px, calc(100vh - 24px));
  display: flex;
  flex-direction: column;
  overflow: hidden;
  color: var(--ik-text);
  background: rgba(255, 255, 255, .98);
  border: 1px solid rgba(0, 150, 180, .24);
  border-radius: 14px;
  box-shadow: 0 16px 44px rgba(0, 56, 157, .2);
  backdrop-filter: blur(10px);
  animation: selection-explain-in .16s ease-out;
}
.selection-explain-header, .selection-explain-footer { display: flex; align-items: center; justify-content: space-between; gap: 12px; }
.selection-explain-header { padding: 12px 14px; border-bottom: 1px solid var(--ik-border); background: linear-gradient(135deg, #f3f9ff, #edfcfb); }
.selection-explain-title { display: flex; align-items: center; gap: 8px; flex-shrink: 0; color: #24384c; font-size: 14px; font-weight: 700; }
.selection-explain-mark { display: inline-flex; align-items: center; justify-content: center; width: 28px; height: 22px; color: #fff; font-size: 11px; letter-spacing: .3px; border-radius: 7px; background: var(--ik-gradient); }
.selection-icon-button, .selection-explain-footer button, .selection-explain-error button { border: 0; background: transparent; color: var(--ik-blue); font: inherit; cursor: pointer; }
.selection-icon-button { display: inline-flex; padding: 5px; border-radius: 7px; color: var(--ik-text-sub); }
.selection-icon-button:hover { background: rgba(0, 69, 183, .08); }
.selection-quote { flex-shrink: 0; margin: 12px 14px 0; padding: 9px 11px; overflow: hidden; color: var(--ik-text-sub); font-size: 12px; line-height: 1.55; white-space: nowrap; text-overflow: ellipsis; background: #f5f9fc; border-left: 3px solid var(--ik-cyan); border-radius: 4px 8px 8px 4px; }
.selection-explain-loading, .selection-explain-error, .selection-explain-answer { min-height: 80px; padding: 14px; font-size: 14px; line-height: 1.75; }
.selection-explain-loading { display: flex; align-items: center; justify-content: center; gap: 9px; color: var(--ik-cyan-deep); }
.selection-explain-error { display: flex; flex-direction: column; align-items: flex-start; gap: 8px; color: var(--el-color-danger); }
.selection-explain-error button { padding: 0; font-size: 13px; }
.selection-explain-answer { overflow-y: auto; white-space: pre-wrap; overflow-wrap: anywhere; }
.selection-explain-footer { flex-shrink: 0; justify-content: flex-end; padding: 9px 14px; color: var(--ik-text-sub); font-size: 11px; border-top: 1px solid var(--ik-border); }
.selection-model { flex: 1; min-width: 0; overflow: hidden; color: var(--ik-text-sub); font-size: 11px; font-weight: 400; text-align: right; text-overflow: ellipsis; white-space: nowrap; }
.selection-footer-actions { flex: 1; display: flex; align-items: center; justify-content: space-evenly; flex-wrap: wrap; gap: 8px 10px; }
.selection-explain-footer button { display: inline-flex; align-items: center; gap: 5px; padding: 4px 0; font-size: 12px; }
.selection-explain-footer button:disabled { opacity: .55; cursor: wait; }
.selection-explain-footer .note-saved { color: #148064; }
.selection-explain-footer .highlight-saved { color: #a86e00; }
.selection-note-compose { flex-shrink: 0; padding: 12px 14px; background: #f7fbfd; border-top: 1px solid var(--ik-border); }
.selection-note-compose label { display: block; margin-bottom: 7px; color: #33475e; font-size: 12px; font-weight: 600; }
.selection-note-compose textarea { width: 100%; min-height: 70px; max-height: 140px; padding: 9px 10px; resize: vertical; color: var(--ik-text); font: inherit; font-size: 13px; line-height: 1.55; background: #fff; border: 1px solid #cfe2ee; border-radius: 8px; outline: none; }
.selection-note-compose textarea:focus { border-color: var(--ik-cyan-deep); box-shadow: 0 0 0 2px rgba(0, 150, 180, .1); }
.selection-note-compose > div { display: flex; align-items: center; justify-content: flex-end; gap: 10px; margin-top: 7px; }
.selection-note-compose > div span { margin-right: auto; color: var(--ik-text-sub); font-size: 10px; }
.selection-note-compose button { padding: 4px 0; color: var(--ik-blue); font: inherit; font-size: 12px; background: transparent; border: 0; cursor: pointer; }
.selection-note-compose button.primary { padding: 6px 10px; color: #fff; background: var(--ik-gradient); border-radius: 7px; }
.selection-note-compose button:disabled { opacity: .6; cursor: wait; }
.selection-highlight-compose { background: #fffdf5; border-top-color: #f0dfaa; }
@media (max-width: 520px) { .selection-footer-actions { width: 100%; justify-content: space-evenly; } }
@keyframes selection-explain-in {
  from { opacity: 0; transform: translateY(5px) scale(.98); }
  to { opacity: 1; transform: translateY(0) scale(1); }
}
</style>
