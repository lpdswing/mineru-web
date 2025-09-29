<template>
  <div class="settings-root">
    <div class="settings-card">
      <div class="settings-header">系统设置</div>
      <el-form :model="settings" label-width="120px" class="settings-form">
        <el-form-item label="强制开启OCR">
          <el-switch
            v-model="settings.forceOcr"
            active-text="开启"
            inactive-text="关闭"
            :disabled="settings.backend !== 'pipeline'"
          />
          <div v-if="settings.backend !== 'pipeline'" class="settings-tip">
            只有在Pipeline模式下可以设置强制OCR
          </div>
        </el-form-item>
        <el-form-item label="OCR识别语言">
          <el-select v-model="settings.ocrLanguage" class="settings-select">
            <el-option label="中英日繁混合(ch)" value="ch" />
            <el-option label="中英日繁混合+手写场景(ch_server)" value="ch_server" />
            <el-option label="中英日繁混合+手写场景(ch_lite)" value="ch_lite" />
            <el-option label="英语(en)" value="en" />
            <el-option label="韩语(korean)" value="korean" />
            <el-option label="日语(japan)" value="japan" />
            <el-option label="繁体中文(chinese_cht)" value="chinese_cht" />
            <el-option label="泰米尔语(ta)" value="ta" />
            <el-option label="泰卢固语(te)" value="te" />
            <el-option label="格鲁吉亚语(ka)" value="ka" />
            <el-option label="拉丁语(latin)" value="latin" />
            <el-option label="阿拉伯语(arabic)" value="arabic" />
            <el-option label="东斯拉夫语(east_slavic)" value="east_slavic" />
            <el-option label="西里尔语(cyrillic)" value="cyrillic" />
            <el-option label="天城文(devanagari)" value="devanagari" />
          </el-select>
        </el-form-item>
        <el-form-item label="公式识别">
          <el-switch
            v-model="settings.formulaRecognition"
            active-text="开启"
            inactive-text="关闭"
          />
        </el-form-item>
        <el-form-item label="表格识别">
          <el-switch
            v-model="settings.tableRecognition"
            active-text="开启"
            inactive-text="关闭"
          />
        </el-form-item>
        <el-form-item label="后端引擎">
          <el-select v-model="settings.backend" class="settings-select">
            <el-option label="Pipeline" value="pipeline" />
            <!-- <el-option label="VLM Transformers" value="vlm-transformers" /> -->
            <!-- <el-option label="VLM SgLang Engine" value="vlm-sglang-engine" /> -->
            <el-option label="VLM HTTP Client" value="vlm-http-client" />
          </el-select>
        </el-form-item>
        <el-form-item>
          <el-button type="primary" @click="saveSettings" size="large">保存设置</el-button>
          <el-button @click="resetSettings" size="large">重置</el-button>
        </el-form-item>
      </el-form>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted } from 'vue'
import { ElMessage } from 'element-plus'
import axios from 'axios'
import { getUserId } from '@/utils/user'

interface Settings {
  forceOcr: boolean
  ocrLanguage: string
  formulaRecognition: boolean
  tableRecognition: boolean
  version: string
  // backend: 'pipeline' | 'vlm-transformers' | 'vlm-sglang-engine' | 'vlm-sglang-client'
  backend: 'pipeline' | 'vlm-http-client'
}

const defaultSettings: Settings = {
  forceOcr: false,
  ocrLanguage: 'ch',  // 将默认值从'auto'改为'ch'
  formulaRecognition: true,
  tableRecognition: true,
  version: '',
  backend: 'pipeline'
}

const settings = ref<Settings>({ ...defaultSettings })

// 加载设置
const loadSettings = async () => {
  try {
    const response = await axios.get('/api/settings', {
      headers: {
        'X-User-Id': getUserId()
      }
    })

    settings.value = {
      forceOcr: response.data.force_ocr,
      ocrLanguage: response.data.ocr_lang,
      formulaRecognition: response.data.formula_recognition,
      tableRecognition: response.data.table_recognition,
      version: response.data.version || '',
      backend: response.data.backend || 'pipeline'
    }
  } catch (error: any) {
    console.error('加载设置失败:', error.response?.data || error.message)
    ElMessage.error(`加载设置失败: ${error.response?.data?.detail || error.message}`)
  }
}

// 保存设置
const saveSettings = async () => {
  try {
    await axios.put('/api/settings', {
      force_ocr: settings.value.forceOcr,
      ocr_lang: settings.value.ocrLanguage,
      formula_recognition: settings.value.formulaRecognition,
      table_recognition: settings.value.tableRecognition,
      version: settings.value.version,
      backend: settings.value.backend,
      user_id: getUserId()
    }, {
      headers: {
        'X-User-Id': getUserId()
      }
    })

    ElMessage.success('设置已保存')
  } catch (error: any) {
    console.error('保存设置失败:', error.response?.data || error.message)
    ElMessage.error(`保存设置失败: ${error.response?.data?.detail || error.message}`)
  }
}

const resetSettings = () => {
  settings.value = { ...defaultSettings }
  ElMessage.info('设置已重置')
}

// 组件挂载时加载设置
onMounted(() => {
  loadSettings()
})
</script>

<style scoped>
.settings-root {
  width: 100%;
  display: flex;
  justify-content: center;
  align-items: flex-start;
  padding: 32px 0 0 0;
}
.settings-card {
  width: 480px;
  background: #fff;
  border-radius: 18px;
  box-shadow: 0 4px 24px 0 rgba(0,0,0,0.04);
  padding: 36px 36px 24px 36px;
  display: flex;
  flex-direction: column;
  align-items: stretch;
}
.settings-header {
  font-size: 1.3rem;
  font-weight: 600;
  color: #222;
  margin-bottom: 18px;
  text-align: center;
}
.settings-form {
  width: 100%;
}
.settings-select {
  width: 180px;
}
:deep(.el-form-item__content) {
  justify-content: flex-start;
}
.settings-tip {
  font-size: 12px;
  color: #909399;
  margin-top: 4px;
}
</style>