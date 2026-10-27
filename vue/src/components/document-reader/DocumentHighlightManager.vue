<template>
  <aside class="reader-highlight-manager" aria-label="高亮管理">
    <header>
      <div><strong>高亮管理</strong><span>{{ items.length }} 条</span></div>
      <button type="button" aria-label="关闭高亮管理" @click="$emit('close')"><el-icon><Close /></el-icon></button>
    </header>
    <div v-if="loading" class="reader-highlight-empty">
      <el-icon class="is-loading"><Loading /></el-icon>正在加载高亮…
    </div>
    <div v-else-if="!items.length" class="reader-highlight-empty">选择文档内容后即可保存高亮</div>
    <template v-else>
      <article v-for="highlight in items" :key="highlight.id" class="reader-highlight-item">
        <button type="button" class="reader-highlight-locate" @click="$emit('locate', highlight)">
          <span>{{ highlight.source_anchor.page ? `第 ${highlight.source_anchor.page} 页` : '文档内容' }} · {{ formatTime(highlight.created_at) }}</span>
          <strong>{{ highlight.selected_text }}</strong>
          <p>{{ highlight.remark || '暂无备注' }}</p>
        </button>
        <div v-if="!readOnly">
          <button type="button" @click="$emit('edit', highlight)"><el-icon><Edit /></el-icon>编辑备注</button>
          <button type="button" class="danger" @click="$emit('remove', highlight)"><el-icon><Delete /></el-icon>删除</button>
        </div>
      </article>
    </template>
  </aside>
</template>

<script setup>
import { computed } from 'vue'
import { Close, Delete, Edit, Loading } from '@element-plus/icons-vue'

const props = defineProps({
  highlights: { type: Array, required: true },
  loading: { type: Boolean, default: false },
  readOnly: { type: Boolean, default: false },
})
defineEmits(['close', 'locate', 'edit', 'remove'])
const items = computed(() => /** @type {any[]} */ (props.highlights))

const formatTime = value => {
  const date = new Date(value)
  if (Number.isNaN(date.getTime())) return ''
  return new Intl.DateTimeFormat('zh-CN', {
    month: '2-digit', day: '2-digit', hour: '2-digit', minute: '2-digit', hour12: false,
  }).format(date)
}
</script>

<style scoped>
.reader-highlight-manager {
  position: absolute;
  z-index: 22;
  top: 58px;
  right: 14px;
  width: min(390px, calc(100% - 28px));
  max-height: min(600px, calc(100% - 76px));
  overflow-y: auto;
  color: var(--ik-text);
  background: rgba(255, 255, 255, .98);
  border: 1px solid rgba(224, 172, 0, .32);
  border-radius: 12px;
  box-shadow: 0 14px 38px rgba(29, 65, 95, .2);
}
header {
  position: sticky;
  z-index: 2;
  top: 0;
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 12px 14px;
  background: linear-gradient(135deg, #fffaf0, #f5fbfd);
  border-bottom: 1px solid #f0e7c7;
}
header div { display: flex; align-items: center; gap: 8px; }
header span { color: var(--ik-text-sub); font-size: 12px; }
button { border: 0; background: transparent; color: inherit; font: inherit; cursor: pointer; }
header > button { display: inline-flex; padding: 4px; color: var(--ik-text-sub); }
.reader-highlight-empty { padding: 32px 16px; color: var(--ik-text-sub); text-align: center; }
.reader-highlight-empty .el-icon { margin-right: 6px; }
.reader-highlight-item { padding: 12px 14px; border-bottom: 1px solid #edf3f6; }
.reader-highlight-item:last-child { border-bottom: 0; }
.reader-highlight-item:hover { background: #fffdf6; }
.reader-highlight-locate { display: block; width: 100%; padding: 0; text-align: left; }
.reader-highlight-locate span { color: #a86e00; font-size: 11px; font-weight: 700; }
.reader-highlight-locate strong, .reader-highlight-locate p { display: block; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.reader-highlight-locate strong { margin-top: 4px; color: #33475e; font-size: 13px; }
.reader-highlight-locate p { margin: 5px 0 0; color: var(--ik-text-sub); font-size: 12px; }
.reader-highlight-item > div { display: flex; justify-content: flex-end; gap: 14px; margin-top: 9px; }
.reader-highlight-item > div button { display: inline-flex; align-items: center; gap: 4px; color: var(--ik-blue); font-size: 12px; }
.reader-highlight-item > div button.danger { color: var(--el-color-danger); }
@media (max-width: 900px) { .reader-highlight-manager { top: 100px; } }
</style>
