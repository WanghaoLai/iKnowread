// 统一文档语义模型 + 预览适配器注册表（Adapter 模式）
//
// 语义模型: { id, title, sourceFormat, engine, url, contentVersion, ocrStatus, ocrError }
// 引擎: pdfjs（PDF.js 画布渲染）| docx（docx-preview）| markdown（安全 HTML）
// 当前支持范围: PDF、DOCX、Markdown。
import { documentDownloadUrl, documentPreviewUrl } from '../api/documentPaths.js'

const ADAPTERS = {
  pdf: { engine: 'pdfjs', source: documentPreviewUrl },
  docx: { engine: 'docx', source: documentDownloadUrl },
  md: { engine: 'markdown', source: documentDownloadUrl },
}

export function buildPreviewModel(row) {
  const ext = (row.ext || '').toLowerCase()
  const adapter = ADAPTERS[ext]
  if (!adapter) return null
  return {
    id: row.id,
    title: row.name,
    sourceFormat: ext,
    engine: adapter.engine,
    url: adapter.source(row.id),
    contentVersion: row.content_version || '',
    ocrStatus: row.ocr_status || (ext === 'pdf' ? 'pending' : 'not_applicable'),
    ocrError: row.ocr_error || '',
    ocrUpdatedAt: row.ocr_updated_at || '',
    sourceType: row.source_type || 'local',
    sourceUrl: row.source_url || '',
    sourceTitle: row.source_title || '',
    sourceFetchedAt: row.source_fetched_at || '',
    readOnly: Boolean(row.read_only),
  }
}

async function fetchDocument(url, options = {}) {
  const res = await fetch(url, { credentials: 'include', signal: options.signal })
  const ct = res.headers.get('content-type') || ''
  if (ct.includes('application/json')) {
    const j = await res.json().catch(() => ({}))
    throw new Error(j.msg || '预览失败')
  }
  if (!res.ok) throw new Error(`预览失败（${res.status}）`)
  return res
}

export async function fetchBytes(url, options = {}) {
  return await (await fetchDocument(url, options)).arrayBuffer()
}

export async function fetchText(url, options = {}) {
  const text = await (await fetchDocument(url, options)).text()
  return text.replace(/^\uFEFF/, '')
}
