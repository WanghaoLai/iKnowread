<template>
  <div class="reader" v-loading="loading" :element-loading-text="loadingText">
    <!-- 工具栏 -->
    <div class="reader-toolbar">
      <div class="reader-title" :title="model.title">{{ model.title }}</div>
      <div class="reader-tools">
        <el-tag v-if="model.sourceType === 'url'" size="small" type="success" effect="plain">网页收藏</el-tag>
        <el-link
            v-if="model.sourceType === 'url' && model.sourceUrl"
            :href="model.sourceUrl"
            target="_blank"
            rel="noopener noreferrer nofollow"
            type="primary"
            :title="model.sourceUrl"
        >查看原网页</el-link>
        <el-button
            class="reader-highlight-button"
            size="small"
            :icon="CollectionTag"
            :loading="highlightManager.loading"
            @click="toggleHighlightManager"
        >高亮 {{ highlights.length }}</el-button>
        <div class="reader-search-box">
          <el-input
              v-model="search.query"
              size="small"
              clearable
              maxlength="200"
              :prefix-icon="Search"
              placeholder="搜索文档内容"
              aria-label="搜索文档内容"
              @keyup.enter="runDocumentSearch"
              @clear="closeDocumentSearch"
          />
          <el-button size="small" :icon="Search" :loading="search.loading" @click="runDocumentSearch">搜索</el-button>
        </div>
        <template v-if="model.engine === 'pdfjs'">
          <el-radio-group v-model="readingMode" size="small" aria-label="阅读模式" :disabled="!pdfDoc" @change="changeReadingMode">
            <el-radio-button value="paged">分页阅读</el-radio-button>
            <el-radio-button value="continuous">长文阅读</el-radio-button>
          </el-radio-group>
          <span class="reader-page">{{ pdfDoc ? `${readingMode === 'continuous' ? '当前 ' : ''}${pageNum} / ${numPages}` : '— / —' }}</span>
          <el-button-group>
            <el-button size="small" @click="zoomBy(-0.25)" :disabled="!pdfDoc || zoom <= 0.5">-</el-button>
            <el-button size="small" @click="fitWidth" :disabled="!pdfDoc">适应宽度</el-button>
            <el-button size="small" @click="zoomBy(0.25)" :disabled="!pdfDoc || zoom >= 3">+</el-button>
          </el-button-group>
        </template>
        <el-tag v-if="model.sourceFormat !== 'pdf'" size="small" effect="plain">
          {{ model.sourceFormat.toUpperCase() }} · 长文阅读 · 选择文字可用 AI解释
        </el-tag>
        <el-tag v-if="model.sourceFormat === 'pdf' && ocrBusy" size="small" effect="plain" type="info">
          <el-icon class="is-loading"><Loading /></el-icon>
          {{ ocrStatus === 'processing' ? '正在识别扫描文字' : '等待文字识别' }}
        </el-tag>
        <el-tag
            v-if="model.sourceFormat === 'pdf' && ocrStatus === 'failed'"
            size="small"
            effect="plain"
            type="danger"
            :title="ocrError"
        >{{ ocrDisabled ? 'OCR 未启用' : 'OCR 未完成' }}</el-tag>
        <el-button
            v-if="model.sourceFormat === 'pdf' && ocrStatus === 'failed' && !ocrDisabled"
            size="small"
            :loading="ocrRetrying"
            @click="retryOcr"
        >重试识别</el-button>
        <el-tag
            v-if="model.sourceFormat === 'pdf'"
            class="reader-selection-hint"
            size="small"
            effect="plain"
            :type="selectableTextCount ? 'success' : 'warning'"
        >
          {{ selectionHint }}
        </el-tag>
      </div>
    </div>

    <DocumentSearchResults
        v-if="search.open"
        :search="search"
        @close="closeDocumentSearch"
        @select="jumpToSearchResult"
    />

    <DocumentHighlightManager
        v-if="highlightManager.open"
        :highlights="highlights"
        :loading="highlightManager.loading"
        @close="highlightManager.open = false"
        @locate="locateManagedHighlight"
        @edit="editManagedHighlight"
        @remove="removeHighlight"
    />

    <!-- 渲染区：PDF.js 画布 / DOCX / Markdown 长文容器 -->
    <div class="reader-body" ref="bodyRef">
      <div v-if="error" class="reader-error">
        <el-icon :size="40"><WarningFilled /></el-icon>
        <div>{{ error }}</div>
        <el-button size="small" type="primary" :icon="Refresh" @click="load">重试</el-button>
      </div>
      <div v-else-if="!pdfDoc && model.engine === 'pdfjs' && !loading" class="reader-empty">暂无内容</div>
      <div v-show="model.engine === 'pdfjs'" class="reader-canvas-wrap" :class="{ continuous: readingMode === 'continuous' }">
        <div v-show="readingMode === 'paged'" ref="pageSurfaceRef" class="reader-page-surface">
          <canvas ref="canvasRef"></canvas>
          <div ref="textLayerRef" class="textLayer" tabindex="0" aria-label="PDF 可选择文字层"></div>
        </div>
        <div v-show="readingMode === 'continuous'" ref="continuousRef" class="reader-continuous" aria-label="PDF 长文连续阅读区"></div>
      </div>
      <div v-show="model.engine === 'docx'" class="reader-longform reader-docx" ref="docxRef" tabindex="0"></div>
      <article
          v-show="model.engine === 'markdown'"
          class="reader-longform reader-markdown"
          ref="markdownRef"
          tabindex="0"
          aria-label="Markdown 文档内容"
      ></article>
    </div>

    <Transition name="reader-pager-fade">
      <nav
          v-if="model.engine === 'pdfjs' && pdfDoc && readingMode === 'paged'"
          class="reader-floating-pagination"
          aria-label="分页导航"
      >
        <el-button
            circle
            :icon="ArrowLeft"
            :disabled="pageNum <= 1"
            aria-label="上一页"
            title="上一页"
            @click="goPage(pageNum - 1)"
        />
        <span class="reader-floating-page" aria-live="polite">{{ pageNum }} / {{ numPages }}</span>
        <el-button
            circle
            :icon="ArrowRight"
            :disabled="pageNum >= numPages"
            aria-label="下一页"
            title="下一页"
            @click="goPage(pageNum + 1)"
        />
      </nav>
    </Transition>

    <SelectionExplainPanel
        ref="explainRef"
        :explain="explain"
        :selection-highlight="selectionHighlight"
        @close="closeExplanation(true)"
        @configure="goToConfig"
        @retry="requestExplanation"
        @save-highlight="saveSelectionHighlight"
        @cancel-highlight="selectionHighlight.open = false"
        @toggle-highlight="toggleHighlightCompose"
        @show-highlight="showSavedSelectionHighlight"
        @copy="copyExplanation"
        @save-note="saveExplanationNote"
        @cancel-note="explain.noteOpen = false"
        @toggle-note="explain.noteOpen = !explain.noteOpen"
        @show-notes="goToNotes"
        @update-highlight-remark="selectionHighlight.remark = $event; selectionHighlight.remarkTouched = true"
        @update-note-remark="explain.noteRemark = $event"
    />

    <DocumentHighlightDetail
        ref="highlightDetailRef"
        :detail="highlightDetail"
        @close="closeHighlightDetail"
        @edit="beginHighlightEdit"
        @cancel-edit="highlightDetail.editing = false"
        @save="saveHighlightRemark"
        @locate="locateDetailHighlight"
        @remove="removeHighlight"
        @update:remark="highlightDetail.remark = $event"
    />
  </div>
