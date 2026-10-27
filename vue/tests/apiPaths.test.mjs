import assert from 'node:assert/strict'
import test from 'node:test'

import { apiMethod, apiPath } from '../src/api/apiPaths.js'

test('renders shared API paths with validated identifiers', () => {
  assert.equal(apiPath('auth.login'), '/login')
  assert.equal(apiPath('web_imports.retry', { job_id: 12 }), '/web-imports/12/retry')
  assert.equal(apiPath('notes.update', { note_id: 7 }), '/notes/7')
  assert.equal(apiPath('ai.config_models', { config_id: 3 }), '/ai/configs/3/models')
  assert.equal(apiMethod('ai.config_models'), 'GET')
  assert.equal(apiPath('dashboard.summary'), '/dashboard')
  assert.equal(apiPath('reading_progress.get', { document_id: 9 }), '/reading-progress/9')
  assert.equal(apiMethod('reading_progress.save'), 'PUT')
  assert.equal(apiPath('announcements.list'), '/announcements')
  assert.equal(apiPath('announcements.read', { announcement_id: 5 }), '/announcements/5/read')
  assert.equal(apiMethod('announcements.read_all'), 'PUT')
  assert.equal(apiPath('announcements.admin_list'), '/admin/announcements')
  assert.equal(apiPath('announcements.status', { announcement_id: 8 }), '/admin/announcements/8/status')
  assert.equal(apiMethod('announcements.delete'), 'DELETE')
  assert.equal(apiPath('experience.me'), '/experience/me')
  assert.equal(apiPath('experience.admin_settings'), '/admin/experience')
  assert.equal(apiMethod('experience.update_admin_settings'), 'PUT')
})

test('rejects missing, invalid and unknown API path inputs', () => {
  assert.throws(() => apiPath('notes.update'), /positive integer/)
  assert.throws(() => apiPath('notes.update', { note_id: '../admin' }), /positive integer/)
  assert.throws(() => apiPath('missing.endpoint'), /unknown API endpoint/)
})
