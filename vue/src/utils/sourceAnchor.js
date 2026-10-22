export const SOURCE_ANCHOR_PROTOCOL = 'iknowread.source-anchor/v1'

// position 使用浏览器 DOM 的 UTF-16 文本偏移；跳转时先核对偏移处原文，
// 不匹配再用 exact + 前后文消歧，避免排版节点变化导致误跳。

const PENDING_ANCHOR_KEY = 'iknowread:pending-source-anchor'
const clampProgression = value => Math.max(0, Math.min(1, Number(value) || 0))

export function isSourceAnchor(anchor) {
  if (!anchor || anchor.protocol !== SOURCE_ANCHOR_PROTOCOL) return false
  if (!Number.isInteger(Number(anchor.document_id)) || Number(anchor.document_id) < 1) return false
  if (!/^[0-9a-f]{32}$/.test(anchor.document_version || '')) return false
  if (!['pdf', 'docx', 'md'].includes(anchor.source_format)) return false
  if (!Number.isFinite(anchor.progression) || anchor.progression < 0 || anchor.progression > 1) return false
  if (anchor.source_format === 'pdf') {
    if (anchor.scope !== 'page' || !Number.isInteger(anchor.page) || anchor.page < 1) return false
  } else if (anchor.scope !== 'document' || anchor.page !== null) return false
  if (anchor.selector) {
    const { position, quote } = anchor.selector
    if (!position || !Number.isInteger(position.start) || !Number.isInteger(position.end)) return false
    if (position.start < 0 || position.end <= position.start || typeof quote?.exact !== 'string' || !quote.exact) return false
  }
  return true
}

export function createPointAnchor(model, { page = null, progression = 0 } = {}) {
  const sourceFormat = String(model.sourceFormat || '').toLowerCase()
  const anchor = {
    protocol: SOURCE_ANCHOR_PROTOCOL,
    document_id: Number(model.id),
    document_version: model.contentVersion || '',
    source_format: sourceFormat,
    scope: sourceFormat === 'pdf' ? 'page' : 'document',
    page: sourceFormat === 'pdf' ? Math.max(1, Number(page) || 1) : null,
    progression: clampProgression(progression),
    selector: null,
  }
  return isSourceAnchor(anchor) ? anchor : null
}

export function createTextAnchor(model, {
  page = null, progression = 0, start, end, exact, prefix = '', suffix = '',
}) {
  const anchor = createPointAnchor(model, { page, progression })
  if (!anchor) return null
  anchor.selector = {
    position: { start: Number(start), end: Number(end) },
    quote: { exact: String(exact), prefix: String(prefix), suffix: String(suffix) },
  }
  return isSourceAnchor(anchor) ? anchor : null
}

export function anchorFromRange(model, range, scopeElement, { page = null, progression = 0 } = {}) {
  if (!range || !scopeElement || !scopeElement.contains(range.commonAncestorContainer)) return null
  const before = document.createRange()
  before.selectNodeContents(scopeElement)
  before.setEnd(range.startContainer, range.startOffset)
  const start = before.toString().length
  const exact = range.toString()
  const scopeText = scopeElement.textContent || ''
  return createTextAnchor(model, {
    page,
    progression,
    start,
    end: start + exact.length,
    exact,
    prefix: scopeText.slice(Math.max(0, start - 80), start),
    suffix: scopeText.slice(start + exact.length, start + exact.length + 80),
  })
}

function textNodes(root) {
  const nodes = []
  const walker = document.createTreeWalker(root, NodeFilter.SHOW_TEXT)
  while (walker.nextNode()) nodes.push(walker.currentNode)
  return nodes
}

function rangeAtOffsets(root, start, end) {
  const nodes = textNodes(root)
  let consumed = 0
  let startNode = null
  let startOffset = 0
  let endNode = null
  let endOffset = 0
  for (const node of nodes) {
    const next = consumed + (node.nodeValue || '').length
    if (!startNode && start >= consumed && start <= next) {
      startNode = node
      startOffset = start - consumed
    }
    if (endNode === null && end >= consumed && end <= next) {
      endNode = node
      endOffset = end - consumed
      break
    }
    consumed = next
  }
  if (!startNode || !endNode) return null
  const range = document.createRange()
  range.setStart(startNode, startOffset)
  range.setEnd(endNode, endOffset)
  return range
}

export function resolveAnchorRange(scopeElement, anchor) {
  if (!scopeElement || !isSourceAnchor(anchor) || !anchor.selector) return null
  const text = scopeElement.textContent || ''
  const { position, quote } = anchor.selector
  if (text.slice(position.start, position.end) === quote.exact) {
    return rangeAtOffsets(scopeElement, position.start, position.end)
  }

  let best = null
  let from = 0
  while (from <= text.length) {
    const index = text.indexOf(quote.exact, from)
    if (index < 0) break
    let score = 0
    if (quote.prefix && text.slice(Math.max(0, index - quote.prefix.length), index) === quote.prefix) score += 2
    if (quote.suffix && text.slice(index + quote.exact.length, index + quote.exact.length + quote.suffix.length) === quote.suffix) score += 2
    score -= Math.min(Math.abs(index - position.start) / 10000, 1)
    if (!best || score > best.score) best = { index, score }
    from = index + Math.max(1, quote.exact.length)
  }
  return best ? rangeAtOffsets(scopeElement, best.index, best.index + quote.exact.length) : null
}

export function readingProgressKey(anchor) {
  return anchor && isSourceAnchor(anchor)
    ? `iknowread:reading-progress:${anchor.document_id}:${anchor.document_version}`
    : ''
}

export function saveReadingProgress(anchor) {
  const key = readingProgressKey(anchor)
  if (!key) return
  try { localStorage.setItem(key, JSON.stringify(anchor)) } catch (_) {}
}

export function loadReadingProgress(model) {
  const point = createPointAnchor(model, { page: 1 })
  const key = readingProgressKey(point)
  if (!key) return null
  try {
    const anchor = JSON.parse(localStorage.getItem(key) || 'null')
    return isSourceAnchor(anchor) ? anchor : null
  } catch (_) {
    return null
  }
}

export function queueSourceNavigation(anchor) {
  if (!isSourceAnchor(anchor)) return false
  try {
    sessionStorage.setItem(PENDING_ANCHOR_KEY, JSON.stringify(anchor))
    return true
  } catch (_) {
    return false
  }
}

export function consumeSourceNavigation() {
  try {
    const anchor = JSON.parse(sessionStorage.getItem(PENDING_ANCHOR_KEY) || 'null')
    sessionStorage.removeItem(PENDING_ANCHOR_KEY)
    return isSourceAnchor(anchor) ? anchor : null
  } catch (_) {
    sessionStorage.removeItem(PENDING_ANCHOR_KEY)
    return null
  }
}

export function navigateToSource(router, anchor) {
  if (!queueSourceNavigation(anchor)) return false
  router.push({ path: '/manager/reader', query: { documentId: anchor.document_id } })
  return true
}