</template>

<script setup>
import { computed, nextTick, onBeforeUnmount, onMounted, ref, shallowRef, watch } from 'vue'
import { useRouter } from 'vue-router'
import { ArrowLeft, ArrowRight, CollectionTag, Loading, Refresh, Search, WarningFilled } from '@element-plus/icons-vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import DocumentHighlightDetail from '@/components/document-reader/DocumentHighlightDetail.vue'
import DocumentHighlightManager from '@/components/document-reader/DocumentHighlightManager.vue'
import DocumentSearchResults from '@/components/document-reader/DocumentSearchResults.vue'
import SelectionExplainPanel from '@/components/document-reader/SelectionExplainPanel.vue'
import { useDocumentHighlights } from '@/composables/useDocumentHighlights'
import { useDocumentLoader } from '@/composables/useDocumentLoader'
import { useDocumentOcr } from '@/composables/useDocumentOcr'
import { useDocumentSearch } from '@/composables/useDocumentSearch'
import { isPdfRenderCancellation as isRenderCancellation, usePdfRenderer } from '@/composables/usePdfRenderer'
import { useReadingProgress } from '@/composables/useReadingProgress'
import { useSelectionExplanation } from '@/composables/useSelectionExplanation'
import { deleteHighlight, listHighlights, updateHighlight } from '@/api/highlights'
import { notifyRequestError } from '@/utils/request'
import { getDocumentOcrStatus, retryDocumentOcr } from '@/api/documents'
import {
  isSourceAnchor,
  resolveAnchorRange,
} from '@/utils/sourceAnchor'

const READING_MODE_KEY = 'iknowread:pdf-reading-mode'
const props = defineProps({
  model: { type: Object, required: true },
  initialAnchor: { type: Object, default: null },
})
const router = useRouter()
const loading = ref(false)
const loadingText = ref('加载中...')
const error = ref('')
// PDFDocumentProxy contains native private fields, so it must never be deeply proxied.
const pdfDoc = shallowRef(null)
const pageNum = ref(1)
const numPages = ref(0)
const selectableTextCount = ref(0)
const continuousRenderedCount = ref(0)
const zoom = ref(1)
const readingMode = ref(localStorage.getItem(READING_MODE_KEY) === 'continuous' ? 'continuous' : 'paged')
const bodyRef = ref()
const canvasRef = ref()
const pageSurfaceRef = ref()
const textLayerRef = ref()
const continuousRef = ref()
const docxRef = ref()
const markdownRef = ref()
const highlightDetailRef = ref()
const {
  highlights,
  highlightManager,
  highlightDetail,
  selectionHighlight,
  replaceAll: replaceHighlights,
  clear: clearHighlights,
  openDetail: openHighlightState,
  closeDetail: closeHighlightDetail,
  beginDetailEdit: beginHighlightEditState,
  resetSelection: resetSelectionHighlight,
  upsert: upsertHighlight,
  removeLocal: removeHighlightState,
  setResolvedRanges,
  clearResolvedRanges,
  rangeFor: rangeForHighlight,
  findResolved: findResolvedHighlight,
} = useDocumentHighlights()
let resizeObserver = null
let resizeTimer = null
let highlightLoadSequence = 0
let appliedInitialAnchor = ''

