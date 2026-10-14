<template>
  <div class="reader" v-loading="loading" :element-loading-text="loadingText">
    <!-- 工具栏 -->
    <div class="reader-toolbar">
      <div class="reader-title" :title="model.title">{{ model.title }}</div>
      <div class="reader-tools">
        <template v-if="model.engine === 'pdfjs' && pdfDoc">
          <el-radio-group v-model="readingMode" size="small" aria-label="阅读模式" @change="changeReadingMode">
            <el-radio-button value="paged">分页阅读</el-radio-button>
            <el-radio-button value="continuous">长文阅读</el-radio-button>
          </el-radio-group>
          <span class="reader-page">{{ readingMode === 'continuous' ? '当前 ' : '' }}{{ pageNum }} / {{ numPages }}</span>
          <el-button-group>
            <el-button size="small" @click="zoomBy(-0.25)" :disabled="zoom <= 0.5">-</el-button>
            <el-button size="small" @click="fitWidth">适应宽度</el-button>
            <el-button size="small" @click="zoomBy(0.25)" :disabled="zoom >= 3">+</el-button>
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
            v-if="model.sourceFormat === 'pdf' && pdfDoc"
            class="reader-selection-hint"
            size="small"
            effect="plain"
            :type="selectableTextCount ? 'success' : 'warning'"
        >
          {{ selectionHint }}
        </el-tag>
      </div>
    </div>

    <!-- 渲染区：PDF.js 画布 / docx-preview 容器 -->
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
      <div v-show="model.engine === 'docx'" class="reader-docx" ref="docxRef" tabindex="0"></div>
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

    <Teleport to="body">
      <aside
          v-if="explain.visible"
          ref="explainRef"
          class="selection-explain"
          :style="{ left: `${explain.left}px`, top: `${explain.top}px` }"
          role="dialog"
          aria-label="选中文字解释"
          @pointerdown.stop
      >
        <header class="selection-explain-header">
          <div class="selection-explain-title">
            <span class="selection-explain-mark">AI</span>
            <span>选文解释</span>
          </div>
          <button type="button" class="selection-icon-button" aria-label="关闭解释" @click="closeExplanation(true)">
            <el-icon><Close /></el-icon>
          </button>
        </header>
        <div class="selection-quote" :title="explain.selection">“{{ explain.selection }}”</div>
        <div v-if="explain.loading" class="selection-explain-loading" role="status">
          <el-icon class="is-loading"><Loading /></el-icon>
          <span>正在理解所选内容…</span>
        </div>
        <div v-else-if="explain.error" class="selection-explain-error">
          <span>{{ explain.error }}</span>
          <button v-if="explain.needsConfig" type="button" @click="goToConfig">前往 API配置</button>
          <button v-else type="button" @click="requestExplanation">重新解释</button>
        </div>
        <div v-else class="selection-explain-answer">{{ explain.answer }}</div>
        <div v-if="explain.noteOpen && !explain.noteSaved" class="selection-note-compose">
          <label for="selection-note-remark">添加个人备注（可选）</label>
          <textarea
              id="selection-note-remark"
              v-model="explain.noteRemark"
              maxlength="5000"
              rows="3"
              placeholder="记录你的理解、疑问或下一步行动"
          ></textarea>
          <div>
            <span>{{ explain.noteRemark.length }} / 5000</span>
            <button type="button" @click="explain.noteOpen = false">取消</button>
            <button type="button" class="primary" :disabled="explain.noteSaving" @click="saveExplanationNote">
              {{ explain.noteSaving ? '保存中…' : '保存笔记' }}
            </button>
          </div>
        </div>
        <footer v-if="!explain.loading && explain.answer" class="selection-explain-footer">
          <span class="selection-model">{{ explain.model }}</span>
          <div class="selection-footer-actions">
            <button type="button" @click="copyExplanation">
              <el-icon><CopyDocument /></el-icon>{{ explain.copied ? '已复制' : '复制' }}
            </button>
            <button v-if="explain.noteSaved" type="button" class="note-saved" @click="goToNotes">
              <el-icon><Notebook /></el-icon>已加入 · 查看
            </button>
            <template v-else>
              <button type="button" :disabled="explain.noteSaving" @click="saveExplanationNote">
                <el-icon><Notebook /></el-icon>{{ explain.noteSaving ? '添加中…' : '一键添加' }}
              </button>
              <button type="button" :disabled="explain.noteSaving" @click="explain.noteOpen = !explain.noteOpen">
                {{ explain.noteOpen ? '收起备注' : '备注后添加' }}
              </button>
            </template>
          </div>
        </footer>
      </aside>
    </Teleport>
  </div>
