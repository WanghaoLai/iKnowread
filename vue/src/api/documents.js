import request from '@/utils/request'
import {
  documentCollectionPath,
  documentItemPath,
  documentOcrPath,
  documentOcrStatusPath,
  documentPurgePath,
  documentRecyclePath,
  documentRestorePath,
} from './documentPaths'

export const listDocuments = (params, options = {}) => request.get(
  documentCollectionPath,
  { ...options, params },
)

export const getDocumentOcrStatus = (id, options = {}) => request.get(
  documentOcrStatusPath(id),
  options,
)

export const retryDocumentOcr = (id, options = {}) => request.post(documentOcrPath(id), null, options)
export const recycleDocument = id => request.delete(documentItemPath(id))

export const listRecycledDocuments = (params, options = {}) => request.get(
  documentRecyclePath,
  { ...options, params },
)

export const restoreDocument = id => request.post(documentRestorePath(id))
export const purgeDocument = id => request.delete(documentPurgePath(id))

export const uploadDocument = (file, options = {}) => {
  const formData = new FormData()
  formData.append('file', file)
  return request.post(documentCollectionPath, formData, options)
}
