<template>
  <div class="upload-root">
    <div class="upload-card">
      <div class="upload-header">
        <span class="upload-title">点击或拖拽上传文档</span>
        <el-button class="url-btn" type="default" size="small" plain @click="showUrlDialog = true">
          <el-icon><link /></el-icon> URL 上传
        </el-button>
      </div>
      <el-upload
        ref="uploadRef"
        class="upload-area"
        drag
        action="/api/upload"
        :auto-upload="false"
        :on-change="handleFileChange"
        :on-remove="handleFileRemove"
        :before-upload="beforeUpload"
        accept=".pdf,.png,.jpg,.jpeg"
        multiple
        :limit="20"
        :disabled="uploading"
      >
        <el-icon class="el-icon--upload"><upload-filled /></el-icon>
        <div class="el-upload__text">
          拖拽文件到此处，或 <span class="upload-link">点击上传</span>
        </div>
        <template #tip>
          <div class="el-upload__tip">
            支持的文件类型：PDF、PNG、JPG、JPEG
            <br>
            单个文档不超过 <b>200M</b> 或 <b>600</b> 页，单图片不超过 <b>10M</b>，单次最多 <b>20</b> 个文件
          </div>
        </template>
      </el-upload>
      <div class="upload-list" v-if="fileList.length > 0">
        <div class="upload-list-header">
          <span>待上传文件列表</span>
          <el-button type="primary" @click="handleUpload" :loading="uploading" :disabled="uploading || fileList.length === 0" size="small">
            <el-icon v-if="!uploading"><upload-filled /></el-icon>
            <span v-if="!uploading">开始上传</span>
            <span v-else>上传中...</span>
          </el-button>
        </div>
        <el-table :data="fileList" border stripe>
          <el-table-column prop="name" label="文件名" />
          <el-table-column prop="size" label="大小" width="120">
            <template #default="{ row }">{{ formatFileSize(row.size) }}</template>
          </el-table-column>
          <el-table-column label="状态" width="120">
            <template #default="{ row }">
              <el-tag :type="getStatusType(row.status)">
                {{ getStatusText(row.status) }}
              </el-tag>
            </template>
          </el-table-column>
          <el-table-column label="操作" width="120">
            <template #default="{ row }">
              <el-button 
                type="danger" 
                link 
                @click="handleFileRemove(row)"
                :disabled="row.status === 'uploading' || uploading"
              >
                删除
              </el-button>
            </template>
          </el-table-column>
        </el-table>
      </div>
      <el-empty v-else description="暂无待上传文件，快来体验智能解析吧！" :image-size="100" class="upload-empty" />
    </div>
    <el-dialog v-model="showUrlDialog" title="URL 上传" width="400px" :close-on-click-modal="false">
      <el-form @submit.prevent>
        <el-form-item label="文档URL" :error="urlError">
          <el-input v-model="urlInput" placeholder="请输入文档下载地址" clearable />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="showUrlDialog = false">取消</el-button>
        <el-button type="primary" @click="handleUrlUpload">添加到上传列表</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup lang="ts">
import { ref } from 'vue'
import { UploadFilled } from '@element-plus/icons-vue'
import { ElMessage } from 'element-plus'
import axios from 'axios'
import type { UploadInstance } from 'element-plus'
import { getUserId } from '@/utils/user'
import { formatFileSize } from '@/utils/format'

interface UploadFile {
  name: string
  size: number
  status: 'waiting' | 'uploading' | 'success' | 'error'
  raw?: File
  url?: string
}

const fileList = ref<UploadFile[]>([])
const uploading = ref(false)

// URL上传相关
const showUrlDialog = ref(false)
const urlInput = ref('')
const urlError = ref('')

const uploadRef = ref<UploadInstance>()


const beforeUpload = (file: File) => {
  // 检查文件大小
  console.log('文件大小:', file.size)
  const isLt200M = file.size / 1024 / 1024 < 200
  if (!isLt200M) {
    ElMessage.error('文件大小不能超过 200MB!')
    return false
  }

  // 检查文件类型
  const allowedTypes = [
    // PDF
    '.pdf',
    // Office (Word & PowerPoint)
    // '.doc', '.docx', '.ppt', '.pptx',
    // 图片
    '.png', '.jpg', '.jpeg'
  ]
  
  const fileExt = file.name.toLowerCase().substring(file.name.lastIndexOf('.'))
  console.log('文件类型:', fileExt)
  console.log('允许的类型:', allowedTypes)
  console.log('是否允许:', allowedTypes.includes(fileExt))

  // 检查是否是 Excel 文件
  if (fileExt === '.xls' || fileExt === '.xlsx') {
    ElMessage.error('不支持 Excel 文件上传！')
    return false
  }

  if (!allowedTypes.includes(fileExt)) {
    ElMessage.error(`不支持的文件类型！仅支持：PDF、Word、PowerPoint、PNG、JPG`)
    return false
  }

  return true
}