</template>

<script setup>
import { computed, nextTick, onBeforeUnmount, onMounted, reactive, ref, shallowRef, watch } from 'vue'
import { useRouter } from 'vue-router'
import * as pdfjsLib from 'pdfjs-dist'
import PdfjsWorker from 'pdfjs-dist/build/pdf.worker.min.mjs?worker'
import { renderAsync } from 'docx-preview'
import { ArrowLeft, ArrowRight, Close, CopyDocument, Loading, Notebook, Refresh, WarningFilled } from '@element-plus/icons-vue'
import { ElMessage } from 'element-plus'
import { fetchBytes } from '@/utils/preview'
import request from '@/utils/request'

pdfjsLib.GlobalWorkerOptions.workerPort = new PdfjsWorker()

const READING_MODE_KEY = 'iknowread:pdf-reading-mode'
const props = defineProps({ model: { type: Object, required: true } })
const router = useRouter()
const loading = ref(false)
const loadingText = ref('加载中...')
const error = ref('')
const activeUrl = ref(props.model.url)
const ocrStatus = ref(props.model.ocrStatus || 'not_applicable')
const ocrError = ref(props.model.ocrError || '')
const ocrRetrying = ref(false)
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
const explainRef = ref()
const explain = reactive({
  visible: false,
  selection: '',
  answer: '',
  model: '',
  modelName: '',
  provider: '',
  providerName: '',
  configName: '',
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

let renderTask = null
let textLayer = null
let continuousObserver = null
let continuousEntries = []
let continuousBuildVersion = 0
let loadingTask = null
let abortController = null
let explainController = null
let loadVersion = 0
let resizeObserver = null
let resizeTimer = null
let ocrTimer = null
const explanationCache = new Map()

const hardenDocxDom = (container) => {
  if (!container) return
  container.querySelectorAll('script, iframe, object, embed, form, base').forEach(node => node.remove())
  container.querySelectorAll('a[href]').forEach(link => {
    const raw = link.getAttribute('href') || ''
    if (raw.startsWith('#')) return
    try {
      const parsed = new URL(raw, window.location.origin)
      if (!['http:', 'https:', 'mailto:'].includes(parsed.protocol)) {
        link.removeAttribute('href')
        return
      }
      link.target = '_blank'
      link.rel = 'noopener noreferrer nofollow'
    } catch (_) {
      link.removeAttribute('href')
    }
  })
}

const ocrBusy = computed(() => ['pending', 'processing'].includes(ocrStatus.value))
const ocrDisabled = computed(() => ocrError.value === 'OCR 服务未启用')
const selectionHint = computed(() => {
  if (selectableTextCount.value) return '拖动选择文字 · AI解释'
  if (ocrBusy.value) return '扫描文字识别完成后将自动刷新'
  if (ocrStatus.value === 'failed') return readingMode.value === 'continuous' ? '当前文档没有可选择文字' : '当前页没有可选择文字'
  if (readingMode.value === 'continuous' && continuousRenderedCount.value < numPages.value) return '滚动加载页面文字层 · 可选择文字'
  return readingMode.value === 'continuous' ? '当前文档没有可选择文字' : '此页没有可选择文字'
})

const versionedUrl = (url, revision) => {
  if (!revision) return url
  const separator = url.includes('?') ? '&' : '?'
  return `${url}${separator}ocr=${encodeURIComponent(revision)}`
}

const clearOcrTimer = () => {
  clearTimeout(ocrTimer)
  ocrTimer = null
}

const scheduleOcrPoll = () => {
  clearOcrTimer()
  if (ocrBusy.value) ocrTimer = setTimeout(refreshOcrStatus, 2500)
}

const refreshOcrStatus = async () => {
  try {
    const response = await request.get(`/document/${props.model.id}/ocr-status`)
    const doc = response.data || {}
    const previous = ocrStatus.value
    ocrStatus.value = doc.ocr_status || previous
    ocrError.value = doc.ocr_error || ''
    if (ocrStatus.value === 'ready' && previous !== 'ready') {
      activeUrl.value = versionedUrl(props.model.url, doc.ocr_updated_at || Date.now())
      await load()
      ElMessage.success('扫描文字识别完成，现在可以选取内容')
    }
  } catch (_) {
    // 请求层已给出必要提示；下一次由用户重试，避免网络异常时持续弹窗。
    clearOcrTimer()
    return
  }
  scheduleOcrPoll()
}

const retryOcr = async () => {
  ocrRetrying.value = true
  try {
    const response = await request.post(`/document/${props.model.id}/ocr`)
    ocrStatus.value = response.data?.ocr_status || 'pending'
    ocrError.value = ''
    scheduleOcrPoll()
  } finally {
    ocrRetrying.value = false
  }
}

const normalizeSelection = value => value
  .replace(/\u00a0/g, ' ')
  .replace(/\s+/g, ' ')
  .replace(/([\u3400-\u9fff])\s+(?=[\u3400-\u9fff])/g, '$1')
  .trim()

const isRenderCancellation = exception => ['RenderingCancelledException', 'AbortException'].includes(exception?.name)

const selectionBelongsToReader = range => {
  const node = range.commonAncestorContainer
  return !!bodyRef.value && (node === bodyRef.value || bodyRef.value.contains(node))
}

const positionExplanation = async () => {
  const rect = explain.anchorRect
  if (!rect) return
  await nextTick()
  const width = Math.min(explainRef.value?.offsetWidth || 380, window.innerWidth - 24)
  const height = Math.min(explainRef.value?.offsetHeight || 260, window.innerHeight - 24)
  explain.left = Math.max(12, Math.min(window.innerWidth - width - 12, rect.left + rect.width / 2 - width / 2))
  const below = rect.bottom + 12
  explain.top = below + height <= window.innerHeight - 12
    ? below
    : Math.max(12, rect.top - height - 12)
}

const closeExplanation = (clearSelection = false) => {
  explainController?.abort()
  explainController = null
  explain.visible = false
  explain.loading = false
  if (clearSelection) window.getSelection()?.removeAllRanges()
}

const requestExplanation = async () => {
  const content = explain.selection
  if (!content || !explain.visible) return
  const cacheKey = `${props.model.id}:${content}`
  const cached = explanationCache.get(cacheKey)
  if (cached) {
    Object.assign(explain, {
      ...cached, loading: false, error: '', needsConfig: false, copied: false,
      noteOpen: false, noteRemark: '', noteSaving: false, noteSaved: false, noteId: null,
    })
    positionExplanation()
    return
  }
  explainController?.abort()
  explainController = new AbortController()
  Object.assign(explain, {
    loading: true, answer: '', model: '', modelName: '', provider: '', providerName: '', configName: '',
    error: '', needsConfig: false, copied: false,
    noteOpen: false, noteRemark: '', noteSaving: false, noteSaved: false, noteId: null,
  })
  positionExplanation()
  try {
    const response = await request.post('/ai/explain', {
      content,
      document_title: props.model.title || '',
    }, { signal: explainController.signal, timeout: 135000 })
    if (!explain.visible || explain.selection !== content) return
    // 展示口径统一为「服务商 · 模型」，不显示配置名称
    const label = [response.data.provider_name || response.data.provider, response.data.model]
        .filter(Boolean).join(' · ')
    const value = {
      answer: response.data.content,
      model: label,
      modelName: response.data.model || '',
      provider: response.data.provider || '',
      providerName: response.data.provider_name || '',
      configName: response.data.config_name || '',
    }
    if (explanationCache.size >= 50) explanationCache.delete(explanationCache.keys().next().value)
    explanationCache.set(cacheKey, value)
    Object.assign(explain, { ...value, loading: false })
  } catch (exception) {
    if (exception.code === 'ERR_CANCELED' || !explain.visible || explain.selection !== content) return
    const message = exception.response?.data?.msg || '解释失败，请稍后重试'
    Object.assign(explain, {
      loading: false,
      error: message,
      needsConfig: message.includes('API配置') || message.includes('先在'),
    })
  } finally {
    positionExplanation()
  }
}

const captureSelection = () => {
  // 等待浏览器完成本次选区更新；触摸设备也可复用同一逻辑。
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
    if (explain.visible && explain.selection === content) return
    explainController?.abort()
    Object.assign(explain, {
      visible: true,
      selection: content,
      answer: '',
      model: '',
      modelName: '',
      provider: '',
      providerName: '',
      configName: '',
      error: '',
      needsConfig: false,
      loading: true,
      copied: false,
      noteOpen: false,
      noteRemark: '',
      noteSaving: false,
      noteSaved: false,
      noteId: null,
      anchorRect: range.getBoundingClientRect(),
    })
    positionExplanation()
    requestExplanation()
  }, 0)
}

