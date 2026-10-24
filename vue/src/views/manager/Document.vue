<template>
  <div>

    <div id="web-import-section" class="card web-import-card">
      <div class="web-import-title">收藏网页</div>
      <div class="web-import-form">
        <el-input
            v-model.trim="data.webUrl"
            clearable
            maxlength="2048"
            :disabled="!webImportEnabled"
            placeholder="输入公开网页 URL，例如 https://example.com/article"
            @keyup.enter="submitWebImport"
        />
        <el-button
            type="primary"
            :disabled="!webImportEnabled"
            :loading="webImportSubmitting"
            @click="submitWebImport"
        >导入网页</el-button>
      </div>
      <div class="upload-hint" :class="{ 'web-import-unavailable': !webImportEnabled }">
        {{ webImportEnabled
          ? '网页将在后台提取为 Markdown；完成后可直接阅读、搜索、高亮、记笔记和划词解释。'
          : webImportError }}
      </div>
      <div v-if="data.webJobs.length" class="web-job-list">
        <div v-for="job in data.webJobs.slice(0, 5)" :key="job.id" class="web-job-row">
          <el-tag size="small" :type="webJobType(job.status)">{{ webJobLabel(job.status) }}</el-tag>
          <span class="web-job-url" :title="job.source_url">{{ job.source_url }}</span>
          <span v-if="job.error" class="web-job-error" :title="job.error">{{ job.error }}</span>
          <el-button
              v-if="job.status === 'failed'"
              link type="primary"
              :loading="busyWebJobIds.has(job.id)"
              :disabled="busyWebJobIds.has(job.id)"
              @click="retryWebJob(job)"
          >重试</el-button>
          <el-button
              v-if="['pending', 'processing'].includes(job.status)"
              link type="warning"
              :loading="busyWebJobIds.has(job.id)"
              :disabled="busyWebJobIds.has(job.id)"
              @click="cancelWebJob(job)"
          >取消</el-button>
          <el-button
              v-if="['success', 'failed', 'canceled'].includes(job.status)"
              link type="danger"
              :loading="busyWebJobIds.has(job.id)"
              :disabled="busyWebJobIds.has(job.id)"
              @click="removeWebJob(job)"
          >删除记录</el-button>
        </div>
      </div>
      <div v-else-if="webJobsLoading" class="upload-hint">正在读取网页收藏任务…</div>
      <div v-if="webJobsError" class="web-job-error web-job-list-error">{{ webJobsError }}</div>
    </div>

    <div id="upload-section" class="card upload-card">
      <el-upload
          class="doc-upload"
          drag
          multiple
          accept=".pdf,.docx,.md"
          :show-file-list="false"
          :http-request="uploadTask"
          :before-upload="beforeUpload"
          :on-success="onUploadSuccess"
          :on-error="onUploadError"
      >
        <el-icon class="upload-icon"><UploadFilled /></el-icon>
        <div class="upload-text">将文档拖到此处，或<em>点击上传</em></div>
        <div class="upload-hint">支持 PDF / DOCX（不超过 50MB）和 Markdown（不超过 5MB）</div>
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
        <el-table-column label="来源" align="center" min-width="110">
          <template #default="scope">
            <el-tag :type="scope.row.source_type === 'url' ? 'success' : 'info'" effect="plain">
              {{ scope.row.source_type === 'url' ? '网页收藏' : '本地上传' }}
            </el-tag>
          </template>
        </el-table-column>
        <el-table-column label="大小" align="center" min-width="100">
          <template #default="scope">{{ formatSize(scope.row.size) }}</template>
        </el-table-column>
        <el-table-column label="创建时间" align="center" min-width="160">
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
import { nextTick, onBeforeUnmount, onMounted, reactive, ref } from "vue";
import { useRoute } from 'vue-router'
import { ElMessage, ElMessageBox } from "element-plus";
import { Search, Refresh, Delete, Document, UploadFilled, View } from "@element-plus/icons-vue";
import { buildPreviewModel } from "@/utils/preview";
import { listDocuments, recycleDocument, retryDocumentOcr, uploadDocument } from '@/api/documents'
import DocumentReader from "@/components/DocumentReader.vue";
import { formatSize, formatTime, documentTagType as tagType } from '@/utils/format'
import { notifyRequestError } from '@/utils/request'
import { useListLoader } from '@/composables/useListLoader'
import { useBusyRefresh } from '@/composables/useBusyRefresh'
import {
  cancelWebImport,
  createWebImport,
  deleteWebImport,
  listWebImports,
  retryWebImport,
} from '@/api/webImports'
import { getCapabilities } from '@/api/auth'

