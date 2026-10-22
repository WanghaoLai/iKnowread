import assert from 'node:assert/strict'
import test from 'node:test'
import createDOMPurify from 'dompurify'
import { JSDOM } from 'jsdom'

import {
  blockRemoteMarkdownImages,
  markdownToHtml,
  parseMarkdownDocument,
  sanitizeMarkdownHtml,
} from '../src/utils/markdown.js'

test('parses common Markdown structures while escaping raw HTML', () => {
  const html = markdownToHtml('# 标题\n\n- 列表\n\n**加粗**与 `代码`\n\n<script>alert(1)</script>')
  assert.match(html, /<h1>标题<\/h1>/)
  assert.match(html, /<ul>/)
  assert.match(html, /<strong>加粗<\/strong>/)
  assert.match(html, /<code>代码<\/code>/)
  assert.doesNotMatch(html, /<script>/)
  assert.match(html, /&lt;script&gt;/)
})

test('does not turn dangerous Markdown links into executable anchors', () => {
  const html = markdownToHtml('[危险](javascript:alert(1)) [安全](https://example.com)')
  assert.doesNotMatch(html, /href="javascript:/)
  assert.match(html, /href="https:\/\/example\.com"/)
  assert.match(html, /rel="noopener noreferrer nofollow"/)
})

test('real DOMPurify removes executable markup and unsafe attributes', () => {
  const window = new JSDOM('').window
  const sanitizer = createDOMPurify(window)
  const cleaned = sanitizeMarkdownHtml(
    '<p style="background:url(https://tracker.example)">safe</p>'
      + '<script>alert(1)</script><iframe src="https://evil.example"></iframe>'
      + '<img src="x" onerror="alert(2)"><a href="javascript:alert(3)" target="_blank">x</a>',
    sanitizer,
  )
  assert.match(cleaned, /<p>safe<\/p>/)
  assert.doesNotMatch(cleaned, /script|iframe|onerror|style=|javascript:/i)
  assert.match(cleaned, /target="_blank"/)
  window.close()
})

test('blocks remote Markdown images in a real DOM tree', () => {
  const dom = new JSDOM(
    '<main><img id="remote" src="https://tracker.example/pixel.png">'
      + '<img id="relative" src="./local.png"><img id="data" src="data:image/png;base64,AA=="></main>',
    { url: 'https://reader.example/document' },
  )
  const root = dom.window.document.querySelector('main')
  blockRemoteMarkdownImages(root, dom.window.location.href)
  const remote = root.querySelector('#remote')
  const relative = root.querySelector('#relative')
  const data = root.querySelector('#data')
  assert.equal(remote.hasAttribute('src'), false)
  assert.equal(remote.dataset.remoteImageBlocked, 'true')
  // Relative URLs resolve to HTTPS and would still leak the current document
  // location to a server, so they are blocked by the same policy.
  assert.equal(relative.hasAttribute('src'), false)
  assert.equal(data.getAttribute('src'), 'data:image/png;base64,AA==')
  dom.window.close()
})

test('removes generated frontmatter from the visible article', () => {
  const source = '---\nsource: url\ntitle: "示例"\n---\n\n# 正文'
  const parsed = parseMarkdownDocument(source)
  assert.match(parsed.frontmatter, /source: url/)
  assert.equal(parsed.body, '\n# 正文')
  assert.doesNotMatch(markdownToHtml(source), /source: url/)
  assert.match(markdownToHtml(source), /<h1>正文<\/h1>/)
})
