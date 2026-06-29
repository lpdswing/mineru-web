import api from './index'
import type { AxiosProgressEvent } from 'axios'
import type { FileItem, ExportFormat, FolderItem, MarkdownVariant, PopoStatus, PopoTreeNode, SourceMap } from '@/types/file'

// 文件列表参数
export interface FileListParams {
  page: number
  page_size: number
  search?: string
  status?: string
  folder_id?: string
}

// 文件列表响应
export interface FileListResponse {
  files: FileItem[]
  total: number
}

export interface UploadResponse {
  total: number
  success?: number
  failed?: number
  files: Array<{
    id?: string
    filename: string
    status: string
    file_id?: string
    error_message?: string | null
  }>
}

export interface ExportResponse {
  status: string
  download_url: string
  filename: string
}

export interface DownloadUrlResponse {
  url: string
}

export interface FolderListResponse {
  folders: FolderItem[]
}

// 文件 API
export const filesApi = {
  /**
   * 获取文件列表
   */
  getFiles(params: FileListParams) {
    return api.get<FileListResponse>('/files', { params })
      .then(res => res.data)
  },

  /**
   * 获取文件夹列表
   */
  getFolders() {
    return api.get<FolderListResponse>('/folders')
      .then(res => res.data)
  },

  /**
   * 创建文件夹
   */
  createFolder(name: string) {
    return api.post<FolderItem>('/folders', { name })
      .then(res => res.data)
  },

  /**
   * 重命名文件夹
   */
  renameFolder(folderId: number, name: string) {
    return api.patch<FolderItem>(`/folders/${folderId}`, { name })
      .then(res => res.data)
  },

  /**
   * 删除文件夹
   */
  deleteFolder(folderId: number) {
    return api.delete(`/folders/${folderId}`)
  },

  /**
   * 移动文件到文件夹
   */
  moveFileToFolder(fileId: string, folderId: number | null) {
    return api.patch<FileItem>(`/files/${fileId}/folder`, { folder_id: folderId })
      .then(res => res.data)
  },

  /**
   * 上传文件
   */
  uploadFiles(formData: FormData, onProgress?: (progress: number) => void) {
    return api.post<UploadResponse>('/upload', formData, {
      headers: { 'Content-Type': 'multipart/form-data' },
      onUploadProgress: (progressEvent: AxiosProgressEvent) => {
        if (onProgress && progressEvent.total) {
          const progress = Math.round((progressEvent.loaded * 100) / progressEvent.total)
          onProgress(progress)
        }
      }
    }).then(res => res.data)
  },

  /**
   * 删除文件
   */
  deleteFile(fileId: string) {
    return api.delete(`/files/${fileId}`)
  },

  /**
   * 解析文件
   */
  parseFile(fileId: string) {
    return api.post(`/files/${fileId}/parse`)
  },

  /**
   * 获取解析状态
   */
  getParseStatus(fileId: string) {
    return api.get(`/files/${fileId}/parse/status`)
      .then(res => res.data)
  },

  /**
   * 获取已解析内容
   */
  getParsedContent(fileId: string, variant: MarkdownVariant = 'markdown') {
    return api.get<string>(`/files/${fileId}/parsed_content`, {
      params: { variant }
    })
      .then(res => res.data)
  },

  /**
   * 获取 Popo 处理状态
   */
  getPopoStatus(fileId: string) {
    return api.get<PopoStatus>(`/files/${fileId}/popo/status`)
      .then(res => res.data)
  },

  /**
   * 获取 Popo 文档结构树
   */
  getPopoTree(fileId: string) {
    return api.get<PopoTreeNode>(`/files/${fileId}/popo/tree`)
      .then(res => res.data)
  },

  /**
   * 获取 PDF 溯源信息
   */
  getSourceMap(fileId: string) {
    return api.get<SourceMap>(`/files/${fileId}/source_map`)
      .then(res => res.data)
  },

  /**
   * 导出文件
   */
  exportFile(fileId: string, format: ExportFormat) {
    return api.get<ExportResponse>(`/files/${fileId}/export`, {
      params: { format }
    }).then(res => res.data)
  },

  /**
   * 获取文件下载URL
   */
  getDownloadUrl(fileId: string) {
    return api.get<DownloadUrlResponse>(`/files/${fileId}/download_url`)
      .then(res => res.data)
  },

  /**
   * 获取同源预览地址
   */
  getContentUrl(fileId: string) {
    return `/api/files/${fileId}/content`
  }
}