const ALLOWED_EXTS = ['pdf', 'docx', 'md']
const MAX_SIZE = 50 * 1024 * 1024
const MARKDOWN_MAX_SIZE = 5 * 1024 * 1024
const route = useRoute()
const initialName = typeof route.query.name === 'string' ? route.query.name.slice(0, 255) : null

const data = reactive({
  tableData: [],
  total: 0,
  pageNum: 1,
  pageSize: 10,
  name: initialName,
  previewVisible: false,
  previewModel: null,
  webUrl: '',
  webJobs: [],
})

const retryingOcrIds = reactive(new Set())
const deletingDocumentIds = reactive(new Set())
const webImportSubmitting = ref(false)
const webImportEnabled = ref(false)
const webImportError = ref('正在检查网页收藏服务…')
const webJobsLoading = ref(false)
const webJobsError = ref('')
const busyWebJobIds = reactive(new Set())
let webImportTimer = null
let webImportStopped = false
let webImportLoadVersion = 0
let webImportController = null
const completedWebJobs = new Set()

const webJobLabel = status => ({
  pending: '排队中', processing: '抓取中', success: '成功', failed: '失败', canceled: '已取消',
})[status] || '未知'
const webJobType = status => ({
  pending: 'warning', processing: 'primary', success: 'success', failed: 'danger', canceled: 'info',
})[status] || 'info'

const scheduleWebImportRefresh = () => {
  clearTimeout(webImportTimer)
  if (!webImportStopped && data.webJobs.some(job => ['pending', 'processing'].includes(job.status))) {
    webImportTimer = setTimeout(loadWebImports, 2000)
  }
}

const loadWebImportCapability = async () => {
  try {
    const res = await getCapabilities({ skipErrorToast: true })
    webImportEnabled.value = Boolean(res.data?.web_import_enabled)
    webImportError.value = res.data?.web_import_error || '网页收藏服务暂不可用'
  } catch {
    webImportEnabled.value = false
    webImportError.value = '无法读取网页收藏服务状态'
  }
}

const loadWebImports = async ({ notify = false } = {}) => {
  const version = ++webImportLoadVersion
  webImportController?.abort()
  const controller = new AbortController()
  webImportController = controller
  webJobsLoading.value = true
  try {
    const res = await listWebImports({ skipErrorToast: true, signal: controller.signal })
    if (version !== webImportLoadVersion || webImportStopped) return
    data.webJobs = res.data || []
    webJobsError.value = ''
    let hasNewSuccess = false
    for (const job of data.webJobs) {
      if (job.status === 'success' && !completedWebJobs.has(job.id)) {
        completedWebJobs.add(job.id)
        hasNewSuccess = true
      }
    }
    if (hasNewSuccess) {
      data.pageNum = 1
      await load()
    }
    scheduleWebImportRefresh()
  } catch {
    if (version !== webImportLoadVersion || controller.signal.aborted || webImportStopped) return
    webJobsError.value = '网页收藏任务加载失败，系统将自动重试'
    if (notify) ElMessage.error(webJobsError.value)
    if (!webImportStopped) {
      webImportTimer = setTimeout(loadWebImports, 5000)
    }
  } finally {
    if (version === webImportLoadVersion) {
      webJobsLoading.value = false
      if (webImportController === controller) webImportController = null
    }
  }
}

