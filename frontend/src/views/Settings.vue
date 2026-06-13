<template>
  <div class="settings-root">
    <div class="settings-container">
      <!-- 页面头部 -->
      <div class="page-header">
        <div class="header-icon">
          <el-icon :size="24"><Setting /></el-icon>
        </div>
        <div class="header-text">
          <h1 class="page-title">系统设置</h1>
          <p class="page-subtitle">配置文档解析参数</p>
        </div>
      </div>

      <!-- 设置表单 -->
      <div class="settings-card">
        <el-form :model="settings" label-position="top" class="settings-form">
          <!-- OCR设置组 -->
          <div class="form-section">
            <div class="section-title">
              <el-icon><View /></el-icon>
              <span>OCR 设置</span>
            </div>
            
            <div class="form-grid">
              <el-form-item label="强制开启OCR">
                <div class="switch-wrapper">
                  <el-switch
                    v-model="settings.forceOcr"
                    :disabled="!supportsParseMethod"
                  />
                  <span class="switch-label">{{ settings.forceOcr ? '已开启' : '已关闭' }}</span>
                </div>
                <div v-if="!supportsParseMethod" class="form-tip">
                  <el-icon><InfoFilled /></el-icon>
                  <span>仅 Pipeline / Hybrid 模式支持此选项</span>
                </div>
              </el-form-item>

              <el-form-item label="OCR识别语言">
                <el-select v-model="settings.ocrLanguage" class="full-width">
                  <el-option label="中英日繁混合 (ch)" value="ch" />
                  <el-option label="中英日繁混合+手写 (ch_server)" value="ch_server" />
                  <el-option label="中英日繁混合+手写 (ch_lite)" value="ch_lite" />
                  <el-option label="英语 (en)" value="en" />
                  <el-option label="韩语 (korean)" value="korean" />
                  <el-option label="日语 (japan)" value="japan" />
                  <el-option label="繁体中文 (chinese_cht)" value="chinese_cht" />
                  <el-option label="泰米尔语 (ta)" value="ta" />
                  <el-option label="泰卢固语 (te)" value="te" />
                  <el-option label="格鲁吉亚语 (ka)" value="ka" />
                  <el-option label="拉丁语 (latin)" value="latin" />
                  <el-option label="阿拉伯语 (arabic)" value="arabic" />
                  <el-option label="东斯拉夫语 (east_slavic)" value="east_slavic" />
                  <el-option label="西里尔语 (cyrillic)" value="cyrillic" />
                  <el-option label="天城文 (devanagari)" value="devanagari" />
                </el-select>
              </el-form-item>
            </div>
          </div>

          <!-- 识别功能组 -->
          <div class="form-section">
            <div class="section-title">
              <el-icon><Document /></el-icon>
              <span>识别功能</span>
            </div>
            
            <div class="form-grid">
              <el-form-item label="公式识别">
                <div class="switch-wrapper">
                  <el-switch v-model="settings.formulaRecognition" />
                  <span class="switch-label">{{ settings.formulaRecognition ? '已开启' : '已关闭' }}</span>
                </div>
              </el-form-item>

              <el-form-item label="表格识别">
                <div class="switch-wrapper">
                  <el-switch v-model="settings.tableRecognition" />
                  <span class="switch-label">{{ settings.tableRecognition ? '已开启' : '已关闭' }}</span>
                </div>
              </el-form-item>
            </div>
          </div>

          <!-- 引擎设置组 -->
          <div class="form-section">
            <div class="section-title">
              <el-icon><Cpu /></el-icon>
              <span>后端引擎</span>
            </div>
            
            <el-form-item label="选择引擎">
              <el-select v-model="settings.backend" class="full-width">
                <el-option label="Pipeline" value="pipeline" />
                <el-option label="VLM Engine" value="vlm-engine" />
                <el-option label="VLM HTTP Client" value="vlm-http-client" />
                <el-option label="Hybrid Engine" value="hybrid-engine" />
                <el-option label="Hybrid HTTP Client" value="hybrid-http-client" />
              </el-select>
            </el-form-item>
          </div>

          <div class="form-section">
            <div class="section-title">
              <el-icon><Connection /></el-icon>
              <span>解析服务状态</span>
              <el-button
                class="section-action"
                type="primary"
                link
                :loading="healthLoading"
                @click="loadMineruHealth"
              >
                刷新
              </el-button>
            </div>

            <div v-if="healthLoading && !mineruHealth" class="loading-state">
              <el-icon class="is-loading"><RefreshRight /></el-icon>
              <span>正在检查解析服务...</span>
            </div>
            <div v-else-if="mineruHealth" class="health-grid">
              <div class="health-row">
                <span class="health-label">服务地址</span>
                <span class="health-value">{{ mineruHealth.base_url || '-' }}</span>
              </div>
              <div class="health-row">
                <span class="health-label">状态</span>
                <el-tag :type="mineruHealth.available ? 'success' : 'danger'">
                  {{ mineruHealth.available ? '可用' : '不可用' }}
                </el-tag>
              </div>
              <div v-if="mineruHealth.version" class="health-row">
                <span class="health-label">MinerU 版本</span>
                <span class="health-value">{{ mineruHealth.version }}</span>
              </div>
              <div v-if="mineruHealth.error" class="health-row">
                <span class="health-label">错误</span>
                <span class="health-value error">{{ mineruHealth.error }}</span>
              </div>
            </div>
          </div>

          <!-- 操作按钮 -->
          <div class="form-actions">
            <el-button @click="resetSettings" size="large" :disabled="savingSettings">
              <el-icon><RefreshRight /></el-icon>
              <span>重置</span>
            </el-button>
            <el-button type="primary" @click="saveSettings" size="large" :loading="savingSettings">
              <el-icon><Check /></el-icon>
              <span>保存设置</span>
            </el-button>
          </div>
        </el-form>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed, ref, onMounted } from 'vue'