const {
  activeUrl,
  contentVersion,
  ocrStatus,
  ocrError,
  ocrRetrying,
  ocrBusy,
  ocrDisabled,
  retry: retryOcr,
  sync: syncOcr,
  stop: stopOcr,
} = useDocumentOcr({
  getModel: () => props.model,
  reload: () => load(),
  notifyReady: () => ElMessage.success('文档处理完成，已刷新可搜索内容'),
  fetchStatus: getDocumentOcrStatus,
  requestRetry: id => retryDocumentOcr(id, { skipErrorToast: true }),
  notifyRetryError: error => notifyRequestError(error, '重新提交文字识别失败，请重试'),
})
const selectionHint = computed(() => {
  if (selectableTextCount.value) return '拖动选择文字 · AI解释'
  if (ocrBusy.value) return '扫描文字识别完成后将自动刷新'
  if (ocrStatus.value === 'failed') return readingMode.value === 'continuous' ? '当前文档没有可选择文字' : '当前页没有可选择文字'
  if (readingMode.value === 'continuous' && continuousRenderedCount.value < numPages.value) return '滚动加载页面文字层 · 可选择文字'
  return readingMode.value === 'continuous' ? '当前文档没有可选择文字' : '此页没有可选择文字'
})

const currentSourceModel = () => ({
  id: props.model.id,
  contentVersion: contentVersion.value,
  sourceFormat: props.model.sourceFormat,
})

const longformElement = () => (
  props.model.engine === 'markdown' ? markdownRef.value : docxRef.value
)

const {
  scrollProgression,
  persist: persistReadingProgress,
  flush: flushReadingProgress,
  load: loadStoredReadingProgress,
  cancel: cancelReadingProgress,
} = useReadingProgress({
  getSourceModel: currentSourceModel,
  getSourceFormat: () => props.model.sourceFormat,
  getPage: () => pageNum.value,
  getPageCount: () => numPages.value,
  getReadingMode: () => readingMode.value,
  getScrollElement: () => bodyRef.value,
})

const rangeScope = range => {
  if (props.model.sourceFormat !== 'pdf') {
    return { element: longformElement(), page: null }
  }
  const common = range.commonAncestorContainer.nodeType === Node.ELEMENT_NODE
    ? range.commonAncestorContainer
    : range.commonAncestorContainer.parentElement
  const layer = common?.closest?.('.textLayer')
  if (!layer) return null
  const slot = layer.closest('.continuous-page')
  return {
    element: layer,
    page: slot ? Number(slot.dataset.pageNumber) : pageNum.value,
  }
}

const clearSourceHighlight = () => {
  if (window.CSS?.highlights) window.CSS.highlights.delete('iknowread-source-anchor')
}

const clearPersistentHighlightRanges = () => {
  clearResolvedRanges()
  if (window.CSS?.highlights) window.CSS.highlights.delete('iknowread-persistent-highlights')
}

const {
  setLoadingTask: setPdfLoadingTask,
  clearLoadingTask: clearPdfLoadingTask,
  updateContinuousPageNumber,
  fitToWidth,
  fitWidth,
  goPage,
  zoomBy,
  changeReadingMode,
  renderedTextLayer,
  ensureTextLayer,
  destroy: destroyPdf,
} = usePdfRenderer({
  pdfDoc,
  pageNum,
  numPages,
  zoom,
  readingMode,
  loading,
  loadingText,
  selectableTextCount,
  continuousRenderedCount,
  bodyRef,
  canvasRef,
  pageSurfaceRef,
  textLayerRef,
  continuousRef,
  onBeforeRender: () => {
    closeExplanation(true)
    clearSourceHighlight()
    clearPersistentHighlightRanges()
  },
  onTextRendered: () => applyPersistentHighlights(),
  onProgress: () => persistReadingProgress(),
  onError: exception => { error.value = exception?.message || '页面渲染失败' },
  readingModeStorageKey: READING_MODE_KEY,
})

const renderedScopeForHighlight = anchor => {
  if (anchor.source_format !== 'pdf') return longformElement()
  return renderedTextLayer(anchor.page)
}

const applyPersistentHighlights = () => {
  clearPersistentHighlightRanges()
  const ranges = []
  const resolved = []
  for (const item of highlights.value) {
    const scope = renderedScopeForHighlight(item.source_anchor)
    const range = scope ? resolveAnchorRange(scope, item.source_anchor) : null
    if (!range) continue
    ranges.push(range)
    resolved.push({ item, range })
  }
  setResolvedRanges(resolved)
  if (ranges.length && window.CSS?.highlights && window.Highlight) {
    window.CSS.highlights.set('iknowread-persistent-highlights', new window.Highlight(...ranges))
  }
}

