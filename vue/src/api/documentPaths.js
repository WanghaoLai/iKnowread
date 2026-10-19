import contract from './documentContract.json' with { type: 'json' }

const API_BASE = import.meta.env?.VITE_BASE_URL || ''

const documentId = value => {
  const normalized = Number(value)
  if (!Number.isSafeInteger(normalized) || normalized < 1) {
    throw new TypeError('document id must be a positive integer')
  }
  return String(normalized)
}

const render = (name, id) => {
  const path = contract[name]?.path
  if (!path) throw new TypeError(`unknown document endpoint: ${name}`)
  return path.includes('{doc_id}')
    ? path.replace('{doc_id}', documentId(id))
    : path
}

export const documentApiContract = Object.freeze(contract)
export const documentCollectionPath = render('list')
export const documentItemPath = id => render('delete', id)
export const documentPreviewPath = id => render('preview', id)
export const documentDownloadPath = id => render('download', id)
export const documentOcrPath = id => render('ocr', id)
export const documentOcrStatusPath = id => render('ocr_status', id)
export const documentRecyclePath = render('recycle_list')
export const documentRestorePath = id => render('restore', id)
export const documentPurgePath = id => render('purge', id)
export const documentPreviewUrl = id => `${API_BASE}${documentPreviewPath(id)}`
export const documentDownloadUrl = id => `${API_BASE}${documentDownloadPath(id)}`
