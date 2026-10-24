import request from '@/utils/request'
import { apiPath } from './apiPaths.js'

export const getDashboard = (options = {}) => request.get(apiPath('dashboard.summary'), options)
