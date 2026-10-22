import request from '@/utils/request'
import { apiPath } from './apiPaths.js'

const configPath = (name, id) => apiPath(name, { config_id: id })

export const getActiveAiConfig = (options = {}) => request.get(apiPath('ai.active_config'), options)
export const listAiProviders = (options = {}) => request.get(apiPath('ai.providers'), options)
export const listAiConfigs = (options = {}) => request.get(apiPath('ai.configs'), options)
export const createAiConfig = (payload, options = {}) => request.post(apiPath('ai.create_config'), payload, options)
export const updateAiConfig = (id, payload, options = {}) => request.put(configPath('ai.update_config', id), payload, options)
export const deleteAiConfig = (id, options = {}) => request.delete(configPath('ai.delete_config', id), options)
export const activateAiConfig = (id, options = {}) => request.post(configPath('ai.activate_config', id), null, options)
export const testSavedAiConfig = (id, options = {}) => request.post(configPath('ai.test_saved_config', id), {}, options)
export const getAiConfigModels = (id, options = {}) => request.get(configPath('ai.config_models', id), options)
export const chatWithAi = (payload, options = {}) => request.post(apiPath('ai.chat'), payload, options)
export const explainSelection = (payload, options = {}) => request.post(apiPath('ai.explain'), payload, options)
