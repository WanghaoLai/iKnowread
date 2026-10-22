import request from '@/utils/request'
import { apiPath } from './apiPaths.js'

export function uploadAvatar({ file, data = {}, onProgress }) {
  const body = new FormData()
  for (const [key, value] of Object.entries(data || {})) {
    if (value !== null && value !== undefined && value !== '') body.append(key, String(value))
  }
  body.append('file', file, file.name)

  return request.post(apiPath('files.upload'), body, {
    skipErrorToast: true,
    onUploadProgress(event) {
      if (!onProgress) return
      const total = event.total || 0
      onProgress({
        loaded: event.loaded,
        total,
        percent: total > 0 ? event.loaded / total * 100 : 0,
      })
    },
  })
}
