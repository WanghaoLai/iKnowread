import assert from 'node:assert/strict'
import test from 'node:test'

import {
  collectReadingProgress,
  documentTypeLabel,
  webImportHost,
} from '../src/utils/homeDashboard.js'

const version = 'a'.repeat(32)
const pdf = {
  id: 7,
  name: '研究报告.pdf',
  ext: 'pdf',
  content_version: version,
  processing_stages: [{ status: 'ready' }],
}

test('dashboard only restores progress for the current document version', () => {
  const anchor = {
    protocol: 'iknowread.source-anchor/v1',
    document_id: 7,
    document_version: version,
    source_format: 'pdf',
    scope: 'page',
    page: 4,
    progression: 0.375,
    selector: null,
  }
  const storage = new Map([
    [`iknowread:reading-progress:7:${version}`, JSON.stringify(anchor)],
    [`iknowread:reading-progress:8:${version}`, '{malformed'],
  ])
  storage.getItem = storage.get.bind(storage)

  const current = collectReadingProgress([pdf], storage)
  const replaced = collectReadingProgress([{ ...pdf, content_version: 'b'.repeat(32) }], storage)

  assert.equal(current.length, 1)
  assert.equal(current[0].anchor.page, 4)
  assert.equal(current[0].percent, 38)
  assert.deepEqual(replaced, [])
})

test('dashboard presents stable labels for local and web documents', () => {
  assert.equal(documentTypeLabel(pdf), 'PDF')
  assert.equal(documentTypeLabel({ ...pdf, ext: 'md' }), 'MD')
  assert.equal(documentTypeLabel({ ...pdf, source_type: 'url' }), '网页')
  assert.equal(webImportHost('https://www.example.com/articles/1'), 'example.com')
})
