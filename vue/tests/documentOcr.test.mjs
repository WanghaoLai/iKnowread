import assert from 'node:assert/strict'
import test from 'node:test'

import {
  buildVersionedDocumentUrl,
  useDocumentOcr,
} from '../src/composables/useDocumentOcr.js'

test('derived OCR revisions bust the preview cache without changing source version', () => {
  const version = 'a'.repeat(32)
  assert.equal(
    buildVersionedDocumentUrl('/documents/7/preview', version, '2026-10-16T10:00:00Z'),
    `/documents/7/preview?version=${version}&revision=2026-10-16T10%3A00%3A00Z`,
  )
  assert.equal(
    buildVersionedDocumentUrl('/documents/7/preview?download=0', version),
    `/documents/7/preview?download=0&version=${version}`,
  )
})

test('ready derivative reloads once while preserving annotation version', async () => {
  const version = 'b'.repeat(32)
  const model = {
    id: 7,
    url: '/documents/7/preview',
    contentVersion: version,
    ocrStatus: 'processing',
    ocrUpdatedAt: 'old',
  }
  let reloads = 0
  let notifications = 0
  const ocr = useDocumentOcr({
    getModel: () => model,
    reload: async () => { reloads += 1 },
    notifyReady: () => { notifications += 1 },
    fetchStatus: async () => ({ data: {
      content_version: version,
      ocr_status: 'ready',
      ocr_error: null,
      ocr_updated_at: 'new',
    } }),
    requestRetry: async () => ({ data: { ocr_status: 'pending' } }),
    pollDelay: 60_000,
  })

  await ocr.refresh()
  ocr.stop()

  assert.equal(ocr.contentVersion.value, version)
  assert.match(ocr.activeUrl.value, /revision=new/)
  assert.equal(reloads, 1)
  assert.equal(notifications, 1)
})

test('status request failures stop automatic polling', async () => {
  const model = {
    id: 8,
    url: '/documents/8/preview',
    contentVersion: 'c'.repeat(32),
    ocrStatus: 'pending',
  }
  const ocr = useDocumentOcr({
    getModel: () => model,
    reload: async () => {},
    fetchStatus: async () => { throw new Error('network') },
    requestRetry: async () => ({ data: { ocr_status: 'pending' } }),
    pollDelay: 60_000,
  })
  await ocr.refresh()
  ocr.stop()
  assert.equal(ocr.ocrStatus.value, 'pending')
})

test('retry failures are reported and do not escape the click handler', async () => {
  const failure = new Error('network')
  let reported = null
  const ocr = useDocumentOcr({
    getModel: () => ({
      id: 9,
      url: '/documents/9/preview',
      contentVersion: 'd'.repeat(32),
      ocrStatus: 'failed',
      ocrError: '识别失败',
    }),
    reload: async () => {},
    fetchStatus: async () => ({ data: {} }),
    requestRetry: async () => { throw failure },
    notifyRetryError: async error => { reported = error },
    pollDelay: 60_000,
  })

  await ocr.retry()

  assert.equal(reported, failure)
  assert.equal(ocr.ocrRetrying.value, false)
  assert.equal(ocr.ocrStatus.value, 'failed')
  assert.equal(ocr.ocrError.value, '识别失败')
})
