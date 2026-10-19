import { nextTick } from 'vue'
import * as pdfjsLib from 'pdfjs-dist'

export const isPdfRenderCancellation = exception => (
  ['RenderingCancelledException', 'AbortException'].includes(exception?.name)
)

export const usePdfRenderer = ({
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
  onBeforeRender,
  onTextRendered,
  onProgress,
  onError,
  readingModeStorageKey,
  createTextLayer = options => new pdfjsLib.TextLayer(options),
}) => {
  let renderTask = null
  let textLayer = null
  let pageRenderVersion = 0
  let continuousObserver = null
  let continuousEntries = []
  let continuousBuildVersion = 0
  let loadingTask = null

  const setLoadingTask = task => { loadingTask = task }
  const clearLoadingTask = task => {
    if (!task || loadingTask === task) loadingTask = null
  }

  const cancelPageRender = async (invalidate = true) => {
    if (invalidate) pageRenderVersion += 1
    textLayer?.cancel()
    textLayer = null
    if (!renderTask) return
    const task = renderTask
    renderTask = null
    task.cancel()
    try { await task.promise } catch (exception) {
      if (!isPdfRenderCancellation(exception)) throw exception
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
      const documentProxy = pdfDoc.value
      const page = entry.page || await documentProxy.getPage(entry.pageNumber)
      if (version !== continuousBuildVersion || documentProxy !== pdfDoc.value) return
      entry.page = page
      const viewport = page.getViewport({ scale: zoom.value })
      if (!entry.canvas) {
        entry.canvas = document.createElement('canvas')
        entry.textContainer = document.createElement('div')
        entry.textContainer.className = 'textLayer'
        entry.textContainer.tabIndex = 0
        entry.textContainer.setAttribute('aria-label', `PDF 第 ${entry.pageNumber} 页可选择文字层`)
        entry.surface.prepend(entry.canvas, entry.textContainer)
      }
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
      const task = page.render(params)
      entry.renderTask = task
      const currentTextLayer = createTextLayer({
        textContentSource: page.streamTextContent({ includeMarkedContent: true, disableNormalization: true }),
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
      onTextRendered?.()
    })().catch(exception => {
      if (version === continuousBuildVersion && !isPdfRenderCancellation(exception)) {
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
    onBeforeRender?.()
    await cancelPageRender()
    await cancelContinuousRender()
    if (documentProxy !== pdfDoc.value) return
    selectableTextCount.value = 0
    const version = ++continuousBuildVersion
    const firstPage = await documentProxy.getPage(1)
    if (version !== continuousBuildVersion || documentProxy !== pdfDoc.value) return
    const estimatedViewport = firstPage.getViewport({ scale: zoom.value })
    const fragment = document.createDocumentFragment()
    const entries = []
    for (let number = 1; number <= documentProxy.numPages; number += 1) {
      const slot = document.createElement('section')
      slot.className = 'continuous-page'
      slot.dataset.pageNumber = String(number)
      slot.style.minHeight = `${estimatedViewport.height}px`
      const badge = document.createElement('span')
      badge.className = 'continuous-page-number'
      badge.textContent = `${number} / ${documentProxy.numPages}`
      const surface = document.createElement('div')
      surface.className = 'reader-page-surface'
      surface.style.width = `${estimatedViewport.width}px`
      surface.style.height = `${estimatedViewport.height}px`
      const status = document.createElement('div')
      status.className = 'continuous-page-status'
      status.textContent = `等待加载第 ${number} 页…`
      surface.append(status)
      slot.append(badge, surface)
      fragment.append(slot)
      entries.push({
        pageNumber: number, page: number === 1 ? firstPage : null, slot, surface,
        canvas: null, textContainer: null, status, rendered: false, rendering: false,
        renderTask: null, textLayer: null, renderPromise: null, textCount: 0,
      })
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

  const renderPage = async () => {
    const documentProxy = pdfDoc.value
    const canvas = canvasRef.value
    const surface = pageSurfaceRef.value
    const layerContainer = textLayerRef.value
    if (!documentProxy || !canvas || !surface || !layerContainer) return
    const targetPage = pageNum.value
    const targetZoom = zoom.value
    const version = ++pageRenderVersion
    onBeforeRender?.()
    selectableTextCount.value = 0
    await cancelPageRender(false)
    if (version !== pageRenderVersion || documentProxy !== pdfDoc.value) return
    const page = await documentProxy.getPage(targetPage)
    if (version !== pageRenderVersion || documentProxy !== pdfDoc.value) return
    const viewport = page.getViewport({ scale: targetZoom })
    const dpr = window.devicePixelRatio || 1
    canvas.width = Math.ceil(viewport.width * dpr)
    canvas.height = Math.ceil(viewport.height * dpr)
    canvas.style.width = `${viewport.width}px`
    canvas.style.height = `${viewport.height}px`
    surface.style.width = `${viewport.width}px`
    surface.style.height = `${viewport.height}px`
    layerContainer.replaceChildren()
    const params = { canvasContext: canvas.getContext('2d'), viewport }
    if (dpr !== 1) params.transform = [dpr, 0, 0, dpr, 0, 0]
    const task = page.render(params)
    renderTask = task
    const currentTextLayer = createTextLayer({
      textContentSource: page.streamTextContent({ includeMarkedContent: true, disableNormalization: true }),
      container: layerContainer,
      viewport,
    })
    textLayer = currentTextLayer
    try {
      await Promise.all([task.promise, currentTextLayer.render()])
      if (version !== pageRenderVersion || documentProxy !== pdfDoc.value) return
      selectableTextCount.value = currentTextLayer.textContentItemsStr.join('').trim().length
      onTextRendered?.()
    } catch (exception) {
      if (!isPdfRenderCancellation(exception)) throw exception
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
    zoom.value = Math.max(0.5, Math.min(3, +((bodyRef.value.clientWidth - 48) / base.width).toFixed(2)))
    await renderCurrentMode()
  }

  const handleError = exception => {
    if (!isPdfRenderCancellation(exception)) onError?.(exception)
  }

  const goPage = async value => {
    if (readingMode.value !== 'paged' || value < 1 || value > numPages.value) return
    pageNum.value = value
    try { await renderPage(); onProgress?.() } catch (exception) { handleError(exception) }
  }

  const zoomBy = async delta => {
    zoom.value = Math.min(3, Math.max(0.5, +(zoom.value + delta).toFixed(2)))
    try { await renderCurrentMode() } catch (exception) { handleError(exception) }
  }

  const fitWidth = async () => {
    try { await fitToWidth() } catch (exception) { handleError(exception) }
  }

  const changeReadingMode = async mode => {
    if (!pdfDoc.value) return
    localStorage.setItem(readingModeStorageKey, mode)
    loading.value = true
    loadingText.value = mode === 'continuous' ? '正在准备长文阅读…' : '正在准备分页阅读…'
    try {
      await nextTick()
      if (mode === 'paged') {
        await cancelContinuousRender()
        if (bodyRef.value) bodyRef.value.scrollTop = 0
      }
      await renderCurrentMode()
      onProgress?.()
    } catch (exception) {
      handleError(exception)
    } finally {
      loading.value = false
    }
  }

  const renderedTextLayer = page => {
    if (readingMode.value === 'paged') return Number(page) === pageNum.value ? textLayerRef.value : null
    const entry = continuousEntries[Number(page) - 1]
    return entry?.rendered ? entry.textContainer : null
  }

  const ensureTextLayer = async page => {
    const targetPage = Math.min(Math.max(page, 1), numPages.value || page)
    const pageChanged = pageNum.value !== targetPage
    pageNum.value = targetPage
    if (readingMode.value === 'paged') {
      if (pageChanged || !textLayerRef.value?.childNodes.length) await renderPage()
      return { element: textLayerRef.value, offsetTop: null }
    }
    if (!continuousEntries.length) await prepareContinuousPages()
    const entry = continuousEntries[targetPage - 1]
    if (!entry) return null
    renderContinuousPage(entry, continuousBuildVersion)
    if (entry.renderPromise) await entry.renderPromise
    return { element: entry.textContainer, offsetTop: entry.slot.offsetTop }
  }

  const destroy = async () => {
    try { await cancelPageRender() } catch (_) {}
    await cancelContinuousRender()
    const task = loadingTask
    loadingTask = null
    const documentProxy = pdfDoc.value
    pdfDoc.value = null
    if (task) {
      try { await task.destroy() } catch (_) {}
    } else if (documentProxy) {
      try { await documentProxy.destroy() } catch (_) {}
    }
    numPages.value = 0
    selectableTextCount.value = 0
  }

  return {
    setLoadingTask,
    clearLoadingTask,
    updateContinuousPageNumber,
    renderPage,
    renderCurrentMode,
    fitToWidth,
    fitWidth,
    goPage,
    zoomBy,
    changeReadingMode,
    renderedTextLayer,
    ensureTextLayer,
    destroy,
  }
}
