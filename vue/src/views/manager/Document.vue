<template>
  <div>

    <div class="card upload-card">
      <el-upload
          class="doc-upload"
          drag
          multiple
          :action="uploadUrl"
          accept=".pdf,.docx"
          :with-credentials="true"
          :show-file-list="false"
          :before-upload="beforeUpload"
          :on-success="onUploadSuccess"
          :on-error="() => ElMessage.error('上传失败，请重试')"
      >
        <el-icon class="upload-icon"><UploadFilled /></el-icon>
        <div class="upload-text">将文档拖到此处，或<em>点击上传</em></div>
        <div class="upload-hint">支持 PDF / DOCX 格式，单个文件不超过 50MB</div>
      </el-upload>
    </div>

    <div class="card" style="margin-bottom: 5px;">
      <el-input v-model="data.name" style="width: 300px; margin-right: 10px" placeholder="请输入文件名查询" :prefix-icon="Search" @keyup.enter="load"></el-input>
      <el-button type="primary" :icon="Search" @click="load">查询</el-button>
      <el-button type="info" :icon="Refresh" style="margin: 0 10px" @click="reset">重置</el-button>
    </div>

    <div class="card" style="margin-bottom: 5px">
      <el-table :data="data.tableData" stripe>
        <el-table-column label="文件名" prop="name" min-width="220" show-overflow-tooltip>
          <template #default="scope">
            <div class="doc-name">
              <el-icon class="doc-icon"><Document /></el-icon>
              <span>{{ scope.row.name }}</span>
            </div>
          </template>
        </el-table-column>
        <el-table-column label="格式" align="center" width="90">
          <template #default="scope">
            <el-tag :type="tagType(scope.row.ext)" effect="light">{{ (scope.row.ext || '').toUpperCase() }}</el-tag>
          </template>
        </el-table-column>
        <el-table-column label="大小" align="center" width="110">
          <template #default="scope">{{ formatSize(scope.row.size) }}</template>
        </el-table-column>
        <el-table-column label="上传时间" align="center" width="170">
          <template #default="scope">{{ formatTime(scope.row.created_at) }}</template>
        </el-table-column>
        <el-table-column label="文字识别" align="center" width="130">
          <template #default="scope">
            <el-tag v-if="scope.row.ext === 'pdf'" size="small" effect="plain" :type="ocrType(scope.row.ocr_status)">
              {{ displayOcrLabel(scope.row) }}
            </el-tag>
            <span v-else class="not-applicable">—</span>
          </template>
        </el-table-column>
        <el-table-column label="操作" align="center" width="330">
          <template #default="scope">
            <el-button type="primary" size="small" :icon="View" @click="handlePreview(scope.row)">预览</el-button>
            <el-button type="primary" size="small" :icon="Download" @click="handleDownload(scope.row)">下载</el-button>
            <el-button v-if="canRetryOcr(scope.row)" size="small" @click="retryOcr(scope.row)">重试识别</el-button>
            <el-button type="danger" size="small" :icon="Delete" @click="handleDelete(scope.row.id)">删除</el-button>
          </template>
        </el-table-column>
      </el-table>
    </div>

    <div class="card">
      <el-pagination @current-change="load" background layout="total, prev, pager, next" v-model:page-size="data.pageSize" v-model:current-page="data.pageNum" :total="data.total"/>
    </div>

    <el-dialog v-model="data.previewVisible" width="72%" top="4vh" destroy-on-close :title="data.previewModel?.title" class="preview-dialog">
      <DocumentReader v-if="data.previewModel" :model="data.previewModel" style="height: 72vh" />
    </el-dialog>

  </div>
</template>

<script setup>
import { onBeforeUnmount, reactive } from "vue";
import request from "@/utils/request";
import { ElMessage, ElMessageBox } from "element-plus";
import { Search, Refresh, Delete, Document, Download, UploadFilled, View } from "@element-plus/icons-vue";
import { buildPreviewModel } from "@/utils/preview";
import DocumentReader from "@/components/DocumentReader.vue";
import { formatSize, formatTime } from '@/utils/format'

const ALLOWED_EXTS = ['pdf', 'docx']
const MAX_SIZE = 50 * 1024 * 1024

// 文档上传的接口地址
const uploadUrl = import.meta.env.VITE_BASE_URL + '/document/upload'

