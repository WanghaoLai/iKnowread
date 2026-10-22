import assert from 'node:assert/strict'
import test from 'node:test'

import { documentDownloadUrl, documentPreviewUrl } from '../src/api/documentPaths.js'
import { buildPreviewModel, fetchBytes, fetchText } from '../src/utils/preview.js'

test('maps supported formats to their protected preview endpoints', () => {
  const pdf = buildPreviewModel({
    id: 4,
    name: 'paper.pdf',
    ext: 'PDF',
    content_version: 'b'.repeat(32),
    ocr_status: 'ready',
  })
  assert.equal(pdf.engine, 'pdfjs')
  assert.equal(pdf.url, documentPreviewUrl(4))
  assert.equal(pdf.ocrStatus, 'ready')

  const docx = buildPreviewModel({ id: 5, name: 'note.docx', ext: 'docx' })
  assert.equal(docx.engine, 'docx')
  assert.equal(docx.url, documentDownloadUrl(5))
  const markdown = buildPreviewModel({
    id: 6, name: 'notes.md', ext: 'MD', source_type: 'url',
    source_url: 'https://example.com/article', source_title: '文章',
  })
  assert.equal(markdown.engine, 'markdown')
  assert.equal(markdown.url, documentDownloadUrl(6))
  assert.equal(markdown.ocrStatus, 'not_applicable')
  assert.equal(markdown.sourceType, 'url')
  assert.equal(markdown.sourceUrl, 'https://example.com/article')
  assert.equal(buildPreviewModel({ id: 7, ext: 'txt' }), null)
})

test('fetchText preserves credentials and decodes UTF-8 Markdown', async t => {
  const previous = globalThis.fetch
  t.after(() => { globalThis.fetch = previous })
  globalThis.fetch = async (_url, options) => {
    assert.equal(options.credentials, 'include')
    return new Response('\uFEFF# 标题\n\n正文', {
      status: 200,
      headers: { 'content-type': 'text/markdown; charset=utf-8' },
    })
  }
  assert.equal(await fetchText(documentDownloadUrl(6)), '# 标题\n\n正文')
})

test('fetchBytes preserves credentials and returns binary data', async t => {
  const previous = globalThis.fetch
  t.after(() => { globalThis.fetch = previous })
  globalThis.fetch = async (url, options) => {
    assert.equal(url, documentPreviewUrl(4))
    assert.equal(options.credentials, 'include')
    return new Response(new Uint8Array([1, 2, 3]), {
      status: 200,
      headers: { 'content-type': 'application/pdf' },
    })
  }
  const bytes = await fetchBytes(documentPreviewUrl(4))
  assert.deepEqual([...new Uint8Array(bytes)], [1, 2, 3])
})

test('fetchBytes surfaces the API error message', async t => {
  const previous = globalThis.fetch
  t.after(() => { globalThis.fetch = previous })
  globalThis.fetch = async () => new Response(JSON.stringify({ msg: '文档已删除' }), {
    status: 404,
    headers: { 'content-type': 'application/json' },
  })
  await assert.rejects(() => fetchBytes(documentPreviewUrl(9)), /文档已删除/)
})