const loadHighlights = async () => {
  const sequence = ++highlightLoadSequence
  const documentId = Number(props.model.id)
  const documentVersion = contentVersion.value
  if (!Number.isInteger(documentId) || !documentVersion) {
    replaceHighlights([])
    clearPersistentHighlightRanges()
    return
  }
  highlightManager.loading = true
  try {
    const response = await listHighlights({ documentId, documentVersion })
    if (
      sequence !== highlightLoadSequence
      || documentId !== Number(props.model.id)
      || documentVersion !== contentVersion.value
    ) return
    replaceHighlights(response.data || [])
    await nextTick()
    applyPersistentHighlights()
  } catch (_) {
    replaceHighlights([])
    clearPersistentHighlightRanges()
  } finally {
    if (sequence === highlightLoadSequence) highlightManager.loading = false
  }
}

const toggleHighlightManager = async () => {
  highlightManager.open = !highlightManager.open
  if (highlightManager.open) closeDocumentSearch()
  if (highlightManager.open && !highlights.value.length && !highlightManager.loading) {
    await loadHighlights()
  }
}

const scrollReaderTo = (top, behavior = 'smooth') => {
  const body = bodyRef.value
  if (!body) return
  const maximum = Math.max(0, body.scrollHeight - body.clientHeight)
  body.scrollTo({
    top: Math.max(0, Math.min(maximum, Number(top) || 0)),
    left: body.scrollLeft,
    behavior,
  })
}

const scrollRangeIntoReader = (range, behavior = 'smooth') => {
  const body = bodyRef.value
  if (!body) return
  const rangeRect = range.getBoundingClientRect()
  const bodyRect = body.getBoundingClientRect()
  const centeredTop = body.scrollTop + rangeRect.top - bodyRect.top
    - Math.max(16, (body.clientHeight - rangeRect.height) / 2)
  scrollReaderTo(centeredTop, behavior)
}

const showSourceRange = (range, { behavior = 'smooth' } = {}) => {
  clearSourceHighlight()
  window.getSelection()?.removeAllRanges()
  if (window.CSS?.highlights && window.Highlight) {
    window.CSS.highlights.set('iknowread-source-anchor', new window.Highlight(range))
  } else {
    const selection = window.getSelection()
    selection?.addRange(range)
  }
  scrollRangeIntoReader(range, behavior)
}

const scopeForAnchor = async (anchor, { behavior = 'smooth' } = {}) => {
  if (anchor.source_format !== 'pdf') return longformElement()
  const scope = await ensureTextLayer(anchor.page)
  if (!scope) return null
  if (scope.offsetTop !== null) scrollReaderTo(scope.offsetTop - 16, behavior)
  return scope.element
}

const jumpToAnchor = async (anchor, { silent = false, behavior = 'smooth' } = {}) => {
  if (!isSourceAnchor(anchor)) {
    if (!silent) ElMessage.warning('原文定位数据无效')
    return false
  }
  if (Number(anchor.document_id) !== Number(props.model.id)) {
    if (!silent) ElMessage.warning('该定位不属于当前文档')
    return false
  }
  if (anchor.document_version !== contentVersion.value) {
    if (!silent) ElMessage.warning('原文来自其他内容版本，无法在当前文档中定位')
    return false
  }
  if (anchor.source_format !== props.model.sourceFormat) {
    if (!silent) ElMessage.warning('原文定位格式与当前文档不一致')
    return false
  }
  const scope = await scopeForAnchor(anchor, { behavior })
  if (!scope) return false
  if (!anchor.selector) {
    if ((anchor.source_format !== 'pdf' || readingMode.value === 'continuous') && bodyRef.value) {
      const maximum = Math.max(0, bodyRef.value.scrollHeight - bodyRef.value.clientHeight)
      scrollReaderTo(maximum * anchor.progression, behavior)
    }
    persistReadingProgress()
    return true
  }
  const range = resolveAnchorRange(scope, anchor)
  if (!range) {
    if (!silent) ElMessage.warning('没有找到对应原文，文档排版可能已经变化')
    return false
  }
  showSourceRange(range, { behavior })
  persistReadingProgress()
  return true
}

const {
  search,
  close: closeDocumentSearch,
  run: runDocumentSearch,
  select: jumpToSearchResult,
} = useDocumentSearch({
  getSourceModel: currentSourceModel,
  getSourceFormat: () => props.model.sourceFormat,
  getPdfDocument: () => pdfDoc.value,
  getDocumentElement: longformElement,
  beforeOpen: () => { highlightManager.open = false },
  jumpToAnchor,
})

const selectionBelongsToReader = range => {
  const node = range.commonAncestorContainer
  return !!bodyRef.value && (node === bodyRef.value || bodyRef.value.contains(node))
}

