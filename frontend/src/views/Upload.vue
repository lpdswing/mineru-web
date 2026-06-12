<template>
  <div class="upload-root">
    <div class="upload-container">
      <!-- 页面头部 -->
      <div class="page-header">
        <div class="header-left">
          <h1 class="page-title">上传文档</h1>
          <span class="page-subtitle">支持拖拽或点击上传</span>
        </div>
      </div>

      <!-- 上传区域 -->
      <div class="upload-zone">
        <el-upload
          ref="uploadRef"
          class="upload-dragger"
          drag
          action="/api/upload"
          :auto-upload="false"
          :on-change="handleFileChange"
          :on-remove="handleFileRemove"
          :before-upload="beforeUpload"
          accept=".pdf,.docx,.pptx,.xlsx,.png,.jpeg,.jp2,.webp,.gif,.bmp,.jpg,.tiff"
          multiple
          :limit="20"
          :disabled="uploading"
          :show-file-list="false"
        >
          <div class="upload-content">
            <div class="upload-icon-wrapper">
              <el-icon class="upload-icon" :size="48"><UploadFilled /></el-icon>
            </div>
            <div class="upload-text">
              <p class="upload-main-text">拖拽文件到此处，或 <span class="upload-link">点击上传</span></p>
              <p class="upload-hint">支持 PDF、DOCX、PPTX、XLSX、PNG、JPG、JPEG、JP2、WEBP、GIF、BMP、TIFF</p>
            </div>
          </div>
        </el-upload>
      </div>

      <!-- 文件列表 -->
      <div class="file-list-section" v-if="fileList.length > 0">
        <div class="section-header">
          <div class="section-title">
            <el-icon><Document /></el-icon>
            <span>待上传文件</span>
            <span class="file-count-badge">{{ fileList.length }}</span>
          </div>
          <el-button 
            type="primary" 
            @click="handleUpload" 
            :loading="uploading" 
            :disabled="uploading || pendingUploadCount === 0"
          >
            <el-icon v-if="!uploading"><UploadFilled /></el-icon>
            <span>{{ uploadButtonText }}</span>
          </el-button>
        </div>

        <div v-if="uploading || uploadProgress > 0" class="upload-progress">
          <el-progress :percentage="uploadProgress" :status="uploadProgressStatus" />
        </div>

        <div v-if="uploadResultMessage && !uploading" class="upload-result">
          <span>{{ uploadResultMessage }}</span>
          <el-button type="primary" link @click="router.push('/files')">查看文件</el-button>
        </div>

        <div class="file-list">
          <div 
            v-for="(file, index) in fileList" 
            :key="index" 
            class="file-item"
            :class="{ 'file-uploading': file.status === 'uploading' }"
          >
            <div class="file-icon">
              <el-icon :size="24"><Document /></el-icon>
            </div>
            <div class="file-info">
              <div class="file-name">{{ file.name }}</div>
              <div class="file-meta">
                <span class="file-size">{{ formatFileSize(file.size) }}</span>
                <span class="file-status" :class="getStatusClass(file.status)">
                  {{ getUploadStatusText(file.status) }}
                </span>
                <span v-if="file.message" class="file-message">{{ file.message }}</span>
              </div>
            </div>
            <el-button 
              type="danger" 
              link 
              class="file-remove"
              @click="handleFileRemove(file, index)"
              :disabled="file.status === 'uploading' || uploading"
            >
              <el-icon><Close /></el-icon>
            </el-button>
          </div>
        </div>
      </div>

      <!-- 空状态 -->
      <div v-else class="empty-state">
        <el-empty description="暂无待上传文件" :image-size="120">
          <template #description>
            <p class="empty-text">拖拽或点击上方区域选择文件</p>
          </template>
        </el-empty>
      </div>

      <!-- 限制说明 -->
      <div class="limits-info">
        <div class="limit-item">
          <el-icon><InfoFilled /></el-icon>
          <span>单个文档 ≤ 200MB 或 600页</span>
        </div>
        <div class="limit-item">
          <el-icon><InfoFilled /></el-icon>
          <span>单张图片 ≤ 10MB</span>
        </div>
        <div class="limit-item">
          <el-icon><InfoFilled /></el-icon>
          <span>单次最多 20 个文件</span>
        </div>
      </div>
    </div>

  </div>
</template>

<script setup lang="ts">
import { computed, ref } from 'vue'
import { UploadFilled, Document, Close, InfoFilled } from '@element-plus/icons-vue'
import { ElMessage } from 'element-plus'
import type { UploadInstance } from 'element-plus'
import { useRouter } from 'vue-router'
import { filesApi } from '@/api/files'
import { formatFileSize } from '@/utils/format'
import { getUploadStatusText } from '@/utils/status'

interface UploadFile {
  name: string
  size: number
  status: 'waiting' | 'uploading' | 'success' | 'error'
  raw?: File
  url?: string
  message?: string
}

const fileList = ref<UploadFile[]>([])
const uploading = ref(false)
const uploadProgress = ref(0)
const uploadResultMessage = ref('')
const uploadRef = ref<UploadInstance>()
const router = useRouter()