const copyExplanation = async () => {
  try {
    await navigator.clipboard.writeText(explain.answer)
    explain.copied = true
    window.setTimeout(() => { explain.copied = false }, 1500)
  } catch (_) {
    ElMessage.error('复制失败，请手动复制')
  }
}

const saveExplanationNote = async () => {
  if (!explain.answer || explain.noteSaving || explain.noteSaved) return
  const documentId = Number(props.model.id)
  if (!Number.isInteger(documentId) || documentId < 1) {
    ElMessage.error('当前文档信息无效，无法添加笔记')
    return
  }
  explain.noteSaving = true
  try {
    const response = await request.post('/notes', {
      source_type: 'ai_explanation',
      document_id: documentId,
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
  } finally {
    explain.noteSaving = false
    positionExplanation()
  }
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
  if (explain.visible && !explainRef.value?.contains(event.target)) closeExplanation(false)
}

const handleBodyScroll = () => {
  closeExplanation(true)
  updateContinuousPageNumber()
}

const cancelRender = async () => {
  textLayer?.cancel()
  textLayer = null
  if (!renderTask) return
  const task = renderTask
  renderTask = null
  task.cancel()
  try { await task.promise } catch (exception) {
    if (!isRenderCancellation(exception)) throw exception
  }
}

const cancelContinuousRender = async () => {
  continuousBuildVersion += 1
  continuousObserver?.disconnect()
  continuousObserver = null
  const pending = []
  for (const entry of continuousEntries) {
    entry.textLayer?.cancel()
    if (entry.renderTask) {
      try { entry.renderTask.cancel() } catch (_) {}
    }
    if (entry.renderPromise) pending.push(entry.renderPromise)
  }
  continuousEntries = []
  continuousRenderedCount.value = 0
  continuousRef.value?.replaceChildren()
  if (pending.length) await Promise.allSettled(pending)
}

const updateContinuousPageNumber = () => {
  if (readingMode.value !== 'continuous' || !bodyRef.value || !continuousEntries.length) return
  const target = bodyRef.value.scrollTop + bodyRef.value.clientHeight * 0.28
  let low = 0
  let high = continuousEntries.length - 1
  while (low < high) {
    const middle = Math.ceil((low + high) / 2)
    if (continuousEntries[middle].slot.offsetTop <= target) low = middle
    else high = middle - 1
  }
  pageNum.value = continuousEntries[low].pageNumber
}

const renderContinuousPage = (entry, version) => {
  if (!entry || entry.rendered || entry.rendering || version !== continuousBuildVersion || !pdfDoc.value) return
  entry.rendering = true
  entry.status.textContent = `正在加载第 ${entry.pageNumber} 页…`
  const promise = (async () => {
    const viewport = entry.page.getViewport({ scale: zoom.value })
    const dpr = window.devicePixelRatio || 1
    entry.canvas.width = Math.ceil(viewport.width * dpr)
    entry.canvas.height = Math.ceil(viewport.height * dpr)
    entry.canvas.style.width = `${viewport.width}px`
    entry.canvas.style.height = `${viewport.height}px`
    entry.surface.style.width = `${viewport.width}px`
    entry.surface.style.height = `${viewport.height}px`
    entry.slot.style.minHeight = `${viewport.height}px`
    const params = { canvasContext: entry.canvas.getContext('2d'), viewport }
    if (dpr !== 1) params.transform = [dpr, 0, 0, dpr, 0, 0]
    const task = entry.page.render(params)
    entry.renderTask = task
    const currentTextLayer = new pdfjsLib.TextLayer({
      textContentSource: entry.page.streamTextContent({ includeMarkedContent: true, disableNormalization: true }),
      container: entry.textContainer,
      viewport,
    })
    entry.textLayer = currentTextLayer
    await Promise.all([task.promise, currentTextLayer.render()])
    if (version !== continuousBuildVersion) return
    entry.rendered = true
    entry.status.textContent = ''
    continuousRenderedCount.value += 1
    const textCount = currentTextLayer.textContentItemsStr.join('').trim().length
    entry.textCount = textCount
    selectableTextCount.value += textCount
  })().catch(exception => {
    if (version === continuousBuildVersion && !isRenderCancellation(exception)) {
      entry.status.textContent = `第 ${entry.pageNumber} 页加载失败，滚动后将重试`
      entry.status.classList.add('error')
    }
  }).finally(() => {
    entry.rendering = false
    entry.renderTask = null
    entry.textLayer = null
    entry.renderPromise = null
  })
  entry.renderPromise = promise
  return promise
}

const prepareContinuousPages = async () => {
  const documentProxy = pdfDoc.value
  if (!documentProxy || !continuousRef.value) return
  const targetPage = Math.min(Math.max(pageNum.value, 1), documentProxy.numPages)
  closeExplanation(true)
  await cancelContinuousRender()
  if (documentProxy !== pdfDoc.value) return
  selectableTextCount.value = 0
  const version = ++continuousBuildVersion
  const fragment = document.createDocumentFragment()
  const entries = []
  for (let number = 1; number <= documentProxy.numPages; number += 1) {
    const page = await documentProxy.getPage(number)
    if (version !== continuousBuildVersion || documentProxy !== pdfDoc.value) return
    const viewport = page.getViewport({ scale: zoom.value })
    const slot = document.createElement('section')
    slot.className = 'continuous-page'
    slot.dataset.pageNumber = String(number)
    slot.style.minHeight = `${viewport.height}px`
    const badge = document.createElement('span')
    badge.className = 'continuous-page-number'
    badge.textContent = `${number} / ${documentProxy.numPages}`
    const surface = document.createElement('div')
    surface.className = 'reader-page-surface'
    surface.style.width = `${viewport.width}px`
    surface.style.height = `${viewport.height}px`
    const canvas = document.createElement('canvas')
    const textContainer = document.createElement('div')
    textContainer.className = 'textLayer'
    textContainer.tabIndex = 0
    textContainer.setAttribute('aria-label', `PDF 第 ${number} 页可选择文字层`)
    const status = document.createElement('div')
    status.className = 'continuous-page-status'
    status.textContent = `等待加载第 ${number} 页…`
    surface.append(canvas, textContainer, status)
    slot.append(badge, surface)
    fragment.append(slot)
    entries.push({ pageNumber: number, page, slot, surface, canvas, textContainer, status, rendered: false, rendering: false, renderTask: null, textLayer: null, renderPromise: null, textCount: 0 })
    if (number % 25 === 0) await new Promise(resolve => requestAnimationFrame(resolve))
  }
  if (version !== continuousBuildVersion || documentProxy !== pdfDoc.value) return
  continuousEntries = entries
  continuousRef.value.replaceChildren(fragment)
  continuousObserver = new IntersectionObserver(changes => {
    for (const change of changes) {
      if (change.isIntersecting) renderContinuousPage(continuousEntries[Number(change.target.dataset.pageNumber) - 1], version)
    }
  }, { root: bodyRef.value, rootMargin: '900px 0px', threshold: 0.01 })
  for (const entry of continuousEntries) continuousObserver.observe(entry.slot)
  const targetEntry = continuousEntries[targetPage - 1]
  if (targetEntry && bodyRef.value) bodyRef.value.scrollTop = Math.max(0, targetEntry.slot.offsetTop - 16)
  renderContinuousPage(targetEntry, version)
  renderContinuousPage(continuousEntries[targetPage], version)
  if (targetEntry?.renderPromise) await targetEntry.renderPromise
  updateContinuousPageNumber()
}

const destroyPdf = async () => {
  try { await cancelRender() } catch (_) {}
  await cancelContinuousRender()
  const task = loadingTask
  loadingTask = null
  const document = pdfDoc.value
  pdfDoc.value = null
  if (task) {
    try { await task.destroy() } catch (_) {}
  } else if (document) {
    try { await document.destroy() } catch (_) {}
  }
  numPages.value = 0
  selectableTextCount.value = 0
}

const renderPage = async () => {
  if (!pdfDoc.value || !canvasRef.value) return
  closeExplanation(true)
  selectableTextCount.value = 0
  await cancelRender()
  const page = await pdfDoc.value.getPage(pageNum.value)
  const viewport = page.getViewport({ scale: zoom.value })
  const canvas = canvasRef.value
  const dpr = window.devicePixelRatio || 1
  canvas.width = Math.ceil(viewport.width * dpr)
  canvas.height = Math.ceil(viewport.height * dpr)
  canvas.style.width = `${viewport.width}px`
  canvas.style.height = `${viewport.height}px`
  const surface = pageSurfaceRef.value
  surface.style.width = `${viewport.width}px`
  surface.style.height = `${viewport.height}px`
  const layerContainer = textLayerRef.value
  layerContainer.replaceChildren()
  const params = { canvasContext: canvas.getContext('2d'), viewport }
  if (dpr !== 1) params.transform = [dpr, 0, 0, dpr, 0, 0]
  const task = page.render(params)
  renderTask = task
  const currentTextLayer = new pdfjsLib.TextLayer({
    textContentSource: page.streamTextContent({ includeMarkedContent: true, disableNormalization: true }),
    container: layerContainer,
    viewport,
  })
  textLayer = currentTextLayer
  try {
    await Promise.all([task.promise, currentTextLayer.render()])
    selectableTextCount.value = currentTextLayer.textContentItemsStr.join('').trim().length
  } catch (exception) {
    if (!isRenderCancellation(exception)) throw exception
  } finally {
    if (renderTask === task) renderTask = null
    if (textLayer === currentTextLayer) textLayer = null
  }
}

const renderCurrentMode = async () => {
  if (readingMode.value === 'continuous') await prepareContinuousPages()
  else await renderPage()
}

const fitToWidth = async () => {
  if (!pdfDoc.value || !bodyRef.value) return
  const page = await pdfDoc.value.getPage(readingMode.value === 'continuous' ? 1 : pageNum.value)
  const base = page.getViewport({ scale: 1 })
  // 两种模式使用同一内容宽度，切换时不改变缩放比例或造成画布横向跳动。
  const horizontalSpace = 48
  zoom.value = Math.max(0.5, Math.min(3, +((bodyRef.value.clientWidth - horizontalSpace) / base.width).toFixed(2)))
  await renderCurrentMode()
}

const showRenderError = (exception) => {
  if (!isRenderCancellation(exception)) {
    error.value = exception?.message || '页面渲染失败'
  }
}

const goPage = async (value) => {
  if (readingMode.value !== 'paged' || value < 1 || value > numPages.value) return
  pageNum.value = value
  try { await renderPage() } catch (exception) { showRenderError(exception) }
}

const zoomBy = async (delta) => {
  zoom.value = Math.min(3, Math.max(0.5, +(zoom.value + delta).toFixed(2)))
  try { await renderCurrentMode() } catch (exception) { showRenderError(exception) }
}

const fitWidth = async () => {
  try { await fitToWidth() } catch (exception) { showRenderError(exception) }
}

const changeReadingMode = async mode => {
  if (!pdfDoc.value) return
  localStorage.setItem(READING_MODE_KEY, mode)
  closeExplanation(true)
  loading.value = true
  loadingText.value = mode === 'continuous' ? '正在准备长文阅读…' : '正在准备分页阅读…'
  try {
    await nextTick()
    if (mode === 'paged') {
      await cancelContinuousRender()
      if (bodyRef.value) bodyRef.value.scrollTop = 0
    }
    // 阅读模式只改变页面组织方式，保留当前缩放比例可避免切换时画面二次缩放。
    await renderCurrentMode()
  } catch (exception) {
    showRenderError(exception)
  } finally {
    loading.value = false
  }
}

const load = async () => {
  closeExplanation(true)
  explanationCache.clear()
  const version = ++loadVersion
  abortController?.abort()
  abortController = new AbortController()
  const signal = abortController.signal
  error.value = ''
  loading.value = true
  loadingText.value = '加载中...'
  await destroyPdf()
  if (docxRef.value) docxRef.value.innerHTML = ''
  try {
    if (props.model.engine === 'docx') {
      const buffer = await fetchBytes(activeUrl.value, { signal })
      if (version !== loadVersion) return
      // DOCX altChunk can contain active HTML. Never grant uploaded documents
      // application-origin execution privileges.
      await renderAsync(buffer, docxRef.value, null, {
        inWrapper: true,
        renderAltChunks: false,
        renderComments: false,
      })
      hardenDocxDom(docxRef.value)
    } else {
      const task = pdfjsLib.getDocument({ url: activeUrl.value, withCredentials: true })
      loadingTask = task
      const document = await task.promise
      if (version !== loadVersion) {
        await document.destroy()
        return
      }
      loadingTask = null
      pdfDoc.value = document
      numPages.value = document.numPages
      pageNum.value = 1
      await nextTick()
      if (bodyRef.value) bodyRef.value.scrollTop = 0
      await fitToWidth()
    }
  } catch (exception) {
    if (version === loadVersion && exception?.name !== 'AbortError' && !isRenderCancellation(exception)) {
      error.value = exception?.message?.toLowerCase().includes('password')
        ? '文档已加密，无法预览'
        : (exception?.message || '预览失败')
    }
  } finally {
    if (version === loadVersion) loading.value = false
  }
}

watch(() => [props.model.id, props.model.url, props.model.engine], () => {
  ocrStatus.value = props.model.ocrStatus || 'not_applicable'
  ocrError.value = props.model.ocrError || ''
  activeUrl.value = ocrStatus.value === 'ready'
    ? versionedUrl(props.model.url, props.model.ocrUpdatedAt)
    : props.model.url
  scheduleOcrPoll()
  load()
}, { immediate: true })

onMounted(() => {
  bodyRef.value?.addEventListener('mouseup', captureSelection)
  bodyRef.value?.addEventListener('touchend', captureSelection)
  bodyRef.value?.addEventListener('keyup', captureSelection)
  bodyRef.value?.addEventListener('scroll', handleBodyScroll, { passive: true })
  document.addEventListener('pointerdown', handleDocumentPointerDown, true)
  window.addEventListener('resize', closeExplanation)
  resizeObserver = new ResizeObserver(() => {
    clearTimeout(resizeTimer)
    resizeTimer = setTimeout(() => {
      if (pdfDoc.value) fitWidth()
    }, 120)
  })
  if (bodyRef.value) resizeObserver.observe(bodyRef.value)
})

onBeforeUnmount(() => {
  loadVersion += 1
  abortController?.abort()
  clearTimeout(resizeTimer)
  clearOcrTimer()
  resizeObserver?.disconnect()
  bodyRef.value?.removeEventListener('mouseup', captureSelection)
  bodyRef.value?.removeEventListener('touchend', captureSelection)
  bodyRef.value?.removeEventListener('keyup', captureSelection)
  bodyRef.value?.removeEventListener('scroll', handleBodyScroll)
  explainController?.abort()
  document.removeEventListener('pointerdown', handleDocumentPointerDown, true)
  window.removeEventListener('resize', closeExplanation)
  destroyPdf()
})

defineExpose({ reload: load })
</script>

<style scoped>
.reader {
  position: relative;
  display: flex;
  flex-direction: column;
  height: 100%;
  min-height: 400px;
  background: #fff;
  border-radius: 14px;
  border: 1px solid rgba(0, 69, 183, .06);
  overflow: hidden;
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
  overflow: auto;
  scrollbar-gutter: stable;
  overscroll-behavior: contain; /* 触底/触顶不再把滚动传给外层页面 */
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
.reader-docx :deep(::selection) {
  background: rgba(48, 218, 212, .34);
}
.reader-continuous :deep(.textLayer ::selection) { background: rgba(48, 218, 212, .34); }
.reader-docx {
  background: #fff;
  max-width: 900px;
  margin: 16px auto;
  padding: 24px 32px;
  box-shadow: 0 4px 18px rgba(0, 56, 157, .18);
  border-radius: 2px;
}
.reader-docx:focus { outline: none; }
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

.selection-explain {
  position: fixed;
  z-index: 4000;
  width: min(380px, calc(100vw - 24px));
  max-height: min(560px, calc(100vh - 24px));
  display: flex;
  flex-direction: column;
  overflow: hidden;
  color: var(--ik-text);
  background: rgba(255, 255, 255, .98);
  border: 1px solid rgba(0, 150, 180, .24);
  border-radius: 14px;
  box-shadow: 0 16px 44px rgba(0, 56, 157, .2);
  backdrop-filter: blur(10px);
  animation: selection-explain-in .16s ease-out;
}
.selection-explain-header,
.selection-explain-footer {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
}
.selection-explain-header {
  padding: 12px 14px;
  border-bottom: 1px solid var(--ik-border);
  background: linear-gradient(135deg, #f3f9ff, #edfcfb);
}
.selection-explain-title {
  display: flex;
  align-items: center;
  gap: 8px;
  font-size: 14px;
  font-weight: 700;
  color: #24384c;
}
.selection-explain-mark {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 28px;
  height: 22px;
  color: #fff;
  font-size: 11px;
  letter-spacing: .3px;
  border-radius: 7px;
  background: var(--ik-gradient);
}
.selection-icon-button,
.selection-explain-footer button,
.selection-explain-error button {
  border: 0;
  background: transparent;
  color: var(--ik-blue);
  font: inherit;
  cursor: pointer;
}
.selection-icon-button {
  display: inline-flex;
  padding: 5px;
  border-radius: 7px;
  color: var(--ik-text-sub);
}
.selection-icon-button:hover { background: rgba(0, 69, 183, .08); }
.selection-quote {
  flex-shrink: 0;
  margin: 12px 14px 0;
  padding: 9px 11px;
  color: var(--ik-text-sub);
  font-size: 12px;
  line-height: 1.55;
  background: #f5f9fc;
  border-left: 3px solid var(--ik-cyan);
  border-radius: 4px 8px 8px 4px;
  overflow: hidden;
  white-space: nowrap;
  text-overflow: ellipsis;
}
.selection-explain-loading,
.selection-explain-error,
.selection-explain-answer {
  min-height: 80px;
  padding: 14px;
  font-size: 14px;
  line-height: 1.75;
}
.selection-explain-loading {
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 9px;
  color: var(--ik-cyan-deep);
}
.selection-explain-error {
  display: flex;
  flex-direction: column;
  align-items: flex-start;
  gap: 8px;
  color: var(--el-color-danger);
}
.selection-explain-error button { padding: 0; font-size: 13px; }
.selection-explain-answer {
  overflow-y: auto;
  white-space: pre-wrap;
  overflow-wrap: anywhere;
}
.selection-explain-footer {
  flex-shrink: 0;
  padding: 9px 14px;
  color: var(--ik-text-sub);
  font-size: 11px;
  border-top: 1px solid var(--ik-border);
}
.selection-model {
  min-width: 0;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.selection-footer-actions {
  flex-shrink: 0;
  display: flex;
  align-items: center;
  gap: 10px;
}
.selection-explain-footer button {
  display: inline-flex;
  align-items: center;
  gap: 5px;
  padding: 4px 0;
  font-size: 12px;
}
.selection-explain-footer button:disabled {
  opacity: .55;
  cursor: wait;
}
.selection-explain-footer .note-saved { color: #148064; }
.selection-note-compose {
  flex-shrink: 0;
  padding: 12px 14px;
  background: #f7fbfd;
  border-top: 1px solid var(--ik-border);
}
.selection-note-compose label {
  display: block;
  margin-bottom: 7px;
  color: #33475e;
  font-size: 12px;
  font-weight: 600;
}
.selection-note-compose textarea {
  width: 100%;
  resize: vertical;
  min-height: 70px;
  max-height: 140px;
  padding: 9px 10px;
  color: var(--ik-text);
  font: inherit;
  font-size: 13px;
  line-height: 1.55;
  background: #fff;
  border: 1px solid #cfe2ee;
  border-radius: 8px;
  outline: none;
}
.selection-note-compose textarea:focus { border-color: var(--ik-cyan-deep); box-shadow: 0 0 0 2px rgba(0, 150, 180, .1); }
.selection-note-compose > div {
  display: flex;
  align-items: center;
  justify-content: flex-end;
  gap: 10px;
  margin-top: 7px;
}
.selection-note-compose > div span { margin-right: auto; color: var(--ik-text-sub); font-size: 10px; }
.selection-note-compose button {
  padding: 4px 0;
  color: var(--ik-blue);
  font: inherit;
  font-size: 12px;
  background: transparent;
  border: 0;
  cursor: pointer;
}
.selection-note-compose button.primary {
  padding: 6px 10px;
  color: #fff;
  background: var(--ik-gradient);
  border-radius: 7px;
}
.selection-note-compose button:disabled { opacity: .6; cursor: wait; }
@media (max-width: 520px) {
  .selection-explain-footer { align-items: flex-start; flex-direction: column; gap: 7px; }
  .selection-footer-actions { width: 100%; justify-content: space-between; }
}
@keyframes selection-explain-in {
  from { opacity: 0; transform: translateY(5px) scale(.98); }
  to { opacity: 1; transform: translateY(0) scale(1); }
}
</style>
