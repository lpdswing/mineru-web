import api from './index'
import type { AxiosProgressEvent } from 'axios'
import type { FileItem, ExportFormat } from '@/types/file'

// 文件列表参数
export interface FileListParams {
  page: number
  page_size: number
  search?: string
  status?: string
}

// 文件列表响应
export interface FileListResponse {
  files: FileItem[]
  total: number
}

export interface UploadResponse {
  total: number
  success: number
  failed: number
  files: Array<{
    filename: string
    status: string
    file_id?: string
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
  getParsedContent(fileId: string) {
    return api.get(`/files/${fileId}/parsed_content`)
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
  }
}
