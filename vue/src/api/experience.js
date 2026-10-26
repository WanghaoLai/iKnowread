import request from '@/utils/request'
import { apiPath } from './apiPaths'

export const getExperiencePolicy = (options = {}) => request.get(
  apiPath('experience.me'), options,
)

export const getExperienceSettings = (options = {}) => request.get(
  apiPath('experience.admin_settings'), options,
)

export const updateExperienceSettings = (payload, options = {}) => request.put(
  apiPath('experience.update_admin_settings'), payload, options,
)

export const listExperienceDocuments = (params, options = {}) => request.get(
  apiPath('experience.admin_documents'), { ...options, params },
)
