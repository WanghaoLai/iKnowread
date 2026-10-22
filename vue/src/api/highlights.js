import request from '@/utils/request'
import { apiPath } from './apiPaths.js'

export const listHighlights = (params, options = {}) => request.get(apiPath('highlights.list'), { ...options, params })
export const createHighlight = (payload, options = {}) => request.post(apiPath('highlights.create'), payload, options)
export const updateHighlight = (id, payload, options = {}) => request.put(apiPath('highlights.update', { highlight_id: id }), payload, options)
export const deleteHighlight = (id, options = {}) => request.delete(apiPath('highlights.delete', { highlight_id: id }), options)