const {
  explain,
  explainRef,
  position: positionExplanation,
  close: closeExplanation,
  request: requestExplanation,
  captureSelection,
  copy: copyExplanation,
  toggleHighlight: toggleHighlightCompose,
  saveHighlight: saveSelectionHighlight,
  showSavedHighlight: showSavedSelectionHighlight,
  saveNote: saveExplanationNote,
  clearCache: clearExplanationCache,
  stop: stopExplanation,
} = useSelectionExplanation({
  getDocumentId: () => props.model.id,
  getContentVersion: () => contentVersion.value,
  getSourceModel: currentSourceModel,
  getRangeScope: rangeScope,
  selectionBelongsToReader,
  getScrollProgression: scrollProgression,
  selectionHighlight,
  resetSelectionHighlight,
  upsertHighlight,
  afterHighlightSaved: applyPersistentHighlights,
  findHighlight: id => highlights.value.find(item => item.id === id),
  showHighlight: (item, fallbackRect) => {
    const rect = rangeForHighlight(item)?.getBoundingClientRect() || fallbackRect
    openHighlightDetail(item, rect)
  },
})

const positionHighlightDetail = async () => {
  const rect = highlightDetail.anchorRect
  if (!rect) return
  await nextTick()
  const element = highlightDetailRef.value?.element
  const width = Math.min(element?.offsetWidth || 360, window.innerWidth - 24)
  const height = Math.min(element?.offsetHeight || 260, window.innerHeight - 24)
  highlightDetail.left = Math.max(12, Math.min(window.innerWidth - width - 12, rect.left + rect.width / 2 - width / 2))
  const below = rect.bottom + 10
  highlightDetail.top = below + height <= window.innerHeight - 12
    ? below
    : Math.max(12, rect.top - height - 10)
}

const openHighlightDetail = (item, rect = null, { edit = false } = {}) => {
  if (!item) return
  closeExplanation(false)
  const fallback = {
    left: Math.max(12, window.innerWidth / 2 - 1),
    right: Math.max(12, window.innerWidth / 2 + 1),
    top: Math.max(12, window.innerHeight / 2 - 1),
    bottom: Math.max(12, window.innerHeight / 2 + 1),
    width: 2,
    height: 2,
  }
  openHighlightState(item, rect || fallback, { edit })
  positionHighlightDetail()
}

const beginHighlightEdit = () => {
  if (!highlightDetail.item) return
  beginHighlightEditState()
  positionHighlightDetail()
}

const saveHighlightRemark = async () => {
  const item = highlightDetail.item
  if (!item || highlightDetail.saving) return
  highlightDetail.saving = true
  try {
    const response = await updateHighlight(item.id, { remark: highlightDetail.remark })
    const updated = response.data
    upsertHighlight(updated)
    highlightDetail.editing = false
    applyPersistentHighlights()
    ElMessage.success('高亮备注已更新')
  } catch (error) {
    notifyRequestError(error, '高亮备注保存失败，请重试')
  } finally {
    highlightDetail.saving = false
    positionHighlightDetail()
  }
}

const locateManagedHighlight = async (item, { open = true, edit = false } = {}) => {
  highlightManager.open = false
  const located = await jumpToAnchor(item.source_anchor)
  if (!located || !open) return
  // 等待平滑定位结束，避免滚动处理立即关闭刚打开的备注卡片。
  await new Promise(resolve => window.setTimeout(resolve, 360))
  await nextTick()
  applyPersistentHighlights()
  const rect = rangeForHighlight(item)?.getBoundingClientRect()
  openHighlightDetail(item, rect, { edit })
}

const editManagedHighlight = item => locateManagedHighlight(item, { edit: true })

const locateDetailHighlight = async () => {
  const item = highlightDetail.item
  if (!item) return
  closeHighlightDetail()
  await locateManagedHighlight(item, { open: true })
}

const removeHighlight = async item => {
  if (!item) return
  // 悬浮窗层级（4000+）必须盖过外层 el-dialog（约 2000），而 ElMessageBox 的
  // 层级低于悬浮窗；先关闭悬浮窗再确认，避免确认框被悬浮窗遮挡。
  closeHighlightDetail()
  highlightManager.open = false
  try {
    await ElMessageBox.confirm('删除后，高亮及其备注将无法恢复。', '删除高亮', {
      type: 'warning', confirmButtonText: '删除', cancelButtonText: '取消',
    })
  } catch (_) {
    return
  }
  try {
    await deleteHighlight(item.id)
  } catch (error) {
    notifyRequestError(error, '高亮删除失败，请重试')
    return
  }
  removeHighlightState(item.id)
  applyPersistentHighlights()
  ElMessage.success('高亮已删除')
}

const caretPointFromEvent = event => {
  if (document.caretPositionFromPoint) {
    const point = document.caretPositionFromPoint(event.clientX, event.clientY)
    return point ? { node: point.offsetNode, offset: point.offset } : null
  }
  const range = document.caretRangeFromPoint?.(event.clientX, event.clientY)
  return range ? { node: range.startContainer, offset: range.startOffset } : null
}

