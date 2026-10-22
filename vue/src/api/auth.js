import request from '@/utils/request'
import { apiPath } from './apiPaths.js'

export const getCapabilities = (options = {}) => request.get(apiPath('meta.capabilities'), options)
export const getCaptcha = (options = {}) => request.get(apiPath('auth.captcha'), options)
export const getCurrentAccount = (options = {}) => request.get(apiPath('auth.me'), options)
export const loginAccount = (payload, options = {}) => request.post(apiPath('auth.login'), payload, options)
export const logoutAccount = (options = {}) => request.post(apiPath('auth.logout'), null, options)
export const registerAccount = (payload, options = {}) => request.post(apiPath('auth.register'), payload, options)
export const updatePassword = (payload, options = {}) => request.put(apiPath('auth.password'), payload, options)
