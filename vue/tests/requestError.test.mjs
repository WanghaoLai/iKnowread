import assert from 'node:assert/strict'
import test from 'node:test'

import { extractRequestErrorMessage } from '../src/utils/requestError.js'

test('extracts the API message from a JSON Blob response', async () => {
  const error = {
    response: {
      data: new Blob([JSON.stringify({ msg: '导出数量超过限制' })], {
        type: 'application/json',
      }),
      headers: { 'content-type': 'application/json; charset=utf-8' },
    },
  }

  assert.equal(await extractRequestErrorMessage(error, '导出失败'), '导出数量超过限制')
})

test('preserves regular structured API errors', async () => {
  const error = { response: { data: { detail: '无权导出这些笔记' } } }
  assert.equal(await extractRequestErrorMessage(error, '导出失败'), '无权导出这些笔记')
})

test('uses the caller fallback for non-JSON binary errors', async () => {
  const error = {
    response: {
      data: new Blob(['binary'], { type: 'application/octet-stream' }),
      headers: { 'content-type': 'application/octet-stream' },
    },
  }
  assert.equal(await extractRequestErrorMessage(error, '笔记导出失败'), '笔记导出失败')
})