const pointInsideRange = (range, point) => {
  try {
    return range.isPointInRange(point.node, point.offset)
  } catch (_) {
    return false
  }
}

const handleHighlightClick = event => {
  const selection = window.getSelection()
  if (selection && !selection.isCollapsed) return
  if (!event.target.closest?.('.textLayer, .reader-longform')) return
  const point = caretPointFromEvent(event)
  if (!point) return
  const resolved = findResolvedHighlight(entry => pointInsideRange(entry.range, point))
  if (!resolved) return
  event.preventDefault()
  openHighlightDetail(resolved.item, resolved.range.getBoundingClientRect())
}

const goToNotes = () => {
  closeExplanation(true)
  router.push('/manager/notes')
}

const goToConfig = () => {
  closeExplanation(true)
  router.push('/manager/api-config')
}

const handleDocumentPointerDown = event => {
  if (explain.visible && !explainRef.value?.element?.contains(event.target)) closeExplanation(false)
  if (
    highlightDetail.visible
    && !highlightDetailRef.value?.element?.contains(event.target)
    && !event.target.closest?.('.reader-highlight-manager')
  ) closeHighlightDetail()
}

const handleBodyScroll = () => {
  closeExplanation(true)
  closeHighlightDetail()
  updateContinuousPageNumber()
  if (!loading.value) persistReadingProgress()
}
const handleWindowResize = () => closeExplanation()

const sourcePositionToRestore = () => {
  const initial = props.initialAnchor
  const signature = initial ? JSON.stringify(initial) : ''
  if (initial && signature !== appliedInitialAnchor) {
    return { anchor: initial, signature, silent: false }
  }
  const progress = loadStoredReadingProgress()
  return progress ? { anchor: progress, signature: '', silent: true } : null
}

const restoreSourcePosition = async (restoration = sourcePositionToRestore()) => {
  if (!restoration) return
  if (restoration.signature) appliedInitialAnchor = restoration.signature
  await jumpToAnchor(restoration.anchor, {
    silent: restoration.silent,
    behavior: 'auto',
  })
}

const { load, stop: stopDocumentLoad } = useDocumentLoader({
  getModel: () => props.model,
  getActiveUrl: () => activeUrl.value,
  getContentVersion: () => contentVersion.value,
  getLongformElement: longformElement,
  docxRef,
  markdownRef,
  bodyRef,
  pageNum,
  loading,
  loadingText,
  error,
  pdfDoc,
  numPages,
  onReset: () => {
    cancelReadingProgress()
    highlightLoadSequence += 1
    closeExplanation(true)
    closeHighlightDetail()
    clearSourceHighlight()
    clearPersistentHighlightRanges()
    clearHighlights()
    closeDocumentSearch()
    clearExplanationCache()
  },
  getRestoration: sourcePositionToRestore,
  destroyPdf,
  setPdfLoadingTask,
  clearPdfLoadingTask,
  fitToWidth,
  loadHighlights,
  restoreSourcePosition,
  isRenderCancellation,
})

watch(() => [props.model.id, props.model.url, props.model.engine, props.model.contentVersion, props.model.ocrUpdatedAt], () => {
  syncOcr(props.model)
  load()
}, { immediate: true })

watch(() => props.initialAnchor, async anchor => {
  if (!anchor || loading.value) return
  const signature = JSON.stringify(anchor)
  if (signature === appliedInitialAnchor) return
  appliedInitialAnchor = signature
  await jumpToAnchor(anchor)
}, { deep: true })

onMounted(() => {
  bodyRef.value?.addEventListener('mouseup', captureSelection)
  bodyRef.value?.addEventListener('touchend', captureSelection)
  bodyRef.value?.addEventListener('keyup', captureSelection)
  bodyRef.value?.addEventListener('click', handleHighlightClick)
  bodyRef.value?.addEventListener('scroll', handleBodyScroll, { passive: true })
  document.addEventListener('pointerdown', handleDocumentPointerDown, true)
  window.addEventListener('resize', handleWindowResize)
  resizeObserver = new ResizeObserver(() => {
    clearTimeout(resizeTimer)
    resizeTimer = setTimeout(() => {
      if (pdfDoc.value && !loading.value) fitWidth()
    }, 120)
  })
  if (bodyRef.value) resizeObserver.observe(bodyRef.value)
})

onBeforeUnmount(() => {
  if (!loading.value) flushReadingProgress()
  stopDocumentLoad()
  clearTimeout(resizeTimer)
  cancelReadingProgress()
  stopOcr()
  resizeObserver?.disconnect()
  bodyRef.value?.removeEventListener('mouseup', captureSelection)
  bodyRef.value?.removeEventListener('touchend', captureSelection)
  bodyRef.value?.removeEventListener('keyup', captureSelection)
  bodyRef.value?.removeEventListener('click', handleHighlightClick)
  bodyRef.value?.removeEventListener('scroll', handleBodyScroll)
  stopExplanation()
  closeDocumentSearch()
  highlightLoadSequence += 1
  clearSourceHighlight()
  clearPersistentHighlightRanges()
  document.removeEventListener('pointerdown', handleDocumentPointerDown, true)
  window.removeEventListener('resize', handleWindowResize)
  destroyPdf()
})

