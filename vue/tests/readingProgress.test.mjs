import assert from 'node:assert/strict'
import test from 'node:test'

import { useReadingProgress } from '../src/composables/useReadingProgress.js'

const model = { id: 9, contentVersion: 'b'.repeat(32), sourceFormat: 'pdf' }

test('paged reading progress is derived from the current page', () => {
  const progress = useReadingProgress({
    getSourceModel: () => model,
    getSourceFormat: () => 'pdf',
    getPage: () => 3,
    getPageCount: () => 5,
    getReadingMode: () => 'paged',
    getScrollElement: () => null,
  })

  assert.equal(progress.currentAnchor().progression, 0.5)
})

test('continuous reading progress is derived from scroll position', () => {
  const progress = useReadingProgress({
    getSourceModel: () => model,
    getSourceFormat: () => 'pdf',
    getPage: () => 2,
    getPageCount: () => 5,
    getReadingMode: () => 'continuous',
    getScrollElement: () => ({ scrollTop: 300, scrollHeight: 1000, clientHeight: 400 }),
  })

  assert.equal(progress.currentAnchor().progression, 0.5)
})
