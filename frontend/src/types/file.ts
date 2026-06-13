// 文件状态枚举
export type FileStatus = 'pending' | 'parsing' | 'parsed' | 'parse_failed'

// 后端类型枚举
export type BackendType =
  | 'pipeline'
  | 'vlm-auto-engine'
  | 'vlm-http-client'
  | 'hybrid-auto-engine'
  | 'hybrid-http-client'
  | 'vlm'
  | 'hybrid'
  | (string & {})

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
  error_message?: string | null
}

// 导出格式类型
export const ExportFormats = {
  MARKDOWN: 'markdown',
  MARKDOWN_PAGE: 'markdown_page',
  MARKDOWN_POPO: 'markdown_popo'
} as const

export type ExportFormat = typeof ExportFormats[keyof typeof ExportFormats]
export type MarkdownVariant = 'markdown' | 'markdown_page' | 'popo'
export type PopoStatusValue = 'not_available' | 'processing' | 'success' | 'failed' | 'skipped'

export interface PopoStatus {
  status: PopoStatusValue
  message?: string
}

export interface SourceBlock {
  id: string
  type: string
  text: string
  bbox: [number, number, number, number]
}

export interface SourcePage {
  page: number
  page_idx: number
  width: number | null
  height: number | null
  blocks: SourceBlock[]
}

export interface SourceMap {
  pages: SourcePage[]
}

// 导出格式显示名称
export const ExportFormatNames: Record<ExportFormat, string> = {
  [ExportFormats.MARKDOWN]: 'Markdown',
  [ExportFormats.MARKDOWN_PAGE]: 'Markdown带页码',
  [ExportFormats.MARKDOWN_POPO]: 'Popo Markdown'
}