const data = reactive({
  tableData: [],
  total: 0,
  pageNum: 1,
  pageSize: 10,
  name: null,
  previewVisible: false,
  previewModel: null,
})

let ocrRefreshTimer = null

const scheduleOcrRefresh = () => {
  clearTimeout(ocrRefreshTimer)
  if (data.tableData.some(row => ['pending', 'processing'].includes(row.ocr_status))) {
    ocrRefreshTimer = setTimeout(load, 3000)
  }
}

// 分页查询当前用户的文档列表
const load = async () => {
  const res = await request.get('/document/selectPage', {
    params: {
      pageNum: data.pageNum,
      pageSize: data.pageSize,
      name: data.name
    }
  })
  data.tableData = res.data?.list || []
  data.total = res.data?.total || 0
  scheduleOcrRefresh()
}

// 上传前校验格式与大小
const beforeUpload = (file) => {
  const ext = (file.name.split('.').pop() || '').toLowerCase()
  if (!ALLOWED_EXTS.includes(ext)) {
    ElMessage.error('不支持的文件格式，仅支持 PDF / DOCX')
    return false
  }
  if (file.size > MAX_SIZE) {
    ElMessage.error('文件大小不能超过 50MB')
    return false
  }
  return true
}

const onUploadSuccess = (res) => {
  if (res.code === '200') {
    ElMessage.success('上传成功')
    data.pageNum = 1  // 最新文件排在第一页
    load()
  } else {
    ElMessage.error(res.msg)
  }
}

const handlePreview = (row) => {
  const model = buildPreviewModel(row)
  if (!model) {
    ElMessage.error('暂不支持预览该格式')
    return
  }
  data.previewModel = model
  data.previewVisible = true
}

const handleDownload = (row) => {
  window.open(import.meta.env.VITE_BASE_URL + '/document/download/' + row.id)
}

const retryOcr = async (row) => {
  const res = await request.post(`/document/${row.id}/ocr`)
  Object.assign(row, res.data || {})
  ElMessage.success('已重新加入文字识别队列')
  scheduleOcrRefresh()
}

const handleDelete = (id) => {
  ElMessageBox.confirm('删除后文件无法恢复，您确定删除吗?', '删除确认', { type: 'warning' }).then(() => {
    request.delete('/document/delete/' + id).then(res => {
      if (res.code === '200') {
        load()
        ElMessage.success('操作成功')
      } else {
        ElMessage.error(res.msg)
      }
    })
  }).catch(() => {})
}

const reset = () => {
  data.name = null
  data.pageNum = 1
  load()
}

const tagType = (ext) => ({ pdf: 'danger', docx: '' }[ext] ?? 'info')
const ocrLabel = (status) => ({
  pending: '等待识别',
  processing: '识别中',
  ready: '可选择文字',
  failed: '识别失败',
}[status] || '未处理')
const displayOcrLabel = (row) => row.ocr_error === 'OCR 服务未启用' ? '未启用' : ocrLabel(row.ocr_status)
const canRetryOcr = (row) => row.ext === 'pdf' && row.ocr_status === 'failed' && row.ocr_error !== 'OCR 服务未启用'
const ocrType = (status) => ({ ready: 'success', failed: 'danger', processing: 'primary' }[status] || 'info')

load()
onBeforeUnmount(() => clearTimeout(ocrRefreshTimer))
</script>

<style scoped>
.upload-card {
  margin-bottom: 5px;
}
.doc-upload :deep(.el-upload-dragger) {
  border: 1px dashed #b9dcec;
  border-radius: 12px;
  padding: 28px 0;
  transition: border-color .25s;
}
.doc-upload :deep(.el-upload-dragger:hover) {
  border-color: var(--ik-cyan-deep);
}
.upload-icon {
  font-size: 44px;
  color: var(--ik-blue);
}
.upload-text {
  color: #33475e;
  font-size: 15px;
  margin-top: 8px;
}
.upload-text em {
  color: var(--ik-blue);
  font-style: normal;
  font-weight: 600;
}
.upload-hint {
  color: #7b93a8;
  font-size: 13px;
  margin-top: 6px;
}
.doc-name {
  display: flex;
  align-items: center;
}
.doc-icon {
  color: var(--ik-cyan-deep);
  margin-right: 6px;
  flex-shrink: 0;
}
.not-applicable { color: var(--ik-text-sub); }
</style>
