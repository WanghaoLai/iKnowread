<template>
  <aside class="reader-search-results" aria-label="文内搜索结果">
    <header>
      <strong>搜索结果</strong>
      <span v-if="!search.loading">{{ search.results.length }} 处</span>
      <button type="button" aria-label="关闭搜索结果" @click="$emit('close')"><el-icon><Close /></el-icon></button>
    </header>
    <div v-if="search.loading" class="reader-search-state"><el-icon class="is-loading"><Loading /></el-icon>正在搜索全文…</div>
    <div v-else-if="search.error" class="reader-search-state error">{{ search.error }}</div>
    <div v-else-if="!search.results.length" class="reader-search-state">没有找到匹配内容</div>
    <template v-else>
      <button
          v-for="(result, index) in search.results"
          :key="`${result.anchor.page || 0}-${result.anchor.selector.position.start}-${index}`"
          type="button"
          class="reader-search-result"
          @click="$emit('select', result)"
      >
        <span>{{ result.anchor.page ? `第 ${result.anchor.page} 页` : '文档内容' }}</span>
        <p>{{ result.snippet }}</p>
      </button>
    </template>
  </aside>
</template>

<script setup>
import { Close, Loading } from '@element-plus/icons-vue'

defineProps({ search: { type: Object, required: true } })
defineEmits(['close', 'select'])
</script>

<style scoped>
.reader-search-results {
  position: absolute;
  z-index: 20;
  top: 58px;
  right: 14px;
  width: min(380px, calc(100% - 28px));
  max-height: min(520px, calc(100% - 76px));
  overflow-y: auto;
  border: 1px solid var(--ik-border);
  border-radius: 12px;
  background: rgba(255, 255, 255, .98);
  box-shadow: 0 14px 38px rgba(29, 65, 95, .2);
}
header {
  position: sticky;
  z-index: 1;
  top: 0;
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 12px 14px;
  color: #24384c;
  background: #f5fbfd;
  border-bottom: 1px solid var(--ik-border);
}
header span { color: var(--ik-text-sub); font-size: 12px; }
header button {
  display: inline-flex;
  margin-left: auto;
  padding: 4px;
  border: 0;
  color: var(--ik-text-sub);
  background: transparent;
  cursor: pointer;
}
.reader-search-state { padding: 28px 16px; color: var(--ik-text-sub); text-align: center; }
.reader-search-state.error { color: var(--el-color-danger); }
.reader-search-result {
  display: block;
  width: 100%;
  padding: 11px 14px;
  border: 0;
  border-bottom: 1px solid #edf3f6;
  color: inherit;
  background: transparent;
  text-align: left;
  cursor: pointer;
}
.reader-search-result:hover, .reader-search-result:focus-visible { background: #edf9fb; outline: none; }
.reader-search-result span { color: var(--ik-cyan-deep); font-size: 11px; font-weight: 700; }
.reader-search-result p { margin: 4px 0 0; color: var(--ik-text); font-size: 13px; line-height: 1.55; }
@media (max-width: 900px) { .reader-search-results { top: 100px; } }
</style>
