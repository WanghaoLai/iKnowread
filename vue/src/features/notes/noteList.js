const DOCUMENT_STATUSES = Object.freeze({
  available: { label: '可阅读', type: 'success' },
  recycled: { label: '回收站', type: 'warning' },
  deleted: { label: '原文已删除', type: 'danger' },
  unlinked: { label: '未关联', type: 'info' },
})

export const noteDocumentStatus = note => DOCUMENT_STATUSES[note.document_status] || (
  note.document_id ? DOCUMENT_STATUSES.available
    : note.document_name ? DOCUMENT_STATUSES.deleted : DOCUMENT_STATUSES.unlinked
)

export const noteGroupLabel = item => (
  item.document_name || (item.document_id === null ? '未关联文档' : '未命名文档')
)

export const noteGroupValue = item => {
  if (item.document_id !== null && item.document_id !== undefined) return item.document_id
  return item.document_name ? `name:${item.document_name}` : 'unlinked'
}

export const noteDocumentNameFilter = value => (
  typeof value === 'string' && value.startsWith('name:') ? value.slice(5) : undefined
)

export const groupNotes = (notes, viewMode) => {
  if (viewMode !== 'document') return [{ key: 'timeline', name: '', items: notes }]
  const groups = new Map()
  for (const note of notes) {
    const key = `${note.document_id ?? 'none'}:${note.document_name || '未关联文档'}`
    if (!groups.has(key)) {
      groups.set(key, { key, name: note.document_name || '未关联文档', items: [] })
    }
    groups.get(key).items.push(note)
  }
  return [...groups.values()]
}