const pendingUploadCount = computed(() => fileList.value.filter(file => file.status !== 'success').length)
const uploadButtonText = computed(() => {
  if (uploading.value) return `上传中 ${uploadProgress.value}%`
  if (fileList.value.length > 0 && pendingUploadCount.value === 0) return '已上传'
  if (fileList.value.some(file => file.status === 'error')) return '重试失败文件'
  return '开始上传'
})
const uploadProgressStatus = computed(() => {
  if (uploading.value) return undefined
  return uploadProgress.value === 100 ? 'success' : undefined
})

const getStatusClass = (status: string) => {
  const map: Record<string, string> = {
    waiting: 'status-waiting',
    uploading: 'status-uploading',
    success: 'status-success',
    error: 'status-error'
  }
  return map[status] || ''
}

const beforeUpload = (file: File) => {
  const allowedTypes = ['.pdf', '.docx', '.pptx', '.xlsx', '.png', '.jpg', '.jpeg', '.jp2', '.webp', '.gif', '.bmp', '.tiff']
  const imageTypes = ['.png', '.jpg', '.jpeg', '.jp2', '.webp', '.gif', '.bmp', '.tiff']
  const fileExt = file.name.toLowerCase().substring(file.name.lastIndexOf('.'))

  if (!allowedTypes.includes(fileExt)) {
    ElMessage.error('不支持的文件类型')
    return false
  }

  const maxSizeMb = imageTypes.includes(fileExt) ? 10 : 200
  const isWithinLimit = file.size / 1024 / 1024 <= maxSizeMb
  if (!isWithinLimit) {
    ElMessage.error(`${imageTypes.includes(fileExt) ? '图片' : '文档'}大小不能超过 ${maxSizeMb}MB`)
    return false
  }

  return true
}

const handleFileChange = (file: any) => {
  if (!file.raw) return
  if (!beforeUpload(file.raw)) return

  uploadResultMessage.value = ''
  uploadProgress.value = 0
  fileList.value.push({
    name: file.name,
    size: file.size,
    status: 'waiting',
    raw: file.raw,
    message: ''
  })
}

const handleFileRemove = (file: UploadFile, index?: number) => {
  if (typeof index === 'number') {
    fileList.value.splice(index, 1)
  } else {
    const foundIndex = fileList.value.findIndex(f => f.name === file.name && f.size === file.size)
    if (foundIndex !== -1) fileList.value.splice(foundIndex, 1)
  }
  if (fileList.value.length === 0) {
    uploadProgress.value = 0
    uploadResultMessage.value = ''
  }
}

const handleUpload = async () => {
  const filesToUpload = fileList.value.filter(file => file.status !== 'success' && file.raw)
  if (filesToUpload.length === 0) {
    ElMessage.warning('请先选择要上传的文件')
    return
  }

  uploading.value = true
  uploadProgress.value = 0
  uploadResultMessage.value = ''
  fileList.value = fileList.value.map(file => (
    filesToUpload.includes(file) ? { ...file, status: 'uploading', message: '' } : file
  ))
  try {
    const formData = new FormData()
    filesToUpload.forEach(file => {
      if (file.raw) {
        formData.append('files', file.raw)
      }
    })

    const result = await filesApi.uploadFiles(formData, progress => {
      uploadProgress.value = progress
    })

    if (result && result.total > 0) {
      const uploadedNames = new Set((result.files || []).map(file => file.filename))
      fileList.value = fileList.value.map(file => {
        if (!filesToUpload.some(uploadFile => uploadFile.name === file.name && uploadFile.size === file.size)) {
          return file
        }
        const uploaded = uploadedNames.has(file.name)
        return {
          ...file,
          status: uploaded ? 'success' : 'error',
          message: uploaded ? '已进入解析队列' : '上传结果未确认'
        }
      })
      uploadProgress.value = 100
      uploadResultMessage.value = `成功上传 ${result.total} 个文件，已进入解析队列`
      ElMessage.success(uploadResultMessage.value)
      uploadRef.value?.clearFiles()
    } else {
      fileList.value = fileList.value.map(file => (
        filesToUpload.some(uploadFile => uploadFile.name === file.name && uploadFile.size === file.size)
          ? { ...file, status: 'error', message: '上传失败，请重试' }
          : file
      ))
      uploadResultMessage.value = '文件上传失败，请重试'
    }
  } catch (error) {
    fileList.value = fileList.value.map(file => (
      filesToUpload.some(uploadFile => uploadFile.name === file.name && uploadFile.size === file.size)
        ? { ...file, status: 'error', message: '上传失败，请重试' }
        : file
    ))
    uploadResultMessage.value = '文件上传失败，请重试'
  } finally {
    uploading.value = false
  }
}
</script>

<style scoped>
.upload-root {
  width: 100%;
  display: flex;
  justify-content: center;
  padding: 20px;
  animation: fadeIn 0.3s ease;
  height: 100%;
  overflow: auto;
}

.upload-container {
  width: 100%;
  max-width: 720px;
  display: flex;
  flex-direction: column;
  gap: 16px;
}

