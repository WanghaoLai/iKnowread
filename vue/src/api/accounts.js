import request from '@/utils/request'
import { apiPath } from './apiPaths.js'

const accountPath = (name, id) => apiPath(name, { account_id: id })

export const listAccounts = (params, options = {}) => request.get(apiPath('accounts.list'), { ...options, params })
export const createAccount = (payload, options = {}) => request.post(apiPath('accounts.create'), payload, options)
export const updateAccount = (id, payload, options = {}) => request.put(accountPath('accounts.update', id), payload, options)
export const deleteAccount = (id, options = {}) => request.delete(accountPath('accounts.delete', id), options)
