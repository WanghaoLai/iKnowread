import assert from 'node:assert/strict'
import test from 'node:test'

import {
  documentApiContract,
  documentCollectionPath,
  documentDownloadPath,
  documentItemPath,
  documentOcrPath,
  documentOcrStatusPath,
  documentPreviewPath,
  documentPurgePath,
  documentRecyclePath,
  documentRestorePath,
} from '../src/api/documentPaths.js'

test('builds every document path from the shared contract', () => {
  assert.equal(documentCollectionPath, '/documents')
  assert.equal(documentItemPath(7), '/documents/7')
  assert.equal(documentPreviewPath(7), '/documents/7/preview')
  assert.equal(documentDownloadPath(7), '/documents/7/download')
  assert.equal(documentOcrPath(7), '/documents/7/ocr')
  assert.equal(documentOcrStatusPath(7), '/documents/7/ocr-status')
  assert.equal(documentRecyclePath, '/documents/recycle-bin')
  assert.equal(documentRestorePath(7), '/documents/recycle-bin/7/restore')
  assert.equal(documentPurgePath(7), '/documents/recycle-bin/7')
  assert.equal(Object.keys(documentApiContract).length, 11)
})

test('rejects invalid document identifiers before issuing a request', () => {
  for (const value of [undefined, null, 0, -1, 1.5, 'not-an-id']) {
    assert.throws(() => documentItemPath(value), /positive integer/)
  }
})
