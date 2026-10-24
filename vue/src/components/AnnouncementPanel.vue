<template>
  <el-popover
    v-model:visible="visible"
    placement="bottom-end"
    :width="420"
    :popper-style="{ maxWidth: 'calc(100vw - 24px)' }"
    trigger="click"
    popper-class="announcement-popover"
    @show="$emit('open')"
  >
    <template #reference>
      <el-badge :is-dot="unreadCount > 0" :hidden="unreadCount === 0" class="notification-badge">
        <button type="button" class="notification-button" :aria-label="notificationLabel">
          <el-icon :size="20"><Bell /></el-icon>
        </button>
      </el-badge>
    </template>

    <section class="notification-panel" aria-label="系统通知">
      <header class="panel-header">
        <div>
          <strong>系统通知</strong>
          <span v-if="unreadCount">{{ unreadCount }} 条未读</span>
        </div>
        <el-button
          v-if="unreadCount"
          link
          type="primary"
          :loading="mutating"
          @click="$emit('read-all')"
        >全部已读</el-button>
      </header>

      <div v-if="loading" class="panel-state" v-loading="true" aria-label="正在加载通知"></div>
      <div v-else-if="error && !items.length" class="panel-state">
        <el-icon><Warning /></el-icon>
        <span>通知加载失败</span>
        <el-button link type="primary" @click="$emit('retry')">重新加载</el-button>
      </div>
      <el-empty v-else-if="!items.length" :image-size="56" description="暂无系统通知" />
      <div v-else class="notification-list">
        <article
          v-for="item in items"
          :key="`${item.id}-${item.published_revision}`"
          class="notification-item"
          :class="{ unread: !item.is_read, expanded: expandedId === item.id }"
        >
          <button type="button" class="notification-summary" @click="toggle(item)">
            <span class="unread-dot" aria-hidden="true"></span>
            <span class="summary-copy">
              <strong>{{ item.title }}</strong>
              <time>{{ formatTime(item.published_at) }}</time>
            </span>
            <el-icon class="expand-icon"><ArrowDown /></el-icon>
          </button>
          <div v-if="expandedId === item.id" class="notification-content markdown-body" v-html="renderMarkdown(item.content)"></div>
        </article>
      </div>
      <p v-if="error && items.length" class="stale-tip">
        <el-icon><Warning /></el-icon> 暂时无法刷新，当前显示上次结果
      </p>
    </section>
  </el-popover>
</template>

<script setup>
import { computed, ref } from 'vue'
import { ArrowDown, Bell, Warning } from '@element-plus/icons-vue'
import { formatTime } from '@/utils/format'
import { renderMarkdown } from '@/utils/markdown'

const props = defineProps({
  items: {
    type: /** @type {import('vue').PropType<Array<{
     * id: number,
     * title: string,
     * content: string,
     * published_revision: number,
     * published_at: string,
     * is_read: boolean,
     * }>>} */ (Array),
    default: () => [],
  },
  unreadCount: { type: Number, default: 0 },
  loading: { type: Boolean, default: false },
  error: { type: Boolean, default: false },
  mutating: { type: Boolean, default: false },
})

const emit = defineEmits(['open', 'read', 'read-all', 'retry'])
const visible = ref(false)
const expandedId = ref(null)
const notificationLabel = computed(() => props.unreadCount
  ? `系统通知，${props.unreadCount} 条未读`
  : '系统通知')

function toggle(item) {
  expandedId.value = expandedId.value === item.id ? null : item.id
  if (!item.is_read) emit('read', item)
}
</script>

<style scoped>
.notification-button {
  display: flex;
  align-items: center;
  justify-content: center;
  width: 38px;
  height: 38px;
  padding: 0;
  border: 0;
  border-radius: 10px;
  background: transparent;
  color: #33475e;
  cursor: pointer;
  transition: background-color .2s, color .2s;
}
.notification-button:hover { background: #eaf6fb; color: var(--ik-blue); }
.notification-button:focus-visible { outline: 2px solid var(--ik-blue); outline-offset: 2px; }
.notification-panel { max-height: min(620px, calc(100vh - 90px)); display: flex; flex-direction: column; }
.panel-header { display: flex; align-items: center; justify-content: space-between; gap: 12px; padding: 4px 4px 12px; border-bottom: 1px solid var(--ik-border); }
.panel-header div { display: flex; align-items: baseline; gap: 8px; }
.panel-header strong { font-size: 17px; color: #182b49; }
.panel-header span { color: #8492a6; font-size: 12px; }
.notification-list { overflow-y: auto; margin: 0 -6px; padding: 6px; }
.notification-item { border-bottom: 1px solid #edf1f5; }
.notification-item:last-child { border-bottom: 0; }
.notification-item.unread { background: #f2f9ff; border-radius: 8px; }
.notification-summary { width: 100%; display: flex; align-items: center; gap: 10px; padding: 13px 10px; border: 0; background: transparent; color: inherit; text-align: left; cursor: pointer; }
.notification-summary:hover { background: rgba(0, 96, 183, .05); border-radius: 8px; }
.unread-dot { width: 7px; height: 7px; flex: 0 0 7px; border-radius: 50%; background: transparent; }
.unread .unread-dot { background: #f56c6c; }
.summary-copy { flex: 1; min-width: 0; display: flex; flex-direction: column; gap: 5px; }
.summary-copy strong { overflow: hidden; text-overflow: ellipsis; white-space: nowrap; font-size: 14px; color: #253858; }
.unread .summary-copy strong { color: var(--ik-blue); }
.summary-copy time { color: #8a97a8; font-size: 12px; }
.expand-icon { color: #8a97a8; transition: transform .2s; }
.expanded .expand-icon { transform: rotate(180deg); }
.notification-content { margin: -2px 17px 14px 27px; padding: 12px 14px; border-radius: 8px; background: #fff; color: #455468; font-size: 13px; line-height: 1.7; overflow-wrap: anywhere; }
.notification-content :deep(p:first-child) { margin-top: 0; }
.notification-content :deep(p:last-child) { margin-bottom: 0; }
.notification-content :deep(img) { max-width: 100%; }
.panel-state { min-height: 150px; display: flex; align-items: center; justify-content: center; gap: 8px; color: #8a97a8; }
.stale-tip { display: flex; align-items: center; gap: 5px; margin: 8px 4px 2px; color: #b88230; font-size: 12px; }
</style>
