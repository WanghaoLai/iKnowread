const SESSION_KEY = 'iknowread-user'

export function getSession() {
  try {
    const value = JSON.parse(localStorage.getItem(SESSION_KEY) || '{}')
    return value && typeof value === 'object' ? value : {}
  } catch (_) {
    localStorage.removeItem(SESSION_KEY)
    return {}
  }
}

export function setSession(account) {
  localStorage.setItem(SESSION_KEY, JSON.stringify(account || {}))
}

export function clearSession() {
  localStorage.removeItem(SESSION_KEY)
}
