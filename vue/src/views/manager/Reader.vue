<template>
  <div class="reader-page">

    <div class="card doc-panel">
      <div class="panel-title">
        <el-icon><Collection /></el-icon>
        <span>我的文档</span>
      </div>
      <el-input v-model="data.name" style="margin-bottom: 10px" placeholder="搜索文件名" :prefix-icon="Search" clearable @input="scheduleLoad"></el-input>
      <div class="doc-list" v-loading="loading">
        <div
            v-for="row in data.tableData"
            :key="row.id"
            class="doc-item"
            :class="{ active: data.selectedId === row.id }"
            @click="selectManual(row)"
        >
          <el-icon class="doc-item-icon"><Document /></el-icon>
          <div class="doc-item-info">
            <div class="doc-item-name" :title="row.name">{{ row.name }}</div>
            <div class="doc-item-meta">
              {{ (row.ext || '').toUpperCase() }} · {{ formatSize(row.size) }}
              <span v-if="row.ext === 'pdf'"> · {{ ocrLabel(row.ocr_status) }}</span>
            </div>
          </div>
        </div>
        <div v-if="!loading && !data.tableData.length" class="doc-empty">
          暂无文档，请先到「我的文档」上传
        </div>
      </div>
      <el-pagination
          class="doc-pagination"
          small
          background
          layout="prev, pager, next"
          v-model:current-page="data.pageNum"
          :page-size="data.pageSize"
          :total="data.total"
          @current-change="load"
      />
    </div>

    <div class="reader-panel">
      <DocumentReader v-if="data.model" :model="data.model" :initial-anchor="data.initialAnchor" />
      <div v-else v-loading="loading" class="card reader-placeholder" aria-live="polite">
        <template v-if="data.openError">
          <div class="placeholder-icon"><el-icon><WarningFilled /></el-icon></div>
          <h2>无法打开文档</h2>
          <p>{{ data.openError }}</p>
        </template>
        <template v-else-if="data.selectedId">
          <div class="placeholder-icon"><el-icon><Reading /></el-icon></div>
          <h2>暂不支持在线预览</h2>
          <p>{{ data.selectedName }}（{{ data.selectedExt }}）请下载后查看，或从左侧选择其他文档。</p>
        </template>
        <template v-else>
          <div class="placeholder-icon"><el-icon><Reading /></el-icon></div>
          <h2>{{ !loading && !data.total ? '还没有可阅读的文档' : '选择一份文档开始阅读' }}</h2>
          <p>{{ !loading && !data.total ? '请先上传文档，上传完成后即可在这里开始阅读。' : '从左侧“我的文档”列表中选择文件，文档内容将在此处打开。' }}</p>
          <div v-if="data.total" class="reader-guide" aria-label="阅读操作提示">
            <div><span>1</span><p><strong>选择阅读方式</strong>PDF 支持分页或连续阅读，DOCX 与 Markdown 以长文方式展示。</p></div>
            <div><span>2</span><p><strong>搜索与定位</strong>搜索文档内容，阅读进度会自动保存，再次打开可继续阅读。</p></div>
            <div><span>3</span><p><strong>划词辅助阅读</strong>选择字、词、句或段落，可获取 AI 解释并保存为笔记或高亮备注。</p></div>
          </div>
          <el-button v-if="!loading && !data.total" type="primary" @click="goToDocuments">前往上传文档</el-button>
        </template>
      </div>
    </div>

  </div>
</template>

<script setup>
import { onBeforeUnmount, onMounted, reactive } from "vue";
import { useRoute, useRouter } from 'vue-router'
import { Collection, Document, Reading, Search, WarningFilled } from "@element-plus/icons-vue";
import { buildPreviewModel } from "@/utils/preview";
import DocumentReader from "@/components/DocumentReader.vue";
import { formatSize } from '@/utils/format'
import { consumeSourceNavigation } from '@/utils/sourceAnchor'
import { getDocumentOcrStatus, listDocuments } from '@/api/documents'
import { useListLoader } from '@/composables/useListLoader'
import { useBusyRefresh } from '@/composables/useBusyRefresh'
import { notifyRequestError } from '@/utils/request'

const route = useRoute()
const router = useRouter()
const queuedAnchor = consumeSourceNavigation()

const data = reactive({
  tableData: [],
  total: 0,
  pageNum: 1,
  pageSize: 20,
  name: null,
  selectedId: null,
  selectedName: '',
  selectedExt: '',
  model: null,
  initialAnchor: queuedAnchor,
  openError: '',
})

let searchTimer = null
const PAGE_SCROLL_LOCK_CLASS = 'iknowread-reader-open'

const { loading, load: loadList, invalidate } = useListLoader(
  requestOptions => listDocuments({
    pageNum: data.pageNum,
    pageSize: data.pageSize,
    name: data.name,
  }, requestOptions),
  {
    cancellable: true,
    onError: error => notifyRequestError(error, '文档列表加载失败，请重试'),
  },
)

const { schedule: scheduleOcrRefresh, stop: stopOcrRefresh } = useBusyRefresh(load, () =>
  data.tableData.some(row => ['pending', 'processing'].includes(row.ocr_status)))

