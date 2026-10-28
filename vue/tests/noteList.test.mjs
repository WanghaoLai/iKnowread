import assert from 'node:assert/strict'
import test from 'node:test'

import {
  groupNotes,
  noteDocumentNameFilter,
  noteDocumentStatus,
  noteGroupLabel,
  noteGroupValue,
} from '../src/features/notes/noteList.js'

test('note document filters keep active, deleted, and unlinked sources distinct', () => {
  assert.equal(noteGroupValue({ document_id: 7, document_name: 'A' }), 7)
  assert.equal(noteGroupValue({ document_id: null, document_name: '已删除文档' }), 'name:已删除文档')
  assert.equal(noteGroupValue({ document_id: null, document_name: null }), 'unlinked')
  assert.equal(noteDocumentNameFilter('name:已删除文档'), '已删除文档')
  assert.equal(noteDocumentNameFilter('unlinked'), undefined)
  assert.equal(noteGroupLabel({ document_id: null, document_name: null }), '未关联文档')
})

test('note status fallback and document grouping preserve display semantics', () => {
  assert.deepEqual(noteDocumentStatus({ document_id: 1 }), { label: '可阅读', type: 'success' })
  assert.deepEqual(noteDocumentStatus({ document_id: null, document_name: '旧文档' }), { label: '原文已删除', type: 'danger' })
  const notes = [
    { id: 1, document_id: 2, document_name: 'B' },
    { id: 2, document_id: 2, document_name: 'B' },
    { id: 3, document_id: null, document_name: null },
  ]
  assert.deepEqual(groupNotes(notes, 'document').map(group => [group.name, group.items.length]), [
    ['B', 2],
    ['未关联文档', 1],
  ])
  assert.equal(groupNotes(notes, 'timeline')[0].items, notes)
})
