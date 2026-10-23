import assert from 'node:assert/strict'
import test from 'node:test'

import {
  announcementStatus,
  applyAllAnnouncementsRead,
  applyAnnouncementRead,
} from '../src/utils/announcements.js'

test('marks one unread announcement without mutating source rows', () => {
  const source = [
    { id: 1, title: '一', is_read: false },
    { id: 2, title: '二', is_read: false },
  ]
  const result = applyAnnouncementRead(source, 1)

  assert.equal(result.changed, true)
  assert.equal(result.items[0].is_read, true)
  assert.equal(result.items[1], source[1])
  assert.equal(source[0].is_read, false)
})

test('reading an already-read or missing announcement is idempotent', () => {
  const source = [{ id: 1, is_read: true }]
  assert.deepEqual(applyAnnouncementRead(source, 1), { items: source, changed: false })
  assert.deepEqual(applyAnnouncementRead(source, 2), { items: source, changed: false })
})

test('marks every visible announcement read and exposes stable status labels', () => {
  const source = [{ id: 1, is_read: false }, { id: 2, is_read: true }]
  const result = applyAllAnnouncementsRead(source)

  assert.deepEqual(result.map(item => item.is_read), [true, true])
  assert.equal(source[0].is_read, false)
  assert.deepEqual(announcementStatus('published'), { label: '已发布', type: 'success' })
  assert.equal(announcementStatus('unexpected').label, 'unexpected')
})
