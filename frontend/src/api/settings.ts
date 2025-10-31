import api from './index'

// 设置相关类型定义
export interface SettingsData {
  force_ocr: boolean
  ocr_lang: string
  formula_recognition: boolean
  table_recognition: boolean
  backend: 'pipeline' | 'vlm-http-client'
  version?: string
}

export interface SettingsResponse extends SettingsData {
  user_id: string
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
  updateSettings(settings: SettingsData & { user_id: string }) {
    return api.put('/settings', settings)
      .then(res => res.data)
  }
}
