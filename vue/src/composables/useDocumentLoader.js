import { nextTick } from 'vue'
import { fetchBytes, fetchText } from '@/utils/preview'
import { loadDocxRenderer, loadPdfEngine } from '../utils/documentEngines.js'

const hardenDocxDom = container => {
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

export const useDocumentLoader = ({
  getModel,
  getActiveUrl,
  getContentVersion,
  getLongformElement,
  docxRef,
  markdownRef,
  bodyRef,
  pageNum,
  loading,
  loadingText,
  error,
  pdfDoc,
  numPages,
  onReset,
  getRestoration,
  destroyPdf,
  setPdfLoadingTask,
  clearPdfLoadingTask,
  fitToWidth,
  loadHighlights,
  restoreSourcePosition,
  isRenderCancellation,
}) => {
  let abortController = null
  let loadVersion = 0

  const load = async () => {
    onReset()
    const version = ++loadVersion
    abortController?.abort()
    abortController = new AbortController()
    const signal = abortController.signal
    error.value = ''
    loading.value = true
    loadingText.value = '加载中...'
    await destroyPdf()
    if (docxRef.value) docxRef.value.innerHTML = ''
    if (markdownRef.value) markdownRef.value.innerHTML = ''
    try {
      const restoration = await getRestoration()
      const model = getModel()
      if (model.engine === 'docx' || model.engine === 'markdown') {
        const staging = document.createElement('div')
        if (model.engine === 'docx') {
          const buffer = await fetchBytes(getActiveUrl(), { signal })
          if (version !== loadVersion) return
          const renderAsync = await loadDocxRenderer()
          if (version !== loadVersion) return
          await renderAsync(buffer, staging, null, {
            inWrapper: true,
            renderAltChunks: false,
            renderComments: false,
          })
          hardenDocxDom(staging)
        } else {
          const source = await fetchText(getActiveUrl(), { signal })
          if (version !== loadVersion) return
          const { blockRemoteMarkdownImages, renderMarkdown } = await import('@/utils/markdown')
          if (version !== loadVersion) return
          staging.innerHTML = renderMarkdown(source)
          if (model.sourceType === 'url') blockRemoteMarkdownImages(staging)
        }
        if (version !== loadVersion) return
        const container = getLongformElement()
        if (!container) return
        container.replaceChildren(...staging.childNodes)
        await nextTick()
        if (version !== loadVersion) return
        await loadHighlights()
        if (version !== loadVersion) return
        await restoreSourcePosition(restoration)
      } else {
        const pdfjsLib = await loadPdfEngine()
        if (version !== loadVersion) return
        const task = pdfjsLib.getDocument({ url: getActiveUrl(), withCredentials: true })
        setPdfLoadingTask(task)
        const documentProxy = await task.promise
        clearPdfLoadingTask(task)
        if (version !== loadVersion) {
          await documentProxy.destroy()
          return
        }
        pdfDoc.value = documentProxy
        numPages.value = documentProxy.numPages
        const restoreAnchor = restoration?.anchor
        const canPreselectPage = restoreAnchor
          && Number(restoreAnchor.document_id) === Number(model.id)
          && restoreAnchor.document_version === getContentVersion()
          && restoreAnchor.source_format === 'pdf'
        pageNum.value = canPreselectPage
          ? Math.min(Math.max(restoreAnchor.page, 1), documentProxy.numPages)
          : 1
        await nextTick()
        if (version !== loadVersion) return
        if (bodyRef.value) bodyRef.value.scrollTop = 0
        await fitToWidth()
        if (version !== loadVersion) return
        await loadHighlights()
        if (version !== loadVersion) return
        await restoreSourcePosition(restoration)
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

  const stop = () => {
    loadVersion += 1
    abortController?.abort()
  }

  return { load, stop }
}