async function load() {
  const res = await loadList()
  if (!res) return
  data.tableData = res.data?.list || []
  data.total = res.data?.total || 0
  const requestedId = Number(route.query.documentId)
  if (Number.isInteger(requestedId) && requestedId > 0) {
    if (data.selectedId !== requestedId) {
      let target = data.tableData.find(doc => doc.id === requestedId)
      if (!target) {
        try {
          const targetResponse = await getDocumentOcrStatus(requestedId)
          target = targetResponse.data
        } catch (_) {
          // 请求层已提示具体原因；这里给出页面级说明并清掉失效的定位参数，
          // 避免落到“选择一份文档”的通用占位符里语义混淆。
          data.openError = '该文档可能已被删除、移入回收站或无访问权限'
          router.replace({ path: route.path, query: {} })
          return
        }
      }
      select(target, queuedAnchor)
    }
  }
  scheduleOcrRefresh()
}

const scheduleLoad = () => {
  clearTimeout(searchTimer)
  data.pageNum = 1
  searchTimer = setTimeout(load, 300)
}

const select = (row, anchor = null) => {
  data.openError = ''
  data.selectedId = row?.id ?? null
  data.selectedName = row?.name || ''
  data.selectedExt = (row?.ext || '').toUpperCase()
  data.model = row ? buildPreviewModel(row) : null
  data.initialAnchor = anchor
}

const selectManual = row => {
  if (route.query.documentId) router.replace({ path: route.path, query: {} })
  select(row)
}

const goToDocuments = () => router.push('/manager/document')

const ocrLabel = (status) => ({
  pending: '等待识别',
  processing: '识别中',
  ready: '文字可选',
  failed: '识别失败',
}[status] || '未处理')

load()
onMounted(() => {
  document.documentElement.classList.add(PAGE_SCROLL_LOCK_CLASS)
  document.body.classList.add(PAGE_SCROLL_LOCK_CLASS)
})
onBeforeUnmount(() => {
  document.documentElement.classList.remove(PAGE_SCROLL_LOCK_CLASS)
  document.body.classList.remove(PAGE_SCROLL_LOCK_CLASS)
  clearTimeout(searchTimer)
  stopOcrRefresh()
  invalidate()
})
</script>

<style scoped>
.reader-page {
  display: flex;
  gap: 10px;
  width: 100%;
  height: 100%;
  min-height: 0;
  padding: 0;
  overflow: hidden;
}
.doc-panel {
  width: 260px;
  min-height: 0;
  flex-shrink: 0;
  display: flex;
  flex-direction: column;
  overflow: hidden;
}
.panel-title {
  display: flex;
  align-items: center;
  gap: 6px;
  font-weight: 600;
  color: #24384c;
  margin-bottom: 10px;
}
.panel-title .el-icon { color: var(--ik-blue); }
.doc-list {
  flex: 1;
  min-height: 0;
  overflow-y: auto;
  overscroll-behavior: contain;
}
.doc-pagination {
  justify-content: center;
  padding-top: 8px;
}
.doc-item {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 9px 10px;
  border-radius: 10px;
  cursor: pointer;
  transition: background-color .2s;
}
.doc-item:hover { background: #eaf6fb; }
.doc-item.active {
  background: var(--ik-gradient);
}
.doc-item.active .doc-item-name,
.doc-item.active .doc-item-meta,
.doc-item.active .doc-item-icon { color: #fff; }
.doc-item-icon {
  color: var(--ik-cyan-deep);
  font-size: 18px;
  flex-shrink: 0;
}
.doc-item-info { min-width: 0; }
.doc-item-name {
  font-size: 13px;
  color: #2a3b4d;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.doc-item-meta {
  font-size: 12px;
  color: var(--ik-text-sub);
  margin-top: 2px;
}
.doc-empty {
  text-align: center;
  color: var(--ik-text-sub);
  font-size: 13px;
  padding: 30px 0;
}
.reader-panel {
  flex: 1;
  min-width: 0;
  min-height: 0;
  height: 100%;
  overflow: hidden;
}
.reader-placeholder {
  height: 100%;
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  gap: 10px;
  padding: clamp(24px, 5vw, 56px);
  overflow-y: auto;
  color: var(--ik-text-sub);
  text-align: center;
}
.placeholder-icon {
  display: grid;
  width: 68px;
  height: 68px;
  place-items: center;
  margin-bottom: 4px;
  color: #fff;
  font-size: 34px;
  background: var(--ik-gradient);
  border-radius: 22px;
  box-shadow: 0 12px 28px rgba(0, 105, 185, .16);
}
.reader-placeholder h2 { margin: 0; color: #24384c; font-size: 22px; }
.reader-placeholder > p { max-width: 620px; margin: 0; font-size: 14px; line-height: 1.7; }
.reader-guide {
  display: grid;
  width: min(720px, 100%);
  grid-template-columns: repeat(3, minmax(0, 1fr));
  gap: 10px;
  margin-top: 12px;
  text-align: left;
}
.reader-guide > div { display: flex; align-items: flex-start; gap: 9px; padding: 13px; background: #f6fafc; border: 1px solid #e5eef3; border-radius: 11px; }
.reader-guide > div > span { display: grid; width: 22px; height: 22px; flex: none; place-items: center; color: #fff; font-size: 11px; font-weight: 700; background: var(--ik-cyan-deep); border-radius: 50%; }
.reader-guide p { margin: 0; font-size: 12px; line-height: 1.55; }
.reader-guide strong { display: block; margin-bottom: 3px; color: #33475e; font-size: 13px; }
@media (max-width: 900px) {
  .reader-guide { grid-template-columns: 1fr; }
}
</style>
