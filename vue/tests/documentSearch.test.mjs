import assert from 'node:assert/strict'
import test from 'node:test'

import { collectDocumentMatches } from '../src/composables/useDocumentSearch.js'

const source = { id: 7, contentVersion: 'a'.repeat(32), sourceFormat: 'pdf' }

test('document search creates bounded source anchors for every match', () => {
  const results = collectDocumentMatches('Alpha beta alpha', 'alpha', source, { page: 2 })

  assert.equal(results.length, 2)
  assert.equal(results[0].anchor.document_id, 7)
  assert.equal(results[0].anchor.page, 2)
  assert.deepEqual(results.map(result => result.anchor.selector.position.start), [0, 11])
})

test('document search respects its result limit', () => {
  const results = collectDocumentMatches('a a a a', 'a', source, { limit: 2 })
  assert.equal(results.length, 2)
})
