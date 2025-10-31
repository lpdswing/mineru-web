import api from './index'

export interface StatsResponse {
  totalFiles: number
  todayUploads: number
  usedSpace: number
  recentFiles: Array<{
    id: string
    name: string
    size: number
    uploadTime: string
    status: string
  }>
}

export const statsApi = {
  /**
   * 获取统计数据
   */
  getStats() {
    return api.get<StatsResponse>('/stats')
      .then(response => response.data)
  }
} 