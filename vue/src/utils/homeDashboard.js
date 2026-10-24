import {
  createPointAnchor,
  isSourceAnchor,
  readingProgressKey,
} from './sourceAnchor.js'

const sourceModel = document => ({
  id: Number(document?.id),
  contentVersion: document?.content_version || '',
  sourceFormat: String(document?.ext || '').toLowerCase(),
})

export function collectReadingProgress(documents, storage = globalThis.localStorage) {
  if (!storage?.getItem) return []
  return (documents || []).flatMap(document => {
    const point = createPointAnchor(sourceModel(document), { page: 1 })
    const key = readingProgressKey(point)
    if (!key) return []
    try {
      const anchor = JSON.parse(storage.getItem(key) || 'null')
      if (!isSourceAnchor(anchor)) return []
      if (anchor.document_id !== Number(document.id)) return []
      if (anchor.document_version !== document.content_version) return []
      return [{
        document,
        anchor,
        percent: Math.round(anchor.progression * 100),
      }]
    } catch (_) {
      return []
    }
  })
}

export function documentTypeLabel(document) {
  if (document?.source_type === 'url') return '网页'
  return ({ pdf: 'PDF', docx: 'DOCX', md: 'MD' })[String(document?.ext || '').toLowerCase()] || '文档'
}

export function webImportHost(sourceUrl) {
  try {
    return new URL(sourceUrl).hostname.replace(/^www\./, '')
  } catch (_) {
    return sourceUrl || '网页导入任务'
  }
}
