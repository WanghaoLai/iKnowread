<template>
  <div>

    <div class="card upload-card">
      <el-upload
          class="doc-upload"
          drag
          multiple
          accept=".pdf,.docx"
          :show-file-list="false"
          :http-request="uploadTask"
          :before-upload="beforeUpload"
          :on-success="onUploadSuccess"
          :on-error="onUploadError"
      >
        <el-icon class="upload-icon"><UploadFilled /></el-icon>
        <div class="upload-text">将文档拖到此处，或<em>点击上传</em></div>
        <div class="upload-hint">支持 PDF / DOCX 格式，单个文件不超过 50MB</div>
      </el-upload>
    </div>

    <div class="card" style="margin-bottom: 5px;">
      <el-input v-model="data.name" style="width: 300px; margin-right: 10px" placeholder="请输入文件名查询" :prefix-icon="Search" @keyup.enter="load"></el-input>
      <el-button type="primary" :icon="Search" :loading="loading" @click="load">查询</el-button>
      <el-button type="info" :icon="Refresh" style="margin: 0 10px" @click="reset">重置</el-button>
    </div>

    <div class="card" style="margin-bottom: 5px">
      <el-table v-loading="loading" :data="data.tableData" stripe>
        <el-table-column label="文件名" prop="name" min-width="340" show-overflow-tooltip>
          <template #default="scope">
            <div class="doc-name">
              <el-icon class="doc-icon"><Document /></el-icon>
              <span>{{ scope.row.name }}</span>
            </div>
          </template>
        </el-table-column>
        <el-table-column label="格式" align="center" min-width="90">
          <template #default="scope">
            <el-tag :type="tagType(scope.row.ext)" effect="light">{{ (scope.row.ext || '').toUpperCase() }}</el-tag>
          </template>
        </el-table-column>
        <el-table-column label="大小" align="center" min-width="100">
          <template #default="scope">{{ formatSize(scope.row.size) }}</template>
        </el-table-column>
        <el-table-column label="上传时间" align="center" min-width="160">
          <template #default="scope">{{ formatTime(scope.row.created_at) }}</template>
        </el-table-column>
        <el-table-column label="处理状态" min-width="180">
          <template #default="scope">
            <div class="processing-stages">
              <el-tag
                  v-for="stage in scope.row.processing_stages"
                  :key="stage.type"
                  size="small"
                  effect="plain"
                  :type="processingType(stage.status)"
                  :title="stage.error || `${stage.label}：${processingLabel(stage.status)}`"
              >{{ stage.label }}：{{ processingLabel(stage.status, stage) }}</el-tag>
            </div>
          </template>
        </el-table-column>
        <el-table-column label="操作" align="center" width="230">
          <template #default="scope">
            <el-button type="primary" size="small" :icon="View" @click="handlePreview(scope.row)">预览</el-button>
            <el-button
                v-if="canRetryOcr(scope.row)"
                size="small"
                :loading="retryingOcrIds.has(scope.row.id)"
                @click="retryOcr(scope.row)"
            >重试识别</el-button>
            <el-button
                type="danger"
                size="small"
                :icon="Delete"
                :loading="deletingDocumentIds.has(scope.row.id)"
                @click="handleDelete(scope.row.id)"
            >删除</el-button>
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
import { ElMessage, ElMessageBox } from "element-plus";
import { Search, Refresh, Delete, Document, UploadFilled, View } from "@element-plus/icons-vue";
import { buildPreviewModel } from "@/utils/preview";
import { listDocuments, recycleDocument, retryDocumentOcr, uploadDocument } from '@/api/documents'
import DocumentReader from "@/components/DocumentReader.vue";
import { formatSize, formatTime, documentTagType as tagType } from '@/utils/format'
import { notifyRequestError } from '@/utils/request'
import { useListLoader } from '@/composables/useListLoader'
import { useBusyRefresh } from '@/composables/useBusyRefresh'

const ALLOWED_EXTS = ['pdf', 'docx']
const MAX_SIZE = 50 * 1024 * 1024

const data = reactive({
  tableData: [],
  total: 0,
  pageNum: 1,
  pageSize: 10,
  name: null,
  previewVisible: false,
  previewModel: null,
})

const retryingOcrIds = reactive(new Set())
const deletingDocumentIds = reactive(new Set())

const { loading, load: loadList, invalidate } = useListLoader(
  signal => listDocuments({
    pageNum: data.pageNum,
    pageSize: data.pageSize,
    name: data.name,
  }, { signal }),
  {
    cancellable: true,
    onError: error => notifyRequestError(error, '文档列表加载失败，请重试'),
  },
)

const { schedule: scheduleOcrRefresh, stop: stopOcrRefresh } = useBusyRefresh(load, () =>
  data.tableData.some(row => (row.processing_stages || []).some(
      stage => ['pending', 'processing'].includes(stage.status)
  )))

// 分页查询当前用户的文档列表
async function load() {
  const res = await loadList()
  if (!res) return
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

// 多文件拖入时串行上传：避免并发触发服务端上传并发限制（429），
// 也让每个失败的文件只弹一条具体错误提示。
let uploadChain = Promise.resolve()
const uploadTask = (option) => {
  const run = async () => {
    try {
      option.onSuccess(await uploadDocument(option.file, {
        skipErrorToast: true,
        timeout: 300000,
      }))
    } catch (error) {
      option.onError(error)
    }
  }
  uploadChain = uploadChain.then(run, run)
  return uploadChain
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

const onUploadError = (error) => {
  ElMessage.error(error?.response?.data?.msg || '上传失败，请重试')
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

const retryOcr = async (row) => {
  if (retryingOcrIds.has(row.id)) return
  retryingOcrIds.add(row.id)
  try {
    const res = await retryDocumentOcr(row.id)
    Object.assign(row, res.data || {})
    ElMessage.success('已重新加入文字识别队列')
    scheduleOcrRefresh()
  } catch (error) {
    notifyRequestError(error, '重新提交文字识别失败，请重试')
  } finally {
    retryingOcrIds.delete(row.id)
  }
}

const handleDelete = async (id) => {
  if (deletingDocumentIds.has(id)) return
  deletingDocumentIds.add(id)
  try {
    await ElMessageBox.confirm('删除后文档将移入回收站，可随时恢复或彻底删除，确定删除吗?', '删除确认', { type: 'warning' })
    const res = await recycleDocument(id)
    if (res.code === '200') {
      ElMessage.success('操作成功')
      await load()
    } else {
      ElMessage.error(res.msg || '文档删除失败')
    }
  } catch (error) {
    if (error !== 'cancel' && error !== 'close') {
      await notifyRequestError(error, '文档删除失败，请重试')
    }
  } finally {
    deletingDocumentIds.delete(id)
  }
}

const reset = () => {
  data.name = null
  data.pageNum = 1
  load()
}

const canRetryOcr = (row) => row.ext === 'pdf' && row.ocr_status === 'failed' && row.ocr_error !== 'OCR 服务未启用'
const processingLabel = (status, stage = {}) => {
  if (stage.error === 'OCR 服务未启用') return '未启用'
  return ({
    not_applicable: '不适用',
    not_started: '未开始',
    pending: '等待中',
    processing: '处理中',
    ready: '已完成',
    failed: '失败',
  })[status] || '未知'
}
const processingType = status => ({
  ready: 'success', failed: 'danger', processing: 'primary', pending: 'warning',
})[status] || 'info'

load()
onBeforeUnmount(() => {
  stopOcrRefresh()
  invalidate()
})
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
.processing-stages {
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
}
</style>