const handleFileChange = (file: any) => {
  // 在文件变化时也进行类型检查
  if (!beforeUpload(file.raw)) {
    return
  }
  
  fileList.value.push({
    name: file.name,
    size: file.size,
    status: 'waiting',
    raw: file.raw
  })
}

const handleFileRemove = (file: UploadFile) => {
  const index = fileList.value.findIndex(f => f.name === file.name)
  if (index !== -1) {
    fileList.value.splice(index, 1)
  }
}

const getStatusType = (status: string) => {
  const map: Record<string, string> = {
    waiting: 'info',
    uploading: 'warning',
    success: 'success',
    error: 'danger'
  }
  return map[status] || 'info'
}

const getStatusText = (status: string) => {
  const map: Record<string, string> = {
    waiting: '等待上传',
    uploading: '上传中',
    success: '上传成功',
    error: '上传失败'
  }
  return map[status] || '未知状态'
}

const handleUrlUpload = () => {
  urlError.value = ''
  const url = urlInput.value.trim()
  if (!url) {
    urlError.value = '请输入文档URL'
    return
  }
  // 简单校验URL格式
  if (!/^https?:\/\//.test(url)) {
    urlError.value = '请输入有效的URL（http/https）'
    return
  }
  // 模拟文件名
  const name = url.split('/').pop() || '远程文档.pdf'
  fileList.value.push({
    name: name,
    size: 0,
    status: 'waiting',
    url
  })
  showUrlDialog.value = false
  urlInput.value = ''
  ElMessage.success('已添加到上传列表')
}

const handleUpload = async () => {
  if (fileList.value.length === 0) {
    ElMessage.warning('请先选择要上传的文件')
    return
  }

  uploading.value = true
  try {
    const formData = new FormData()
    fileList.value.forEach(file => {
      if (file.raw) {
        formData.append('files', file.raw)
      }
      // 如有URL上传，也可在此处理
    })

    const res = await axios.post('/api/upload', formData, {
      headers: {
        'Content-Type': 'multipart/form-data',
        'X-User-Id': getUserId()
      }
    })

    if (res.data && res.data.total > 0) {
      ElMessage.success('文件上传成功，已进入解析队列！')
      fileList.value = []
      // 清空el-upload组件的文件列表
      uploadRef.value?.clearFiles()
    } else {
      ElMessage.error('文件上传失败，请重试！')
    }
  } catch (error) {
    console.error('上传失败:', error)
    ElMessage.error('文件上传失败，请重试！')
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
  align-items: flex-start;
  padding: 32px 0 0 0;
  box-sizing: border-box;
  /* min-height: 70vh; */
  /* height: auto; */
}
.upload-card {
  width: 100%;
  max-width: 80vw;
  background: transparent;
  border-radius: 0;
  box-shadow: none;
  padding: 24px 0;
  display: flex;
  flex-direction: column;
  align-items: center;
}
.upload-header {
  width: 100%;
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 18px;
}
.upload-title {
  font-size: 1.3rem;
  font-weight: 600;
  color: #222;
}
.url-btn {
  border-radius: 8px;
  font-size: 0.98rem;
  background: #f7f8fa;
  color: #409eff;
  border: none;
}
.upload-area {
  width: 100%;
  margin-bottom: 18px;
}
.upload-link {
  color: #409eff;
  font-weight: 500;
  cursor: pointer;
}
.upload-list {
  width: 100%;
  margin-top: 18px;
  /* max-height: 400px; */
  overflow-y: auto;
}
.upload-list-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 12px;
}
.upload-empty {
  margin: 32px 0 0 0;
  height: auto;
  max-height: 10vh;
}
:deep(.el-upload-dragger) {
  width: 100%;
  border-radius: 12px;
  background: #f7f8fa;
  border: 1.5px dashed #b1b3b8;
  min-height: 180px;
  display: flex;
  flex-direction: column;
  justify-content: center;
}
:deep(.el-upload__tip) {
  margin-top: 8px;
  color: #909399;
}
:deep(.el-table) {
  border-radius: 12px;
  overflow: hidden;
}
@media (max-width: 1024px) {
  .upload-card {
    max-width: 680px;
    padding: 24px 16px;
  }
}
@media (max-width: 768px) {
  .upload-root {
    padding: 20px 16px 0 16px;
  }
  .upload-card {
    max-width: 100%;
    padding: 20px 12px;
  }
  .upload-header {
    flex-direction: column;
    align-items: stretch;
    gap: 12px;
  }
  .url-btn {
    align-self: flex-end;
  }
  .upload-list-header {
    flex-direction: column;
    align-items: stretch;
    gap: 12px;
  }
  .upload-list-header > span {
    font-weight: 600;
  }
  :deep(.el-upload-dragger) {
    min-height: 160px;
  }
}
</style> 