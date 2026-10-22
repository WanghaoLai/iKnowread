import createDOMPurify from 'dompurify'
import MarkdownIt from 'markdown-it'

const parser = new MarkdownIt({
  html: false,
  linkify: true,
  typographer: false,
})

const defaultLinkOpen = parser.renderer.rules.link_open
  || ((tokens, index, options, _environment, renderer) => renderer.renderToken(tokens, index, options))

parser.renderer.rules.link_open = (tokens, index, options, environment, renderer) => {
  const token = tokens[index]
  token.attrSet('target', '_blank')
  token.attrSet('rel', 'noopener noreferrer nofollow')
  return defaultLinkOpen(tokens, index, options, environment, renderer)
}

const purifier = typeof window === 'undefined' ? null : createDOMPurify(window)
const SANITIZE_OPTIONS = Object.freeze({
  USE_PROFILES: { html: true },
  FORBID_TAGS: ['script', 'style', 'iframe', 'object', 'embed', 'form', 'base'],
  FORBID_ATTR: ['style'],
  ADD_ATTR: ['target'],
})

export function parseMarkdownDocument(source) {
  const text = String(source || '').replace(/^\uFEFF/, '')
  if (!text.startsWith('---\n')) return { body: text, frontmatter: '' }
  const closing = text.indexOf('\n---\n', 4)
  if (closing < 0 || closing > 16 * 1024) return { body: text, frontmatter: '' }
  return {
    frontmatter: text.slice(4, closing),
    body: text.slice(closing + 5),
  }
}

export const markdownToHtml = source => parser.render(parseMarkdownDocument(source).body)

export function sanitizeMarkdownHtml(html, activePurifier = purifier) {
  if (!activePurifier?.sanitize) throw new Error('Markdown 清洗器不可用')
  return activePurifier.sanitize(html, SANITIZE_OPTIONS)
}

export const renderMarkdown = source => sanitizeMarkdownHtml(markdownToHtml(source))

export function blockRemoteMarkdownImages(root, baseUrl = globalThis.location?.href || 'http://localhost/') {
  for (const image of root?.querySelectorAll?.('img[src]') || []) {
    const raw = image.getAttribute('src') || ''
    let parsed
    try {
      parsed = new URL(raw, baseUrl)
    } catch {
      image.removeAttribute('src')
      continue
    }
    if (parsed.protocol === 'http:' || parsed.protocol === 'https:') {
      image.removeAttribute('src')
      image.setAttribute('data-remote-image-blocked', 'true')
      image.setAttribute('title', '远程图片已阻止，以保护阅读隐私')
    }
  }
}
