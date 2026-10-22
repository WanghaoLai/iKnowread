<template>
  <Teleport to="body">
    <aside
        v-if="detail.visible && detail.item"
        ref="root"
        class="highlight-detail"
        :style="{ left: `${detail.left}px`, top: `${detail.top}px` }"
        role="dialog"
        aria-label="高亮备注"
        @pointerdown.stop
    >
      <header>
        <div><span></span><strong>高亮备注</strong></div>
        <button type="button" aria-label="关闭高亮备注" @click="$emit('close')"><el-icon><Close /></el-icon></button>
      </header>
      <blockquote>“{{ detail.item.selected_text }}”</blockquote>
      <template v-if="detail.editing">
        <textarea
            :value="detail.remark"
            maxlength="12000"
            rows="5"
            placeholder="添加你的理解、疑问，或保留 AI 解释"
            @input="$emit('update:remark', eventValue($event))"
        ></textarea>
        <div class="highlight-detail-edit-actions">
          <span>{{ detail.remark.length }} / 12000</span>
          <button type="button" @click="$emit('cancel-edit')">取消</button>
          <button type="button" class="primary" :disabled="detail.saving" @click="$emit('save')">
            {{ detail.saving ? '保存中…' : '保存' }}
          </button>
        </div>
      </template>
      <p v-else class="highlight-detail-remark">{{ detail.item.remark || '暂无备注' }}</p>
      <footer>
        <span>{{ detail.item.model || '手动高亮' }}</span>
        <div>
          <button type="button" @click="$emit('locate')"><el-icon><Location /></el-icon>定位</button>
          <button type="button" @click="$emit('edit')"><el-icon><Edit /></el-icon>编辑</button>
          <button type="button" class="danger" @click="$emit('remove', detail.item)"><el-icon><Delete /></el-icon>删除</button>
        </div>
      </footer>
    </aside>
  </Teleport>
</template>

<script setup>
import { ref } from 'vue'
import { Close, Delete, Edit, Location } from '@element-plus/icons-vue'

defineProps({ detail: { type: Object, required: true } })
defineEmits(['close', 'edit', 'cancel-edit', 'save', 'locate', 'remove', 'update:remark'])

const root = ref()
const eventValue = event => event.target instanceof HTMLTextAreaElement ? event.target.value : ''
defineExpose({ element: root })
</script>

<style scoped>
.highlight-detail {
  position: fixed;
  z-index: 4010;
  width: min(370px, calc(100vw - 24px));
  max-height: min(520px, calc(100vh - 24px));
  display: flex;
  flex-direction: column;
  overflow: hidden;
  color: var(--ik-text);
  background: rgba(255, 255, 255, .98);
  border: 1px solid rgba(224, 172, 0, .38);
  border-radius: 14px;
  box-shadow: 0 16px 44px rgba(0, 56, 157, .2);
  backdrop-filter: blur(10px);
  animation: highlight-detail-in .16s ease-out;
}
header, footer { display: flex; align-items: center; justify-content: space-between; gap: 10px; }
header {
  padding: 12px 14px;
  background: linear-gradient(135deg, #fff9e8, #f3fafc);
  border-bottom: 1px solid #f0e6c2;
}
header div { display: flex; align-items: center; gap: 8px; }
header div span { width: 18px; height: 9px; border-radius: 3px; background: rgba(255, 205, 44, .78); }
button { border: 0; background: transparent; color: var(--ik-blue); font: inherit; cursor: pointer; }
header > button { display: inline-flex; padding: 4px; color: var(--ik-text-sub); }
blockquote {
  flex-shrink: 0;
  margin: 12px 14px 0;
  padding: 9px 11px;
  overflow: hidden;
  color: var(--ik-text-sub);
  font-size: 12px;
  line-height: 1.55;
  white-space: nowrap;
  text-overflow: ellipsis;
  background: #fffaf0;
  border-left: 3px solid #f0b000;
  border-radius: 4px 8px 8px 4px;
}
.highlight-detail-remark {
  min-height: 54px;
  margin: 0;
  padding: 14px;
  overflow-y: auto;
  color: #33475e;
  font-size: 14px;
  line-height: 1.7;
  white-space: pre-wrap;
  overflow-wrap: anywhere;
}
textarea {
  min-height: 100px;
  margin: 14px 14px 0;
  padding: 9px 10px;
  resize: vertical;
  color: var(--ik-text);
  font: inherit;
  font-size: 13px;
  line-height: 1.55;
  border: 1px solid #decf9e;
  border-radius: 8px;
  outline: none;
}
textarea:focus { border-color: #d59b00; box-shadow: 0 0 0 2px rgba(213, 155, 0, .1); }
.highlight-detail-edit-actions { display: flex; align-items: center; justify-content: flex-end; gap: 10px; padding: 8px 14px 12px; }
.highlight-detail-edit-actions span { margin-right: auto; color: var(--ik-text-sub); font-size: 10px; }
.highlight-detail-edit-actions button.primary { padding: 6px 11px; color: #fff; background: var(--ik-gradient); border-radius: 7px; }
footer { padding: 9px 14px; color: var(--ik-text-sub); font-size: 11px; border-top: 1px solid var(--ik-border); }
footer > span { min-width: 0; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
footer div { display: flex; flex-shrink: 0; align-items: center; gap: 12px; }
footer button { display: inline-flex; align-items: center; gap: 4px; padding: 3px 0; font-size: 12px; }
footer button.danger { color: var(--el-color-danger); }
button:disabled { opacity: .6; cursor: wait; }
@media (max-width: 520px) { footer { align-items: flex-start; flex-direction: column; } }
@keyframes highlight-detail-in {
  from { opacity: 0; transform: translateY(5px) scale(.98); }
  to { opacity: 1; transform: translateY(0) scale(1); }
}
</style>