const initializeWebImports = async () => {
  await loadWebImportCapability()
  await loadWebImports()
}

const submitWebImport = async () => {
  if (!webImportEnabled.value || !data.webUrl || webImportSubmitting.value) return
  webImportSubmitting.value = true
  try {
    await createWebImport(data.webUrl, { skipErrorToast: true })
    data.webUrl = ''
    ElMessage.success('已加入网页抓取队列')
    await loadWebImports()
  } catch (error) {
    notifyRequestError(error, '网页导入失败，请检查 URL 后重试')
  } finally {
    webImportSubmitting.value = false
  }
}

const retryWebJob = async job => {
  if (busyWebJobIds.has(job.id)) return
  busyWebJobIds.add(job.id)
  try {
    await retryWebImport(job.id, { skipErrorToast: true })
    ElMessage.success('已重新加入抓取队列')
    await loadWebImports()
  } catch (error) {
    notifyRequestError(error, '重新提交抓取任务失败')
  } finally {
    busyWebJobIds.delete(job.id)
  }
}

const cancelWebJob = async job => {
  if (busyWebJobIds.has(job.id)) return
  busyWebJobIds.add(job.id)
  try {
    await cancelWebImport(job.id, { skipErrorToast: true })
    ElMessage.success('抓取任务已取消')
    await loadWebImports()
  } catch (error) {
    notifyRequestError(error, '取消抓取任务失败')
  } finally {
    busyWebJobIds.delete(job.id)
  }
}

const removeWebJob = async job => {
  if (busyWebJobIds.has(job.id)) return
  try {
    await ElMessageBox.confirm('仅删除该抓取记录，已生成的文档会保留。', '删除抓取记录', {
      type: 'warning',
      confirmButtonText: '删除',
      cancelButtonText: '取消',
    })
  } catch {
    return
  }
  busyWebJobIds.add(job.id)
  try {
    await deleteWebImport(job.id, { skipErrorToast: true })
    completedWebJobs.delete(job.id)
    ElMessage.success('抓取记录已删除')
    await loadWebImports()
  } catch (error) {
    notifyRequestError(error, '删除抓取记录失败')
  } finally {
    busyWebJobIds.delete(job.id)
  }
}

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
    ElMessage.error('不支持的文件格式，仅支持 PDF / DOCX / Markdown')
    return false
  }
  if (ext === 'md' && file.size > MARKDOWN_MAX_SIZE) {
    ElMessage.error('Markdown 文件大小不能超过 5MB')
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
initializeWebImports()
onMounted(async () => {
  const target = ({ upload: 'upload-section', 'web-import': 'web-import-section' })[route.query.focus]
  if (!target) return
  await nextTick()
  document.getElementById(target)?.scrollIntoView({ behavior: 'smooth', block: 'start' })
})
onBeforeUnmount(() => {
  webImportStopped = true
  webImportLoadVersion += 1
  webImportController?.abort()
  clearTimeout(webImportTimer)
  stopOcrRefresh()
  invalidate()
})
</script>

<style scoped>
.upload-card {
  margin-bottom: 5px;
}
.web-import-card {
  margin-bottom: 5px;
}
.web-import-title {
  color: #33475e;
  font-size: 16px;
  font-weight: 600;
  margin-bottom: 12px;
}
.web-import-form {
  display: flex;
  gap: 10px;
  max-width: 860px;
}
.web-job-list {
  border-top: 1px solid #edf2f7;
  margin-top: 14px;
  padding-top: 8px;
}
.web-job-row {
  align-items: center;
  display: flex;
  gap: 8px;
  min-height: 30px;
}
.web-job-url {
  color: #50677c;
  max-width: 440px;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.web-job-error {
  color: #d45b5b;
  flex: 1;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.web-import-unavailable {
  color: #c45656;
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
