function headerValue(headers, name) {
  if (!headers) return ''
  if (typeof headers.get === 'function') return headers.get(name) || ''
  return headers[name] || headers[name.toLowerCase()] || ''
}

function payloadMessage(payload) {
  if (!payload || typeof payload !== 'object') return ''
  if (typeof payload.msg === 'string' && payload.msg.trim()) return payload.msg
  if (typeof payload.detail === 'string' && payload.detail.trim()) return payload.detail
  return ''
}

function isBlobLike(value) {
  return value && typeof value === 'object' && typeof value.text === 'function'
}

export async function extractRequestErrorMessage(error, fallback = '请求失败，请稍后重试') {
  const response = error?.response
  let payload = response?.data
  const contentType = String(
    headerValue(response?.headers, 'content-type') || payload?.type || '',
  ).toLowerCase()

  if (isBlobLike(payload) && contentType.includes('json')) {
    try {
      payload = JSON.parse(await payload.text())
    } catch (_) {
      return fallback
    }
  }

  if (typeof payload === 'string' && contentType.includes('json')) {
    try {
      payload = JSON.parse(payload)
    } catch (_) {
      return fallback
    }
  }

  return payloadMessage(payload) || fallback
}