import { ElMessage } from 'element-plus'
import { Setting, View, Document, Cpu, InfoFilled, RefreshRight, Check, Connection } from '@element-plus/icons-vue'
import { settingsApi } from '@/api/settings'
import type { MineruBackend, MineruHealthResponse } from '@/api/settings'

interface Settings {
  forceOcr: boolean
  ocrLanguage: string
  formulaRecognition: boolean
  tableRecognition: boolean
  version: string
  backend: MineruBackend
}

const defaultSettings: Settings = {
  forceOcr: false,
  ocrLanguage: 'ch',
  formulaRecognition: true,
  tableRecognition: true,
  version: '',
  backend: 'pipeline'
}

const settings = ref<Settings>({ ...defaultSettings })
const mineruHealth = ref<MineruHealthResponse | null>(null)
const savingSettings = ref(false)
const healthLoading = ref(false)
const supportsParseMethod = computed(() => {
  return settings.value.backend === 'pipeline' || settings.value.backend.startsWith('hybrid-')
})

const loadSettings = async () => {
  try {
    const data = await settingsApi.getSettings()
    settings.value = {
      forceOcr: data.force_ocr,
      ocrLanguage: data.ocr_lang,
      formulaRecognition: data.formula_recognition,
      tableRecognition: data.table_recognition,
      version: data.version || '',
      backend: data.backend || 'pipeline'
    }
  } catch (error) {
    ElMessage.error('加载设置失败')
  }
}

const saveSettings = async () => {
  savingSettings.value = true
  try {
    await settingsApi.updateSettings({
      force_ocr: settings.value.forceOcr,
      ocr_lang: settings.value.ocrLanguage,
      formula_recognition: settings.value.formulaRecognition,
      table_recognition: settings.value.tableRecognition,
      version: settings.value.version,
      backend: settings.value.backend
    })
    ElMessage.success('设置已保存')
  } catch (error) {
    ElMessage.error('保存设置失败')
  } finally {
    savingSettings.value = false
  }
}

const resetSettings = () => {
  settings.value = { ...defaultSettings }
  ElMessage.info('设置已重置')
}

