// 文件状态映射
export const FileStatusMap = {
  pending: { text: '等待解析', type: 'info' as const },
  parsing: { text: '解析中', type: 'warning' as const },
  parsed: { text: '已完成', type: 'success' as const },
  parse_failed: { text: '解析失败', type: 'danger' as const }
} as const

// 上传状态映射
export const UploadStatusMap = {
  waiting: { text: '等待上传', type: 'info' as const },
  uploading: { text: '上传中', type: 'warning' as const },
  success: { text: '上传成功', type: 'success' as const },
  error: { text: '上传失败', type: 'danger' as const }
} as const

/**
 * 获取文件状态信息
 */
export function getFileStatusInfo(status: string) {
  return FileStatusMap[status as keyof typeof FileStatusMap] || { text: '未知状态', type: 'info' as const }
}

/**
 * 获取文件状态显示文本
 */
export function getFileStatusText(status: string): string {
  return getFileStatusInfo(status).text
}

/**
 * 获取文件状态类型
 */
export function getFileStatusType(status: string): string {
  return getFileStatusInfo(status).type
}

/**
 * 获取上传状态信息
 */
export function getUploadStatusInfo(status: string) {
  return UploadStatusMap[status as keyof typeof UploadStatusMap] || { text: '未知状态', type: 'info' as const }
}

/**
 * 获取上传状态显示文本
 */
export function getUploadStatusText(status: string): string {
  return getUploadStatusInfo(status).text
}

/**
 * 获取上传状态类型
 */
export function getUploadStatusType(status: string): string {
  return getUploadStatusInfo(status).type
}

// 后端配置映射
export const BackendConfig = {
  pipeline: { icon: 'Pipeline', color: '#409EFF' },
  vlm: { icon: 'VLM', color: '#67C23A' }
} as const

/**
 * 获取后端信息
 */
export function getBackendInfo(backend?: string) {
  return BackendConfig[backend as keyof typeof BackendConfig] || { icon: '', color: '#909399' }
}

/**
 * 获取后端图标
 */
export function getBackendIcon(backend?: string): string {
  return getBackendInfo(backend).icon
}

/**
 * 获取后端颜色
 */
export function getBackendColor(backend?: string): string {
  return getBackendInfo(backend).color
}

/**
 * 格式化日期时间
 */
export function formatDateTime(dateStr: string): string {
  if (!dateStr) return ''
  const date = new Date(dateStr)
  return date.toLocaleString('zh-CN', {
    year: 'numeric',
    month: '2-digit',
    day: '2-digit',
    hour: '2-digit',
    minute: '2-digit',
    second: '2-digit',
    hour12: false
  })
}
