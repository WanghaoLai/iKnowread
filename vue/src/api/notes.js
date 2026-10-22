import request from '@/utils/request'
import { apiPath } from './apiPaths.js'

export const listNotes = (params, options = {}) => request.get(apiPath('notes.list'), { ...options, params })
export const getNoteSummary = (options = {}) => request.get(apiPath('notes.summary'), options)
export const createNote = (payload, options = {}) => request.post(apiPath('notes.create'), payload, options)
export const updateNote = (id, payload, options = {}) => request.put(apiPath('notes.update', { note_id: id }), payload, options)
export const deleteNote = (id, options = {}) => request.delete(apiPath('notes.delete', { note_id: id }), options)
export const exportNotes = (payload, options = {}) => request.post(apiPath('notes.export'), payload, options)
