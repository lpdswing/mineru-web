import api from './index'

export type MineruBackend =
  | 'pipeline'
  | 'vlm-engine'
  | 'vlm-http-client'
  | 'hybrid-engine'
  | 'hybrid-http-client'
  | (string & {})

// 设置相关类型定义
export interface SettingsData {
  force_ocr: boolean
  ocr_lang: string
  formula_recognition: boolean
  table_recognition: boolean
  backend: MineruBackend
  version?: string
}

export interface SettingsResponse extends SettingsData {
  user_id: string
}

export interface MineruHealthResponse {
  available: boolean
  base_url: string
  status?: string
  version?: string
  error?: string
  [key: string]: unknown
}

// 设置 API
export const settingsApi = {
  /**
   * 获取用户设置
   */
  getSettings() {
    return api.get<SettingsResponse>('/settings')
      .then(res => res.data)
  },

  /**
   * 更新用户设置
   */
  updateSettings(settings: SettingsData) {
    return api.put('/settings', settings)
      .then(res => res.data)
  },

  getMineruHealth() {
    return api.get<MineruHealthResponse>('/system/mineru-health')
      .then(res => res.data)
  }
}