const loadMineruHealth = async () => {
  healthLoading.value = true
  try {
    mineruHealth.value = await settingsApi.getMineruHealth()
  } catch (error) {
    mineruHealth.value = {
      available: false,
      base_url: '',
      error: '无法获取 MinerU API 状态'
    }
  } finally {
    healthLoading.value = false
  }
}

onMounted(() => {
  loadSettings()
  loadMineruHealth()
})
</script>

<style scoped>
.settings-root {
  width: 100%;
  display: flex;
  justify-content: center;
  padding: 20px;
  animation: fadeIn 0.3s ease;
  height: 100%;
  overflow: auto;
}

.settings-container {
  width: 100%;
  max-width: 560px;
  display: flex;
  flex-direction: column;
  gap: 20px;
}

.page-header {
  display: flex;
  align-items: center;
  gap: 14px;
}

.header-icon {
  width: 48px;
  height: 48px;
  border-radius: var(--radius-lg);
  background: var(--primary-gradient);
  display: flex;
  align-items: center;
  justify-content: center;
  color: white;
  flex-shrink: 0;
}

.header-text {
  flex: 1;
}

.page-title {
  font-size: 1.5rem;
  font-weight: 700;
  color: var(--text-primary);
  margin: 0 0 4px;
}

.page-subtitle {
  font-size: 14px;
  color: var(--text-muted);
  margin: 0;
}

.settings-card {
  background: var(--bg-primary);
  border-radius: var(--radius-xl);
  box-shadow: var(--shadow-md);
  padding: 24px;
}

.settings-form {
  display: flex;
  flex-direction: column;
  gap: 24px;
}

.form-section {
  display: flex;
  flex-direction: column;
  gap: 16px;
}

.section-title {
  display: flex;
  align-items: center;
  gap: 8px;
  font-size: 14px;
  font-weight: 600;
  color: var(--text-primary);
  padding-bottom: 10px;
  border-bottom: 1px solid var(--border-light);
}

.section-action {
  margin-left: auto;
}

.form-grid {
  display: grid;
  grid-template-columns: repeat(2, 1fr);
  gap: 16px;
}

.settings-form :deep(.el-form-item) {
  margin-bottom: 0;
}

.settings-form :deep(.el-form-item__label) {
  font-weight: 500;
  color: var(--text-secondary);
  padding-bottom: 6px;
  font-size: 13px;
}

.full-width {
  width: 100%;
}

.switch-wrapper {
  display: flex;
  align-items: center;
  gap: 12px;
}

.switch-label {
  font-size: 13px;
  color: var(--text-muted);
}

.form-tip {
  display: flex;
  align-items: center;
  gap: 6px;
  margin-top: 8px;
  font-size: 12px;
  color: var(--text-muted);
}

.loading-state {
  display: flex;
  align-items: center;
  gap: 8px;
  font-size: 13px;
  color: var(--text-muted);
  min-height: 28px;
}

.health-grid {
  display: grid;
  gap: 10px;
  padding: 2px 0;
}

.health-row {
  display: grid;
  grid-template-columns: 88px minmax(0, 1fr);
  align-items: center;
  gap: 12px;
  min-height: 28px;
}

.health-label {
  color: var(--text-muted);
  font-size: 13px;
}

.health-value {
  color: var(--text-secondary);
  font-size: 13px;
  overflow-wrap: anywhere;
}

.health-value.error {
  color: var(--danger-color);
}

.form-actions {
  display: flex;
  justify-content: flex-end;
  gap: 12px;
  padding-top: 12px;
  border-top: 1px solid var(--border-light);
}

@media (max-width: 768px) {
  .settings-root {
    padding: 20px 16px;
  }
  
  .settings-card {
    padding: 24px 20px;
  }
  
  .form-grid {
    grid-template-columns: 1fr;
  }
  
  .form-actions {
    flex-direction: column;
  }
  
  .form-actions .el-button {
    width: 100%;
  }
}
</style>
