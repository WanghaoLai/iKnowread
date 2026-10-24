import request from '@/utils/request'
import { apiPath } from './apiPaths.js'

export const getReadingProgress = (documentId, options = {}) => request.get(
  apiPath('reading_progress.get', { document_id: documentId }),
  options,
)

export const saveReadingProgress = (sourceAnchor, options = {}) => request.put(
  apiPath('reading_progress.save'),
  { source_anchor: sourceAnchor },
  options,
)
