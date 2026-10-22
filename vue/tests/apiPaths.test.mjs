import assert from 'node:assert/strict'
import test from 'node:test'

import { apiMethod, apiPath } from '../src/api/apiPaths.js'

test('renders shared API paths with validated identifiers', () => {
  assert.equal(apiPath('auth.login'), '/login')
  assert.equal(apiPath('web_imports.retry', { job_id: 12 }), '/web-imports/12/retry')
  assert.equal(apiPath('notes.update', { note_id: 7 }), '/notes/7')
  assert.equal(apiPath('ai.config_models', { config_id: 3 }), '/ai/configs/3/models')
  assert.equal(apiMethod('ai.config_models'), 'GET')
})

test('rejects missing, invalid and unknown API path inputs', () => {
  assert.throws(() => apiPath('notes.update'), /positive integer/)
  assert.throws(() => apiPath('notes.update', { note_id: '../admin' }), /positive integer/)
  assert.throws(() => apiPath('missing.endpoint'), /unknown API endpoint/)
})