.page-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
}

.header-left {
  display: flex;
  flex-direction: column;
  gap: 4px;
}

.page-title {
  font-size: 1.5rem;
  font-weight: 700;
  color: var(--text-primary);
  margin: 0;
}

.page-subtitle {
  font-size: 14px;
  color: var(--text-muted);
}

.upload-zone {
  width: 100%;
}

.upload-dragger {
  width: 100%;
}

.upload-dragger :deep(.el-upload-dragger) {
  width: 100%;
  padding: 32px 24px;
  border: 2px dashed var(--border-color);
  border-radius: var(--radius-xl);
  background: var(--bg-secondary);
  transition: all var(--transition-normal);
}

.upload-dragger :deep(.el-upload-dragger:hover) {
  border-color: var(--primary-color);
  background: rgb(99 102 241 / 0.02);
}

.upload-content {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 12px;
}

.upload-icon-wrapper {
  width: 64px;
  height: 64px;
  border-radius: 50%;
  background: rgb(99 102 241 / 0.1);
  display: flex;
  align-items: center;
  justify-content: center;
}

.upload-icon {
  color: var(--primary-color);
}

.upload-text {
  text-align: center;
}

.upload-main-text {
  font-size: 16px;
  color: var(--text-primary);
  margin: 0 0 8px;
}

.upload-link {
  color: var(--primary-color);
  font-weight: 500;
  cursor: pointer;
}

.upload-hint {
  font-size: 13px;
  color: var(--text-muted);
  margin: 0;
}

.file-list-section {
  background: var(--bg-primary);
  border-radius: var(--radius-lg);
  border: 1px solid var(--border-light);
  overflow: hidden;
  display: flex;
  flex-direction: column;
}

.section-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 12px 16px;
  border-bottom: 1px solid var(--border-light);
  background: var(--bg-tertiary);
  flex-shrink: 0;
}

.section-title {
  display: flex;
  align-items: center;
  gap: 8px;
  font-weight: 600;
  color: var(--text-primary);
}

.file-count-badge {
  background: var(--primary-color);
  color: white;
  font-size: 12px;
  padding: 2px 8px;
  border-radius: 10px;
  font-weight: 500;
}

.upload-progress {
  padding: 12px 16px 0;
}

.upload-result {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  padding: 10px 16px 0;
  font-size: 13px;
  color: var(--text-secondary);
}

.file-list {
  flex: 1;
  overflow-y: auto;
  min-height: 0;
  max-height: 200px;
}

.file-item {
  display: flex;
  align-items: center;
  gap: 12px;
  padding: 12px 16px;
  border-bottom: 1px solid var(--border-light);
  transition: background var(--transition-fast);
}

.file-item:last-child {
  border-bottom: none;
}

.file-item:hover {
  background: var(--bg-hover);
}

.file-uploading {
  background: rgb(99 102 241 / 0.04);
}

.file-icon {
  width: 40px;
  height: 40px;
  border-radius: var(--radius-md);
  background: var(--bg-tertiary);
  display: flex;
  align-items: center;
  justify-content: center;
  color: var(--text-muted);
  flex-shrink: 0;
}

.file-info {
  flex: 1;
  min-width: 0;
}

.file-name {
  font-weight: 500;
  color: var(--text-primary);
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

.file-meta {
  display: flex;
  align-items: center;
  gap: 12px;
  margin-top: 4px;
}

.file-size {
  font-size: 13px;
  color: var(--text-muted);
}

.file-message {
  min-width: 0;
  font-size: 12px;
  color: var(--text-muted);
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.file-status {
  font-size: 12px;
  padding: 2px 8px;
  border-radius: 4px;
}

.status-waiting {
  background: var(--bg-tertiary);
  color: var(--text-muted);
}

.status-uploading {
  background: rgb(99 102 241 / 0.1);
  color: var(--primary-color);
}

.status-success {
  background: rgb(16 185 129 / 0.1);
  color: var(--success-color);
}

.status-error {
  background: rgb(239 68 68 / 0.1);
  color: var(--danger-color);
}

.file-remove {
  opacity: 0;
  transition: opacity var(--transition-fast);
}

.file-item:hover .file-remove {
  opacity: 1;
}

.empty-state {
  padding: 24px 20px;
  text-align: center;
  flex: 1;
}

.empty-text {
  color: var(--text-muted);
  margin: 0;
}

.limits-info {
  display: flex;
  justify-content: center;
  gap: 20px;
  flex-wrap: wrap;
  flex-shrink: 0;
}

.limit-item {
  display: flex;
  align-items: center;
  gap: 6px;
  font-size: 13px;
  color: var(--text-muted);
}

@media (max-width: 768px) {
  .upload-root {
    padding: 20px 16px;
  }
  
  .page-header {
    flex-direction: column;
    align-items: flex-start;
    gap: 12px;
  }
  
  .url-btn {
    width: 100%;
  }
  
  .limits-info {
    flex-direction: column;
    align-items: center;
    gap: 8px;
  }
}
</style>
