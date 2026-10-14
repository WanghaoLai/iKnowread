<template>
  <div class="reader-page">

    <div class="card doc-panel">
      <div class="panel-title">
        <el-icon><Collection /></el-icon>
        <span>我的文档</span>
      </div>
      <el-input v-model="data.name" style="margin-bottom: 10px" placeholder="搜索文件名" :prefix-icon="Search" clearable @input="scheduleLoad"></el-input>
      <div class="doc-list" v-loading="data.loading">
        <div
            v-for="row in data.tableData"
            :key="row.id"
            class="doc-item"
            :class="{ active: data.selectedId === row.id }"
            @click="select(row)"
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
        <div v-if="!data.loading && !data.tableData.length" class="doc-empty">
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
      <DocumentReader v-if="data.model" :model="data.model" />
      <div v-else class="card reader-placeholder">
        <el-icon :size="44"><Reading /></el-icon>
        <div v-if="data.selectedId">{{ data.selectedName }}（{{ data.selectedExt }}）暂不支持在线预览，请下载后查看</div>
        <div v-else>从左侧选择要阅读的文档</div>
      </div>
    </div>

  </div>
</template>

<script setup>
import { onBeforeUnmount, reactive } from "vue";
import request from "@/utils/request";
import { Collection, Document, Reading, Search } from "@element-plus/icons-vue";
import { buildPreviewModel } from "@/utils/preview";
import DocumentReader from "@/components/DocumentReader.vue";
import { formatSize } from '@/utils/format'

const data = reactive({
  tableData: [],
  total: 0,
  pageNum: 1,
  pageSize: 20,
  loading: false,
  name: null,
  selectedId: null,
  selectedName: '',
  selectedExt: '',
  model: null,
})

let searchTimer = null
let controller = null
let requestSequence = 0
let ocrRefreshTimer = null

const scheduleOcrRefresh = () => {
  clearTimeout(ocrRefreshTimer)
  if (data.tableData.some(row => ['pending', 'processing'].includes(row.ocr_status))) {
    ocrRefreshTimer = setTimeout(load, 3000)
  }
}

const load = async () => {
  controller?.abort()
  const activeController = new AbortController()
  controller = activeController
  const sequence = ++requestSequence
  data.loading = true
  try {
    const res = await request.get('/document/selectPage', {
      signal: activeController.signal,
      params: {
        pageNum: data.pageNum,
        pageSize: data.pageSize,
        name: data.name
      }
    })
    if (sequence !== requestSequence) return
    data.tableData = res.data?.list || []
    data.total = res.data?.total || 0
    if (!data.tableData.some(doc => doc.id === data.selectedId)) {
      select(data.tableData[0] || null)
    }
    scheduleOcrRefresh()
  } catch (_) {
    // request interceptor reports real failures; cancellation is expected.
  } finally {
    if (sequence === requestSequence) data.loading = false
  }
}

const scheduleLoad = () => {
  clearTimeout(searchTimer)
  data.pageNum = 1
  searchTimer = setTimeout(load, 300)
}

const select = (row) => {
  data.selectedId = row?.id ?? null
  data.selectedName = row?.name || ''
  data.selectedExt = (row?.ext || '').toUpperCase()
  data.model = row ? buildPreviewModel(row) : null
}

const ocrLabel = (status) => ({
  pending: '等待识别',
  processing: '识别中',
  ready: '文字可选',
  failed: '识别失败',
}[status] || '未处理')

load()
onBeforeUnmount(() => {
  clearTimeout(searchTimer)
  clearTimeout(ocrRefreshTimer)
  controller?.abort()
})
</script>

<style scoped>
.reader-page {
  display: flex;
  gap: 10px;
  height: calc(100vh - 60px - 28px);
  padding: 0;
}
.doc-panel {
  width: 260px;
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
  overflow-y: auto;
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
}
.reader-placeholder {
  height: 100%;
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  gap: 12px;
  color: var(--ik-text-sub);
}
.reader-placeholder .el-icon { color: var(--ik-blue); }
</style>
