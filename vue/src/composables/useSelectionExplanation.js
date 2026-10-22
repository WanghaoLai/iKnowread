import { nextTick, reactive, ref } from 'vue'
import { ElMessage } from 'element-plus'
import { explainSelection } from '@/api/ai'
import { createHighlight } from '@/api/highlights'
import { createNote } from '@/api/notes'
import { notifyRequestError } from '@/utils/request'
import { anchorFromRange, isSourceAnchor } from '@/utils/sourceAnchor'

const emptyExplanation = () => ({
  visible: false,
  selection: '',
  answer: '',
  model: '',
  modelName: '',
  provider: '',
  providerName: '',
  configName: '',
  documentVersion: '',
  sourceAnchor: null,
  error: '',
  needsConfig: false,
  loading: false,
  copied: false,
  noteOpen: false,
  noteRemark: '',
  noteSaving: false,
  noteSaved: false,
  noteId: null,
  left: 12,
  top: 12,
  anchorRect: null,
})

const normalizeSelection = value => value
  .replace(/\u00a0/g, ' ')
  .replace(/\s+/g, ' ')
  .replace(/([\u3400-\u9fff])\s+(?=[\u3400-\u9fff])/g, '$1')
  .trim()

export const useSelectionExplanation = ({
  getDocumentId,
  getContentVersion,
  getSourceModel,
  getRangeScope,
  selectionBelongsToReader,
  getScrollProgression,
  selectionHighlight,
  resetSelectionHighlight,
  upsertHighlight,
  afterHighlightSaved,
  findHighlight,
  showHighlight,
}) => {
  const explain = reactive(emptyExplanation())
  const explainRef = ref()
  const explanationCache = new Map()
  let controller = null

  const position = async () => {
    const rect = explain.anchorRect
    if (!rect) return
    await nextTick()
    const element = explainRef.value?.element
    const width = Math.min(element?.offsetWidth || 380, window.innerWidth - 24)
    const height = Math.min(element?.offsetHeight || 260, window.innerHeight - 24)
    explain.left = Math.max(12, Math.min(window.innerWidth - width - 12, rect.left + rect.width / 2 - width / 2))
    const below = rect.bottom + 12
    explain.top = below + height <= window.innerHeight - 12
      ? below
      : Math.max(12, rect.top - height - 12)
  }

  const close = (clearSelection = false) => {
    controller?.abort()
    controller = null
    explain.visible = false
    explain.loading = false
    if (clearSelection) window.getSelection()?.removeAllRanges()
  }

  const request = async () => {
    const content = explain.selection
    const sourceAnchor = explain.sourceAnchor
    if (!content || !explain.visible || !isSourceAnchor(sourceAnchor)) return
    const cacheKey = `${sourceAnchor.document_id}:${sourceAnchor.document_version}:${sourceAnchor.page || 0}:${sourceAnchor.selector.position.start}:${content}`
    const cached = explanationCache.get(cacheKey)
    if (cached) {
      Object.assign(explain, {
        ...cached, loading: false, error: '', needsConfig: false, copied: false,
        noteOpen: false, noteRemark: '', noteSaving: false, noteSaved: false, noteId: null,
      })
      if (!selectionHighlight.saved && !selectionHighlight.remarkTouched) {
        selectionHighlight.remark = cached.answer || ''
      }
      position()
      return
    }
    controller?.abort()
    controller = new AbortController()
    Object.assign(explain, {
      loading: true, answer: '', model: '', modelName: '', provider: '', providerName: '', configName: '', documentVersion: '',
      error: '', needsConfig: false, copied: false,
      noteOpen: false, noteRemark: '', noteSaving: false, noteSaved: false, noteId: null,
    })
    position()
    try {
      const response = await explainSelection({ content, source_anchor: sourceAnchor }, {
        signal: controller.signal,
        timeout: 135000,
      })
      if (!explain.visible || explain.selection !== content) return
      const label = [response.data.provider_name || response.data.provider, response.data.model]
        .filter(Boolean).join(' · ')
      const value = {
        answer: response.data.content,
        model: label,
        modelName: response.data.model || '',
        provider: response.data.provider || '',
        providerName: response.data.provider_name || '',
        configName: response.data.config_name || '',
        documentVersion: response.data.source_anchor?.document_version || sourceAnchor.document_version,
        sourceAnchor: response.data.source_anchor || sourceAnchor,
      }
      if (explanationCache.size >= 50) explanationCache.delete(explanationCache.keys().next().value)
      explanationCache.set(cacheKey, value)
      Object.assign(explain, { ...value, loading: false })
      if (!selectionHighlight.saved && !selectionHighlight.remarkTouched) {
        selectionHighlight.remark = value.answer || ''
      }
    } catch (exception) {
      if (exception.code === 'ERR_CANCELED' || !explain.visible || explain.selection !== content) return
      const message = exception.response?.data?.msg || '解释失败，请稍后重试'
      Object.assign(explain, {
        loading: false,
        error: message,
        needsConfig: message.includes('API配置') || message.includes('先在'),
      })
    } finally {
      position()
    }
  }

  const captureSelection = () => {
    window.setTimeout(() => {
      const selection = window.getSelection()
      if (!selection || selection.isCollapsed || !selection.rangeCount) return
      const range = selection.getRangeAt(0)
      if (!selectionBelongsToReader(range)) return
      const content = normalizeSelection(selection.toString())
      if (!content) return
      if (content.length > 4000) {
        ElMessage.warning('一次最多解释 4000 个字符，请缩小选取范围')
        return
      }
      const scope = getRangeScope(range)
      const sourceAnchor = scope && anchorFromRange(getSourceModel(), range, scope.element, {
        page: scope.page,
        progression: getScrollProgression(),
      })
      if (!sourceAnchor) {
        ElMessage.warning('无法建立原文定位，请重新选择内容')
        return
      }
      if (
        explain.visible
        && explain.selection === content
        && explain.sourceAnchor?.selector?.position?.start === sourceAnchor.selector.position.start
        && explain.sourceAnchor?.page === sourceAnchor.page
      ) return
      controller?.abort()
      resetSelectionHighlight()
      Object.assign(explain, {
        ...emptyExplanation(),
        visible: true,
        selection: content,
        documentVersion: sourceAnchor.document_version,
        sourceAnchor,
        loading: true,
        anchorRect: range.getBoundingClientRect(),
      })
      position()
      request()
    }, 0)
  }

  const copy = async () => {
    try {
      await navigator.clipboard.writeText(explain.answer)
      explain.copied = true
      window.setTimeout(() => { explain.copied = false }, 1500)
    } catch (_) {
      ElMessage.error('复制失败，请手动复制')
    }
  }

  const toggleHighlight = () => {
    selectionHighlight.open = !selectionHighlight.open
    if (selectionHighlight.open && !selectionHighlight.remarkTouched && !selectionHighlight.remark) {
      selectionHighlight.remark = explain.answer || ''
    }
    position()
  }

  const saveHighlight = async () => {
    if (selectionHighlight.saving || selectionHighlight.saved || !isSourceAnchor(explain.sourceAnchor)) return
    const documentId = Number(getDocumentId())
    if (!Number.isInteger(documentId) || documentId < 1) {
      ElMessage.error('当前文档信息无效，无法保存高亮')
      return
    }
    selectionHighlight.saving = true
    try {
      const remark = selectionHighlight.remarkTouched
        ? selectionHighlight.remark
        : (selectionHighlight.remark || explain.answer || '')
      const response = await createHighlight({
        document_id: documentId,
        source_anchor: explain.sourceAnchor,
        selected_text: explain.selection,
        remark,
        provider: explain.provider || null,
        config_name: explain.configName || null,
        model: explain.modelName || null,
      })
      const created = response.data
      upsertHighlight(created, { selected: true })
      await nextTick()
      afterHighlightSaved()
      window.getSelection()?.removeAllRanges()
      ElMessage.success(created.remark ? '高亮及备注已保存' : '高亮已保存')
    } catch (error) {
      notifyRequestError(error, '高亮保存失败，请重试')
    } finally {
      selectionHighlight.saving = false
      position()
    }
  }

  const showSavedHighlight = () => {
    const item = findHighlight(selectionHighlight.id)
    if (item) showHighlight(item, explain.anchorRect)
  }

  const saveNote = async () => {
    if (!explain.answer || explain.noteSaving || explain.noteSaved) return
    const documentId = Number(getDocumentId())
    if (!Number.isInteger(documentId) || documentId < 1) {
      ElMessage.error('当前文档信息无效，无法添加笔记')
      return
    }
    explain.noteSaving = true
    try {
      const response = await createNote({
        source_type: 'ai_explanation',
        document_id: documentId,
        document_version: explain.documentVersion || getContentVersion(),
        source_anchor: explain.sourceAnchor,
        selected_text: explain.selection,
        content: explain.answer,
        remark: explain.noteRemark,
        provider: explain.provider,
        config_name: explain.configName,
        model: explain.modelName,
      })
      explain.noteId = response.data?.id || null
      explain.noteSaved = true
      explain.noteOpen = false
      ElMessage.success('已加入「我的笔记」')
    } catch (error) {
      notifyRequestError(error, '笔记保存失败，请重试')
    } finally {
      explain.noteSaving = false
      position()
    }
  }

  const clearCache = () => explanationCache.clear()
  const stop = () => {
    controller?.abort()
    controller = null
  }

  return {
    explain,
    explainRef,
    position,
    close,
    request,
    captureSelection,
    copy,
    toggleHighlight,
    saveHighlight,
    showSavedHighlight,
    saveNote,
    clearCache,
    stop,
  }
}
