// 文件状态枚举
export type FileStatus = 'pending' | 'parsing' | 'parsed' | 'parse_failed'

// 后端类型枚举
export type BackendType =
  | 'pipeline'
  | 'vlm-engine'
  | 'vlm-http-client'
  | 'hybrid-engine'
  | 'hybrid-http-client'
  | 'vlm'
  | 'hybrid'
  | (string & {})

// 文件项接口
export interface FileItem {
  id: string
  folder_id?: number | null
  filename: string
  size: number
  upload_time: string
  start_at?: string
  finish_at?: string
  status: FileStatus
  backend?: BackendType
  error_message?: string | null
  parse_stage?: string | null
  progress_percent?: number | null
  progress_message?: string | null
  last_heartbeat_at?: string | null
  mineru_task_id?: string | null
  mineru_task_status?: string | null
}

export interface FolderItem {
  id: number
  user_id: string
  name: string
  created_at?: string | null
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

// Popo 后处理生成的文档结构树节点
export interface PopoTreeNode {
  type: string
  title?: string
  metadata?: string
  content?: string
  level?: number
  location?: Array<{ bbox?: number[]; page?: number }>
  block_ids?: number[]
  children?: PopoTreeNode[]
}

// 导出格式显示名称
export const ExportFormatNames: Record<ExportFormat, string> = {
  [ExportFormats.MARKDOWN]: 'Markdown',
  [ExportFormats.MARKDOWN_PAGE]: 'Markdown带页码',
  [ExportFormats.MARKDOWN_POPO]: 'Popo Markdown'
}

// 识别结果 Markdown 编辑历史版本
export type ParsedContentVersionSource = 'parse' | 'save' | 'restore'

export interface ParsedContentVersion {
  id: number
  version: number
  note?: string | null
  source: ParsedContentVersionSource
  created_at: string
  is_current: boolean
}

export interface ParsedContentVersionDetail extends ParsedContentVersion {
  content: string
}

export interface SaveParsedContentResult {
  changed: boolean
  version: number
  /** 数据库已提交；对象存储同步是否成功。false 时 sync_error 有值 */
  synced?: boolean
  sync_error?: string | null
}

export interface RestoreParsedContentResult {
  restored: boolean
  version: number
  synced?: boolean
  sync_error?: string | null
}
