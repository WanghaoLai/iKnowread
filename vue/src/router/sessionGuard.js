import { apiPath } from '../api/apiPaths.js'

export const SESSION_VERIFY_TIMEOUT_MS = 8_000

export async function fetchVerifiedSession(
  baseUrl = '',
  { fetchImpl = globalThis.fetch, timeoutMs = SESSION_VERIFY_TIMEOUT_MS } = {},
) {
  const response = await fetchImpl(`${baseUrl}${apiPath('auth.me')}`, {
    credentials: 'include',
    signal: AbortSignal.timeout(timeoutMs),
  })
  if (!response.ok) throw new Error('unauthorized')
  const result = await response.json()
  if (result.code !== '200' || !result.data?.id) throw new Error('unauthorized')
  if (!result.data.is_experience) return result.data
  const policyResponse = await fetchImpl(`${baseUrl}${apiPath('experience.me')}`, {
    credentials: 'include',
    signal: AbortSignal.timeout(timeoutMs),
  })
  if (!policyResponse.ok) throw new Error('experience policy unavailable')
  const policyResult = await policyResponse.json()
  if (policyResult.code !== '200' || !policyResult.data?.enabled) {
    throw new Error('experience account disabled')
  }
  return { ...result.data, experience_policy: policyResult.data }
}
