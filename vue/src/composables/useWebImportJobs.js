import { reactive, ref } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { getCapabilities } from '@/api/auth'
import {
  cancelWebImport,
  createWebImport,
  deleteWebImport,
  listWebImports,
  retryWebImport,
} from '@/api/webImports'
import { notifyRequestError } from '@/utils/request'

const RUNNING_STATUSES = new Set(['pending', 'processing'])

export const webJobLabel = status => ({
  pending: '排队中', processing: '抓取中', success: '成功', failed: '失败', canceled: '已取消',
})[status] || '未知'

export const webJobType = status => ({
  pending: 'warning', processing: 'primary', success: 'success', failed: 'danger', canceled: 'info',
})[status] || 'info'

export function useWebImportJobs({ data, onDocumentCreated }) {
  const webImportSubmitting = ref(false)
  const webImportEnabled = ref(false)
  const webImportError = ref('正在检查网页收藏服务…')
  const webJobsLoading = ref(false)
  const webJobsError = ref('')
  const busyWebJobIds = reactive(new Set())
  const completedWebJobs = new Set()
  let refreshTimer = null
  let stopped = false
  let loadVersion = 0
  let controller = null

  const scheduleRefresh = load => {
    clearTimeout(refreshTimer)
    if (!stopped && data.webJobs.some(job => RUNNING_STATUSES.has(job.status))) {
      refreshTimer = setTimeout(load, 2000)
    }
  }

  const loadCapability = async () => {
    try {
      const response = await getCapabilities({ skipErrorToast: true })
      webImportEnabled.value = Boolean(response.data?.web_import_enabled)
      webImportError.value = response.data?.web_import_error || '网页收藏服务暂不可用'
    } catch {
      webImportEnabled.value = false
      webImportError.value = '无法读取网页收藏服务状态'
    }
  }

  const loadWebImports = async ({ notify = false } = {}) => {
    const version = ++loadVersion
    controller?.abort()
    const currentController = new AbortController()
    controller = currentController
    webJobsLoading.value = true
    try {
      const response = await listWebImports({
        skipErrorToast: true,
        signal: currentController.signal,
      })
      if (version !== loadVersion || stopped) return
      data.webJobs = response.data || []
      webJobsError.value = ''
      let hasNewSuccess = false
      for (const job of data.webJobs) {
        if (job.status === 'success' && !completedWebJobs.has(job.id)) {
          completedWebJobs.add(job.id)
          hasNewSuccess = true
        }
      }
      if (hasNewSuccess) await onDocumentCreated()
      scheduleRefresh(loadWebImports)
    } catch {
      if (version !== loadVersion || currentController.signal.aborted || stopped) return
      webJobsError.value = '网页收藏任务加载失败，系统将自动重试'
      if (notify) ElMessage.error(webJobsError.value)
      if (!stopped) refreshTimer = setTimeout(loadWebImports, 5000)
    } finally {
      if (version === loadVersion) {
        webJobsLoading.value = false
        if (controller === currentController) controller = null
      }
    }
  }

  const initialize = async () => {
    stopped = false
    await loadCapability()
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

  const runJobCommand = async (job, request, successMessage, errorMessage) => {
    if (busyWebJobIds.has(job.id)) return
    busyWebJobIds.add(job.id)
    try {
      await request(job.id, { skipErrorToast: true })
      ElMessage.success(successMessage)
      await loadWebImports()
    } catch (error) {
      notifyRequestError(error, errorMessage)
    } finally {
      busyWebJobIds.delete(job.id)
    }
  }

  const retryWebJob = job => runJobCommand(
    job, retryWebImport, '已重新加入抓取队列', '重新提交抓取任务失败',
  )

  const cancelWebJob = job => runJobCommand(
    job, cancelWebImport, '抓取任务已取消', '取消抓取任务失败',
  )

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
    await runJobCommand(job, async (id, options) => {
      await deleteWebImport(id, options)
      completedWebJobs.delete(id)
    }, '抓取记录已删除', '删除抓取记录失败')
  }

  const stop = () => {
    stopped = true
    loadVersion += 1
    controller?.abort()
    controller = null
    clearTimeout(refreshTimer)
  }

  return {
    webImportSubmitting,
    webImportEnabled,
    webImportError,
    webJobsLoading,
    webJobsError,
    busyWebJobIds,
    initialize,
    submitWebImport,
    retryWebJob,
    cancelWebJob,
    removeWebJob,
    stop,
  }
}
