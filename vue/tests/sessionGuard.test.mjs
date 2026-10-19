import assert from 'node:assert/strict'
import test from 'node:test'

import {
  SESSION_VERIFY_TIMEOUT_MS,
  fetchVerifiedSession,
} from '../src/router/sessionGuard.js'

test('session verification has a bounded default timeout', async () => {
  let requestOptions
  const fetchImpl = async (_url, options) => {
    requestOptions = options
    return { ok: true, json: async () => ({ code: '200', data: { id: 7 } }) }
  }

  const user = await fetchVerifiedSession('/api', { fetchImpl })

  assert.equal(user.id, 7)
  assert.equal(requestOptions.credentials, 'include')
  assert.ok(requestOptions.signal instanceof AbortSignal)
  assert.equal(SESSION_VERIFY_TIMEOUT_MS, 8_000)
})

test('a hanging session request aborts instead of freezing navigation', async () => {
  const fetchImpl = (_url, { signal }) => new Promise((_resolve, reject) => {
    signal.addEventListener('abort', () => reject(signal.reason), { once: true })
  })

  await assert.rejects(
    fetchVerifiedSession('', { fetchImpl, timeoutMs: 10 }),
    error => error?.name === 'TimeoutError',
  )
})
