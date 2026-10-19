import assert from 'node:assert/strict'
import test from 'node:test'

import { useDocumentHighlights } from '../src/composables/useDocumentHighlights.js'

const item = (id, remark = '') => ({ id, remark, selected_text: `text-${id}` })

test('removing a highlight clears every dependent state', () => {
  const store = useDocumentHighlights()
  const first = item(1, 'one')
  const second = item(2, 'two')
  const firstRange = { name: 'first' }

  store.replaceAll([first, second])
  store.openDetail(first, { top: 1 })
  store.upsert(first, { selected: true })
  store.setResolvedRanges([{ item: first, range: firstRange }])

  store.removeLocal(first.id)

  assert.deepEqual(store.highlights.value, [second])
  assert.equal(store.highlightDetail.visible, false)
  assert.equal(store.highlightDetail.item, null)
  assert.equal(store.selectionHighlight.saved, false)
  assert.equal(store.selectionHighlight.id, null)
  assert.equal(store.rangeFor(first), undefined)
})

test('updating a highlight keeps the list and open detail synchronized', () => {
  const store = useDocumentHighlights()
  const original = item(1, 'before')
  const updated = item(1, 'after')

  store.replaceAll([original])
  store.openDetail(original, { top: 1 })
  store.upsert(updated)

  assert.deepEqual(store.highlights.value[0], updated)
  assert.deepEqual(store.highlightDetail.item, updated)
  assert.equal(store.highlightDetail.remark, 'after')
})

test('replacing a document highlight set removes stale UI references', () => {
  const store = useDocumentHighlights()
  const original = item(1)

  store.replaceAll([original])
  store.openDetail(original, { top: 1 })
  store.upsert(original, { selected: true })
  store.replaceAll([])

  assert.equal(store.highlightDetail.item, null)
  assert.equal(store.selectionHighlight.id, null)
})
