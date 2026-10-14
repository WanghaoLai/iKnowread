import defaultAvatar from '@/assets/imgs/logo.png'

// 文件相对路径 → 完整可访问地址
// 后端/数据库统一存相对路径（如 files/download/xxx.png），换域名、端口、存储后端时数据无需变更
export const DEFAULT_AVATAR = defaultAvatar

export function fileUrl(path) {
  if (!path) return ''
  // 已是完整地址（兼容历史数据）原样返回
  if (/^https?:\/\//i.test(path)) return path
  const base = (import.meta.env.VITE_BASE_URL || '').replace(/\/$/, '')
  return base + '/' + path.replace(/^\//, '')
}
