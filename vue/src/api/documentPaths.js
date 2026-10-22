import { apiContract, apiPath } from './apiPaths.js'

const API_BASE = import.meta.env?.VITE_BASE_URL || ''

export const documentApiContract = Object.freeze(Object.fromEntries(
  Object.entries(apiContract)
    .filter(([name]) => name.startsWith('documents.'))
    .map(([name, endpoint]) => [name.slice('documents.'.length), endpoint]),
))
export const documentCollectionPath = apiPath('documents.list')
export const documentItemPath = id => apiPath('documents.delete', { doc_id: id })
export const documentPreviewPath = id => apiPath('documents.preview', { doc_id: id })
export const documentDownloadPath = id => apiPath('documents.download', { doc_id: id })
export const documentOcrPath = id => apiPath('documents.ocr', { doc_id: id })
export const documentOcrStatusPath = id => apiPath('documents.ocr_status', { doc_id: id })
export const documentRecyclePath = apiPath('documents.recycle_list')
export const documentRestorePath = id => apiPath('documents.restore', { doc_id: id })
export const documentPurgePath = id => apiPath('documents.purge', { doc_id: id })
export const documentPreviewUrl = id => `${API_BASE}${documentPreviewPath(id)}`
export const documentDownloadUrl = id => `${API_BASE}${documentDownloadPath(id)}`
