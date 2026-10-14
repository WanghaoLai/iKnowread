// 统一文档语义模型 + 预览适配器注册表（Adapter 模式）
//
// 语义模型: { id, title, sourceFormat, engine, url, ocrStatus, ocrError, ocrUpdatedAt }
// 引擎: pdfjs（PDF.js 画布渲染）| docx（docx-preview 浏览器原生渲染）
// 当前支持范围: PDF、DOCX。
const BASE = import.meta.env.VITE_BASE_URL || ''

const ADAPTERS = {
  pdf: { engine: 'pdfjs', source: id => `${BASE}/document/preview/${id}` },
  docx: { engine: 'docx', source: id => `${BASE}/document/download/${id}` },
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
    ocrStatus: row.ocr_status || (ext === 'pdf' ? 'pending' : 'not_applicable'),
    ocrError: row.ocr_error || '',
    ocrUpdatedAt: row.ocr_updated_at || '',
  }
}

export async function fetchBytes(url, options = {}) {
  const res = await fetch(url, { credentials: 'include', signal: options.signal })
  const ct = res.headers.get('content-type') || ''
  if (ct.includes('application/json')) {
    const j = await res.json().catch(() => ({}))
    throw new Error(j.msg || '预览失败')
  }
  if (!res.ok) throw new Error(`预览失败（${res.status}）`)
  return await res.arrayBuffer()
}
