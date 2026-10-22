import { reactive } from 'vue'
import { ElMessage } from 'element-plus'
import { createTextAnchor } from '../utils/sourceAnchor.js'

export const collectDocumentMatches = (text, query, sourceModel, { page = null, progression = 0, limit = 100 } = {}) => {
  const results = []
  const haystack = text.toLocaleLowerCase()
  const needle = query.toLocaleLowerCase()
  let from = 0
  while (from <= text.length && results.length < limit) {
    const index = haystack.indexOf(needle, from)
    if (index < 0) break
    const exact = text.slice(index, index + query.length)
    const anchor = createTextAnchor(sourceModel, {
      page, progression, start: index, end: index + exact.length, exact,
      prefix: text.slice(Math.max(0, index - 80), index),
      suffix: text.slice(index + exact.length, index + exact.length + 80),
    })
    if (anchor) {
      results.push({
        anchor,
        snippet: text.slice(Math.max(0, index - 28), index + exact.length + 42)
          .replace(/\s+/g, ' ').trim(),
      })
    }
    from = index + Math.max(1, exact.length)
  }
  return results
}

export const useDocumentSearch = ({
  getSourceModel,
  getSourceFormat,
  getPdfDocument,
  getDocumentElement,
  beforeOpen,
  jumpToAnchor,
}) => {
  const search = reactive({ query: '', open: false, loading: false, results: [], error: '' })
  let sequence = 0

  const close = () => {
    sequence += 1
    Object.assign(search, { open: false, loading: false, results: [], error: '' })
  }

  const run = async () => {
    const query = search.query.trim()
    if (!query) return ElMessage.warning('请输入要搜索的内容')
    beforeOpen?.()
    const currentSequence = ++sequence
    Object.assign(search, { open: true, loading: true, results: [], error: '' })
    try {
      const results = []
      const sourceModel = getSourceModel()
      if (getSourceFormat() === 'pdf') {
        const document = getPdfDocument()
        if (!document) throw new Error('文档尚未加载完成')
        for (let page = 1; page <= document.numPages && results.length < 100; page += 1) {
          if (currentSequence !== sequence) return
          const pdfPage = await document.getPage(page)
          if (currentSequence !== sequence) return
          const content = await pdfPage.getTextContent({ includeMarkedContent: true, disableNormalization: true })
          if (currentSequence !== sequence) return
          const text = content.items.map(item => item.str || '').join('')
          results.push(...collectDocumentMatches(text, query, sourceModel, {
            page,
            progression: document.numPages > 1 ? (page - 1) / (document.numPages - 1) : 0,
            limit: 100 - results.length,
          }))
          if (page % 4 === 0) await new Promise(resolve => requestAnimationFrame(resolve))
        }
      } else {
        results.push(...collectDocumentMatches(
          getDocumentElement()?.textContent || '', query, sourceModel,
        ))
      }
      if (currentSequence === sequence) search.results = results
    } catch (exception) {
      if (currentSequence === sequence) search.error = exception?.message || '搜索失败'
    } finally {
      if (currentSequence === sequence) search.loading = false
    }
  }

  const select = async result => {
    search.open = false
    await jumpToAnchor(result.anchor)
  }

  return { search, close, run, select }
}