defineExpose({ reload: load, jumpToAnchor })
</script>

<style scoped>
.reader {
  position: relative;
  display: flex;
  flex-direction: column;
  height: 100%;
  min-width: 0;
  min-height: 0;
  box-sizing: border-box;
  background: #fff;
  border-radius: 14px;
  border: 1px solid rgba(0, 69, 183, .06);
  overflow: hidden;
  contain: layout paint;
}
.reader-toolbar {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 10px;
  padding: 10px 14px;
  border-bottom: 1px solid var(--ik-border);
  background: linear-gradient(180deg, #f4fbfe, #fff);
  flex-wrap: wrap;
  box-sizing: border-box;
}
.reader-title {
  font-weight: 600;
  color: #24384c;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  max-width: 40%;
}
.reader-tools {
  display: flex;
  align-items: center;
  gap: 10px;
  flex-wrap: wrap;
  justify-content: flex-end;
  min-height: 32px;
}
.reader-highlight-button {
  min-width: 76px;
}
.reader-search-box {
  display: flex;
  align-items: center;
  gap: 6px;
  width: 248px;
}
.reader-search-box :deep(.el-input) { min-width: 0; }
.reader-selection-hint {
  width: 190px;
  justify-content: center;
  box-sizing: border-box;
}
.reader-page {
  font-size: 13px;
  color: var(--ik-text-sub);
  width: 74px;
  height: 24px;
  line-height: 24px;
  flex: none;
  text-align: center;
}
.reader-body {
  flex: 1;
  min-width: 0;
  min-height: 0;
  overflow: auto;
  scrollbar-gutter: stable;
  overscroll-behavior: contain; /* 触底/触顶不再把滚动传给外层页面 */
  overflow-anchor: none;
  background: #eef6fa;
  position: relative;
}
.reader-canvas-wrap {
  display: flex;
  justify-content: center;
  padding: 16px 0;
}
.reader-canvas-wrap.continuous {
  display: block;
  padding: 18px 0 28px;
}
.reader-continuous {
  width: max-content;
  min-width: 100%;
}
.reader-continuous :deep(.continuous-page) {
  position: relative;
  width: 100%;
  display: flex;
  justify-content: center;
  box-sizing: border-box;
  padding: 0 24px;
  margin-bottom: 22px;
}
.reader-continuous :deep(.continuous-page:last-child) { margin-bottom: 0; }
.reader-continuous :deep(.continuous-page-number) {
  position: absolute;
  z-index: 3;
  top: 8px;
  right: 32px;
  padding: 4px 8px;
  color: #fff;
  font-size: 11px;
  border-radius: 10px;
  background: rgba(34, 57, 78, .68);
  pointer-events: none;
}
.reader-continuous :deep(.reader-page-surface) {
  position: relative;
  flex: none;
  box-shadow: 0 4px 18px rgba(0, 56, 157, .18);
  border-radius: 2px;
  background: #fff;
}
.reader-continuous :deep(.reader-page-surface canvas) { display: block; }
.reader-continuous :deep(.continuous-page-status) {
  position: absolute;
  inset: 0;
  display: flex;
  align-items: center;
  justify-content: center;
  color: var(--ik-text-sub);
  font-size: 13px;
  pointer-events: none;
}
.reader-continuous :deep(.continuous-page-status:empty) { display: none; }
.reader-continuous :deep(.continuous-page-status.error) { color: var(--el-color-danger); }
.reader-page-surface {
  position: relative;
  box-shadow: 0 4px 18px rgba(0, 56, 157, .18);
  border-radius: 2px;
  background: #fff;
}
.reader-page-surface canvas {
  display: block;
}
.textLayer {
  position: absolute;
  inset: 0;
  overflow: clip;
  line-height: 1;
  text-align: initial;
  text-size-adjust: none;
  forced-color-adjust: none;
  transform-origin: 0 0;
  z-index: 1;
}
.textLayer:focus { outline: none; }
.reader-continuous :deep(.textLayer) {
  position: absolute;
  inset: 0;
  overflow: clip;
  line-height: 1;
  text-align: initial;
  text-size-adjust: none;
  forced-color-adjust: none;
  transform-origin: 0 0;
  z-index: 1;
}
.reader-continuous :deep(.textLayer:focus) { outline: none; }
.textLayer :deep(span),
.textLayer :deep(br) {
  position: absolute;
  color: transparent;
  white-space: pre;
  cursor: text;
  transform-origin: 0 0;
}
.reader-continuous :deep(.textLayer span),
.reader-continuous :deep(.textLayer br) {
  position: absolute;
  color: transparent;
  white-space: pre;
  cursor: text;
  transform-origin: 0 0;
}
.textLayer :deep(span.markedContent) {
  top: 0;
  height: 0;
}
.reader-continuous :deep(.textLayer span.markedContent) { top: 0; height: 0; }
.textLayer :deep(span[role="img"]) {
  user-select: none;
  cursor: default;
}
.reader-continuous :deep(.textLayer span[role="img"]) { user-select: none; cursor: default; }
.textLayer :deep(::selection),
.reader-longform :deep(::selection) {
  background: rgba(48, 218, 212, .34);
}
.reader-continuous :deep(.textLayer ::selection) { background: rgba(48, 218, 212, .34); }
:global(::highlight(iknowread-source-anchor)) {
  background: rgba(255, 193, 7, .52);
}
:global(::highlight(iknowread-persistent-highlights)) {
  background: rgba(255, 213, 71, .64);
  text-decoration: underline rgba(197, 136, 0, .72) 1px;
}
.reader-longform {
  background: #fff;
  max-width: 900px;
  margin: 16px auto;
  padding: 24px 32px;
  box-shadow: 0 4px 18px rgba(0, 56, 157, .18);
  border-radius: 2px;
}
.reader-longform:focus { outline: none; }
.reader-markdown {
  box-sizing: border-box;
  min-height: calc(100% - 32px);
  color: #273b4d;
  font-size: 16px;
  line-height: 1.78;
  overflow-wrap: anywhere;
}
.reader-markdown :deep(h1),
.reader-markdown :deep(h2),
.reader-markdown :deep(h3),
.reader-markdown :deep(h4),
.reader-markdown :deep(h5),
.reader-markdown :deep(h6) {
  margin: 1.35em 0 .65em;
  color: #173c5a;
  line-height: 1.3;
}
.reader-markdown :deep(h1) { margin-top: 0; padding-bottom: .3em; border-bottom: 1px solid var(--ik-border); }
.reader-markdown :deep(h2) { padding-bottom: .25em; border-bottom: 1px solid rgba(184, 213, 228, .65); }
.reader-markdown :deep(p),
.reader-markdown :deep(ul),
.reader-markdown :deep(ol),
.reader-markdown :deep(blockquote),
.reader-markdown :deep(pre),
.reader-markdown :deep(table) { margin: 0 0 1em; }
.reader-markdown :deep(blockquote) {
  padding: .15em 1em;
  color: #587186;
  border-left: 4px solid var(--ik-cyan-deep);
  background: #f4fbfd;
}
.reader-markdown :deep(code) {
  padding: .12em .35em;
  border-radius: 4px;
  color: #b4235a;
  background: #f4f6f8;
  font-family: ui-monospace, SFMono-Regular, Menlo, Consolas, monospace;
  font-size: .9em;
}
.reader-markdown :deep(pre) {
  overflow: auto;
  padding: 14px 16px;
  border-radius: 8px;
  background: #182633;
}
.reader-markdown :deep(pre code) { padding: 0; color: #edf6fa; background: transparent; }
.reader-markdown :deep(table) { display: block; width: 100%; overflow-x: auto; border-collapse: collapse; }
.reader-markdown :deep(th),
.reader-markdown :deep(td) { padding: 7px 10px; border: 1px solid var(--ik-border); }
.reader-markdown :deep(th) { background: #f1f8fb; }
.reader-markdown :deep(img) { max-width: 100%; height: auto; }
.reader-markdown :deep(a) { color: var(--ik-blue); text-decoration: underline; text-underline-offset: 2px; }
@media (max-width: 760px) {
  .reader-search-box { width: 100%; }
}
.reader-floating-pagination {
  position: absolute;
  z-index: 12;
  left: 50%;
  bottom: 18px;
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 7px 9px;
  transform: translateX(-50%);
  color: #fff;
  background: rgba(25, 54, 79, .82);
  border: 1px solid rgba(255, 255, 255, .3);
  border-radius: 999px;
  box-shadow: 0 10px 28px rgba(0, 45, 105, .26);
  backdrop-filter: blur(12px);
  -webkit-backdrop-filter: blur(12px);
}
.reader-floating-pagination :deep(.el-button) {
  width: 34px;
  height: 34px;
  margin: 0;
  color: #1f6187;
  border: 0;
  background: rgba(255, 255, 255, .94);
  box-shadow: none;
}
.reader-floating-pagination :deep(.el-button:not(.is-disabled):hover),
.reader-floating-pagination :deep(.el-button:not(.is-disabled):focus-visible) {
  color: #fff;
  background: var(--ik-cyan-deep);
}
.reader-floating-pagination :deep(.el-button.is-disabled) {
  color: rgba(47, 76, 96, .4);
  background: rgba(255, 255, 255, .62);
}
.reader-floating-page {
  min-width: 54px;
  color: #fff;
  font-size: 12px;
  font-variant-numeric: tabular-nums;
  text-align: center;
  user-select: none;
}
.reader-pager-fade-enter-active,
.reader-pager-fade-leave-active {
  transition: opacity .18s ease, transform .18s ease;
}
.reader-pager-fade-enter-from,
.reader-pager-fade-leave-to {
  opacity: 0;
  transform: translate(-50%, 8px) scale(.96);
}
.reader-error {
  height: 100%;
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  gap: 12px;
  color: var(--el-color-danger);
}
.reader-empty {
  height: 100%;
  display: flex;
  align-items: center;
  justify-content: center;
  color: var(--ik-text-sub);
}

</style>
