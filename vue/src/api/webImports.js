import request from '@/utils/request'
import { apiPath } from './apiPaths.js'

const jobPath = (name, id) => apiPath(name, { job_id: id })

export const createWebImport = (url, options = {}) => request.post(apiPath('web_imports.create'), { url }, options)
export const listWebImports = (options = {}) => request.get(apiPath('web_imports.list'), options)
export const getWebImport = (id, options = {}) => request.get(jobPath('web_imports.get', id), options)
export const retryWebImport = (id, options = {}) => request.post(jobPath('web_imports.retry', id), null, options)
export const cancelWebImport = (id, options = {}) => request.post(jobPath('web_imports.cancel', id), null, options)
export const deleteWebImport = (id, options = {}) => request.delete(jobPath('web_imports.delete', id), options)
