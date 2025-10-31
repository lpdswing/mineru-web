// 文件状态枚举
export type FileStatus = 'pending' | 'parsing' | 'parsed' | 'parse_failed'

// 后端类型枚举
export type BackendType = 'pipeline' | 'vlm'

// 文件项接口
export interface FileItem {
  id: string
  filename: string
  size: number
  upload_time: string
  start_at?: string
  finish_at?: string
  status: FileStatus
  backend?: BackendType
}

// 导出格式类型
export const ExportFormats = {
  MARKDOWN: 'markdown',
  MARKDOWN_PAGE: 'markdown_page'
} as const

export type ExportFormat = typeof ExportFormats[keyof typeof ExportFormats]

// 导出格式显示名称
export const ExportFormatNames: Record<ExportFormat, string> = {
  [ExportFormats.MARKDOWN]: 'Markdown',
  [ExportFormats.MARKDOWN_PAGE]: 'Markdown带页码'
}
