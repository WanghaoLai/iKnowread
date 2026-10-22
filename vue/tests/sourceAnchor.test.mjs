import assert from 'node:assert/strict'
import test from 'node:test'

import {
  createPointAnchor,
  createTextAnchor,
  isSourceAnchor,
  readingProgressKey,
} from '../src/utils/sourceAnchor.js'

const pdf = {
  id: 7,
  sourceFormat: 'pdf',
  contentVersion: 'a'.repeat(32),
}

test('creates a bounded PDF point anchor', () => {
  const anchor = createPointAnchor(pdf, { page: 3, progression: 2 })
  assert.equal(anchor.page, 3)
  assert.equal(anchor.progression, 1)
  assert.equal(anchor.scope, 'page')
  assert.ok(isSourceAnchor(anchor))
  assert.equal(readingProgressKey(anchor), `iknowread:reading-progress:7:${'a'.repeat(32)}`)
})

test('rejects stale or malformed source anchors', () => {
  const valid = createTextAnchor(pdf, {
    page: 1,
    progression: 0.2,
    start: 2,
    end: 4,
    exact: '原文',
  })
  assert.ok(isSourceAnchor(valid))
  assert.equal(isSourceAnchor({ ...valid, document_version: 'stale' }), false)
  assert.equal(isSourceAnchor({ ...valid, selector: { ...valid.selector, position: { start: 4, end: 2 } } }), false)
})

test('uses document scope for DOCX anchors', () => {
  const anchor = createPointAnchor({ ...pdf, sourceFormat: 'docx' }, { page: 9, progression: 0.4 })
  assert.equal(anchor.page, null)
  assert.equal(anchor.scope, 'document')
  assert.ok(isSourceAnchor(anchor))
})

test('uses document scope for Markdown anchors', () => {
  const anchor = createPointAnchor({ ...pdf, sourceFormat: 'md' }, { page: 9, progression: 0.6 })
  assert.equal(anchor.page, null)
  assert.equal(anchor.scope, 'document')
  assert.ok(isSourceAnchor(anchor))
})
