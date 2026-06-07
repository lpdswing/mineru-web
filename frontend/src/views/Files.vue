<template>
  <div class="files-root">
    <div class="files-container">
      <!-- 页面头部 -->
      <div class="page-header">
        <div class="header-left">
          <h1 class="page-title">文件管理</h1>
          <span class="file-count">共 {{ total }} 个文件</span>
        </div>
        <div class="header-actions">
          <el-button 
            type="danger" 
            @click="handleBatchDelete" 
            :disabled="!multipleSelection.length"
          >
            <el-icon><Delete /></el-icon>
            <span>批量删除</span>
            <span v-if="multipleSelection.length" class="action-count">({{ multipleSelection.length }})</span>
          </el-button>
          <el-dropdown @command="handleBatchExport" :disabled="!multipleSelection.length">
            <el-button type="default" :loading="batchExporting">
              <el-icon><Download /></el-icon>
              <span>批量导出</span>
            </el-button>
            <template #dropdown>
              <el-dropdown-menu>
                <el-dropdown-item v-for="(name, format) in ExportFormatNames" :key="format" :command="format">
                  {{ name }}
                </el-dropdown-item>
              </el-dropdown-menu>
            </template>
          </el-dropdown>
          <el-button type="primary" @click="$router.push('/upload')">
            <el-icon><Upload /></el-icon>
            <span>上传文件</span>
          </el-button>
        </div>
      </div>

      <!-- 搜索筛选栏 -->
      <div class="filter-bar">
        <el-input
          v-model="params.search"
          placeholder="搜索文件名..."
          class="search-input"
          clearable
          @input="onParamChange"
        >
          <template #prefix>
            <el-icon><Search /></el-icon>
          </template>
        </el-input>
        <el-select v-model="params.status" placeholder="全部状态" class="status-select" clearable @change="onParamChange">
          <el-option label="全部状态" value="" />
          <el-option label="等待解析" value="pending" />
          <el-option label="解析中" value="parsing" />
          <el-option label="已完成" value="parsed" />
          <el-option label="解析失败" value="parse_failed" />
        </el-select>
      </div>

      <!-- 文件表格 -->
      <div class="table-wrapper">
        <el-table 
          :data="files" 
          v-if="files && files.length > 0 && !loading" 
          @selection-change="handleSelectionChange"
          :header-cell-style="{ background: 'var(--bg-tertiary)', color: 'var(--text-primary)', fontWeight: 600 }"
        >
          <el-table-column type="selection" width="48" />
          <el-table-column prop="filename" label="文件名称" min-width="200">
            <template #default="{ row }">
              <div class="file-name-cell">
                <el-tag
                  v-if="row.backend"
                  size="small"
                  :style="{ background: getBackendColor(row.backend), color: 'white', border: 'none' }"
                >
                  {{ getBackendIcon(row.backend) }}
                </el-tag>
                <span class="file-name">{{ row.filename }}</span>
              </div>
            </template>
          </el-table-column>
          <el-table-column prop="size" label="大小" width="100">
            <template #default="{ row }">
              <span class="cell-text">{{ formatFileSize(row.size) }}</span>
            </template>
          </el-table-column>
          <el-table-column prop="uploadTime" label="上传时间" width="160">
            <template #default="{ row }">
              <span class="cell-text">{{ formatDateTime(row.upload_time) }}</span>
            </template>
          </el-table-column>
          <el-table-column prop="finish_at" label="解析完成时间" width="160">
            <template #default="{ row }">
              <span class="cell-text">{{ formatDateTime(row.finish_at) }}</span>
            </template>
          </el-table-column>
          <el-table-column prop="status" label="状态" width="110">
            <template #default="{ row }">
              <div class="status-cell">
                <span class="status-dot" :class="getStatusClass(row.status)"></span>
                <el-tooltip
                  v-if="row.status === 'parse_failed' && row.error_message"
                  :content="row.error_message"
                  placement="top"
                >
                  <span class="status-error-text">{{ getStatusText(row.status) }}</span>
                </el-tooltip>
                <span v-else>{{ getStatusText(row.status) }}</span>
              </div>
            </template>
          </el-table-column>
          <el-table-column label="操作" width="280" fixed="right">
            <template #default="{ row }">
              <div class="action-cell">
                <el-button class="action-link" link @click="openPreview(row)">查看</el-button>
                <el-button class="action-link" link @click="downloadFile(row)">下载</el-button>
                <el-button class="action-link danger" link @click="deleteFile(row)">删除</el-button>
                <el-button 
                  class="action-link"
                  link 
                  @click="parseFile(row)"
                  :disabled="row.status === 'parsed' || row.status === 'parsing'"
                >解析</el-button>
                <el-dropdown @command="(fmt: string) => handleExport(row, fmt as ExportFormat)">
                  <el-button class="action-link" link :loading="exportingId === row.id">
                    导出 <el-icon class="el-icon--right"><ArrowDown /></el-icon>
                  </el-button>
                  <template #dropdown>
                    <el-dropdown-menu>
                      <el-dropdown-item v-for="(name, format) in ExportFormatNames" :key="format" :command="format">
                        {{ name }}
                      </el-dropdown-item>
                    </el-dropdown-menu>
                  </template>
                </el-dropdown>
              </div>
            </template>
          </el-table-column>
        </el-table>

        <!-- 空状态 -->
        <div v-else-if="!loading" class="empty-state">
          <el-empty description="暂无文件">
            <el-button type="primary" @click="$router.push('/upload')">
              <el-icon><Upload /></el-icon>
              上传文件
            </el-button>
          </el-empty>
        </div>

        <!-- 加载状态 -->
        <el-skeleton v-else :rows="8" animated class="table-skeleton" />
      </div>

      <!-- 分页 -->
      <div class="pagination-wrapper">
        <el-pagination
          v-model:current-page="params.page"
          v-model:page-size="params.pageSize"
          :total="total"
          :page-sizes="[10, 20, 50, 100]"
          layout="total, sizes, prev, pager, next"
          @size-change="onParamChange"
          @current-change="onParamChange"
        />
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, reactive, watch, onMounted, onUnmounted, computed } from 'vue'
import { Upload, Delete, Search, Download, ArrowDown } from '@element-plus/icons-vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { useRouter } from 'vue-router'
import JSZip from 'jszip'
import axios from 'axios'
import { filesApi } from '@/api/files'
import { formatFileSize } from '@/utils/format'
import {
  formatDateTime,
  getFileStatusText as getStatusText,
  getBackendIcon,
  getBackendColor
} from '@/utils/status'
import type { FileItem, ExportFormat } from '@/types/file'
import { ExportFormatNames } from '@/types/file'

const files = ref<FileItem[]>([])
const total = ref(0)
const loading = ref(false)
const pollingTimer = ref<number | null>(null)
const POLLING_INTERVAL = 3000

const params = reactive({
  page: 1,
  pageSize: 10,
  search: '',
  status: ''
})

const exportingId = ref<string>('')
const batchExporting = ref(false)
const multipleSelection = ref<FileItem[]>([])
const router = useRouter()

const hasParsingFiles = computed(() => files.value.some(f => f.status === 'parsing'))

const getStatusClass = (status: string) => {
  const map: Record<string, string> = {
    pending: 'status-pending',
    parsing: 'status-parsing',
    parsed: 'status-success',
    parse_failed: 'status-error'
  }
  return map[status] || 'status-pending'
}

const openPreview = (file: FileItem) => {
  router.push({ 
    name: 'FilePreview', 
    params: { id: file.id },
    query: { page: params.page }
  })
}

const handleExport = async (file: FileItem, format: ExportFormat) => {
  if (!file || exportingId.value === file.id) return
  exportingId.value = file.id
  try {
    const result = await filesApi.exportFile(file.id, format)
    if (result.status === 'success') {
      const response = await fetch(result.download_url)
      const blob = await response.blob()
      const url = window.URL.createObjectURL(blob)
      const link = document.createElement('a')
      link.href = url
      link.download = result.filename
      document.body.appendChild(link)
      link.click()
      window.URL.revokeObjectURL(url)
      document.body.removeChild(link)
      ElMessage.success(`导出${ExportFormatNames[format]}成功`)
    }
  } finally {
    exportingId.value = ''
  }
}

const stopPolling = () => {
  if (pollingTimer.value) {
    clearInterval(pollingTimer.value)
    pollingTimer.value = null
  }
}

const updateFiles = (newFiles: FileItem[]) => {
  if (files.value.length !== newFiles.length) {
    files.value = newFiles
    return
  }
  newFiles.forEach((newFile, index) => {
    const oldFile = files.value[index]
    if (oldFile.id === newFile.id && oldFile.status !== newFile.status) {
      files.value[index] = newFile
    }
  })
}

const startPolling = () => {
  stopPolling()
  pollingTimer.value = window.setInterval(async () => {
    await pollFiles()
  }, POLLING_INTERVAL)
}

const pollFiles = async () => {
  try {
    const result = await filesApi.getFiles({
      page: params.page,
      page_size: params.pageSize,
      search: params.search,
      status: params.status
    })
    updateFiles(result.files)
    total.value = result.total
  } catch (e) {}
}

const fetchFiles = async () => {
  loading.value = true
  try {
    const result = await filesApi.getFiles({
      page: params.page,
      page_size: params.pageSize,
      search: params.search,
      status: params.status
    })
    files.value = result.files
    total.value = result.total
  } catch (e) {
    files.value = []
    total.value = 0
  } finally {
    loading.value = false
  }
}

const deleteFile = (file: FileItem) => {
  ElMessageBox.confirm('确定要删除该文件吗？', '删除确认', {
    confirmButtonText: '确定',
    cancelButtonText: '取消',
    type: 'warning'
  }).then(async () => {
    try {
      await filesApi.deleteFile(file.id)
      ElMessage.success('删除成功')
      fetchFiles()
    } catch (e) {}
  }).catch(() => {})
}

const downloadFile = async (file: FileItem) => {
  try {
    const result = await filesApi.getDownloadUrl(file.id)
    const response = await axios.get(result.url, { responseType: 'blob' })
    const blob = new Blob([response.data])
    const url = window.URL.createObjectURL(blob)
    const link = document.createElement('a')
    link.href = url
    link.download = file.filename
    document.body.appendChild(link)
    link.click()
    window.URL.revokeObjectURL(url)
    document.body.removeChild(link)
  } catch (e) {}
}

const handleBatchDelete = async () => {
  if (!multipleSelection.value.length || batchExporting.value) return
  ElMessageBox.confirm(
    `确定要删除选中的 ${multipleSelection.value.length} 个文件吗？`,
    '批量删除确认',
    { confirmButtonText: '确定', cancelButtonText: '取消', type: 'warning' }
  ).then(async () => {
    batchExporting.value = true
    const failedFiles: string[] = []
    try {
      const deletePromises = multipleSelection.value.map(async (file) => {
        try {
          await filesApi.deleteFile(file.id)
        } catch (e) {
          failedFiles.push(file.filename)
        }
      })
      await Promise.all(deletePromises)
      if (failedFiles.length === 0) {
        ElMessage.success(`成功删除 ${multipleSelection.value.length} 个文件`)
      } else if (failedFiles.length < multipleSelection.value.length) {
        ElMessage.warning(`成功删除 ${multipleSelection.value.length - failedFiles.length} 个文件，${failedFiles.length} 个文件删除失败`)
      } else {
        ElMessage.error('所有文件删除失败')
      }
      fetchFiles()
    } finally {
      batchExporting.value = false
    }
  }).catch(() => {})
}

const handleBatchExport = async (format: ExportFormat) => {
  if (!multipleSelection.value.length || batchExporting.value) return
  batchExporting.value = true
  try {
    const zip = new JSZip()
    for (const file of multipleSelection.value) {
      try {
        const result = await filesApi.exportFile(file.id, format)
        if (result.status === 'success') {
          const response = await fetch(result.download_url)
          const content = await response.blob()
          zip.file(result.filename, content)
        }
      } catch (e) {}
    }
    const zipBlob = await zip.generateAsync({ type: 'blob' })
    const url = window.URL.createObjectURL(zipBlob)
    const link = document.createElement('a')
    link.href = url
    link.download = `batch_export_${new Date().getTime()}.zip`
    document.body.appendChild(link)
    link.click()
    window.URL.revokeObjectURL(url)
    document.body.removeChild(link)
    ElMessage.success(`批量导出${ExportFormatNames[format]}完成`)
  } finally {
    batchExporting.value = false
  }
}

const handleSelectionChange = (val: FileItem[]) => {
  multipleSelection.value = val
}

const parseFile = async (file: FileItem) => {
  try {
    await filesApi.parseFile(file.id)
    ElMessage.success('解析任务已提交')
    const index = files.value.findIndex(f => f.id === file.id)
    if (index !== -1) {
      files.value[index] = { ...files.value[index], status: 'parsing' }
    }
  } catch (e) {}
}

const onParamChange = () => {
  fetchFiles()
}

const handleSearch = () => {
  params.page = 1
  fetchFiles()
}

onMounted(() => {
  fetchFiles().then(() => {
    startPolling()
  })
})

onUnmounted(() => {
  stopPolling()
})

watch([() => params.search, () => params.status], () => {
  handleSearch()
})

watch([() => params.page, () => params.pageSize], () => {
  fetchFiles()
})

watch(hasParsingFiles, (hasParsing) => {
  if (hasParsing) {
    startPolling()
  } else {
    stopPolling()
  }
})
</script>

<style scoped>
.files-root {
  width: 100%;
  height: 100%;
  padding: 20px 24px;
  animation: fadeIn 0.3s ease;
  display: flex;
  flex-direction: column;
  overflow: hidden;
}

.files-container {
  width: 100%;
  height: 100%;
  display: flex;
  flex-direction: column;
  gap: 16px;
  overflow: hidden;
}

.page-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  flex-wrap: wrap;
  gap: 12px;
  flex-shrink: 0;
}

.header-left {
  display: flex;
  align-items: baseline;
  gap: 12px;
}

.page-title {
  font-size: 1.5rem;
  font-weight: 700;
  color: var(--text-primary);
  margin: 0;
}

.file-count {
  font-size: 14px;
  color: var(--text-muted);
}

.header-actions {
  display: flex;
  gap: 12px;
  flex-wrap: wrap;
}

.action-count {
  margin-left: 4px;
  opacity: 0.8;
}

.filter-bar {
  display: flex;
  gap: 12px;
  flex-wrap: wrap;
  flex-shrink: 0;
}

.search-input {
  width: 280px;
}

.status-select {
  width: 140px;
}

.table-wrapper {
  background: var(--bg-primary);
  border-radius: var(--radius-lg);
  overflow: hidden;
  box-shadow: var(--shadow-sm);
  flex: 1;
  min-height: 0;
  display: flex;
  flex-direction: column;
}

.table-wrapper :deep(.el-table) {
  --el-table-border-color: var(--border-light);
  flex: 1;
}

.table-wrapper :deep(.el-table__body-wrapper) {
  overflow-y: auto;
}

.file-name-cell {
  display: flex;
  align-items: center;
  gap: 8px;
}

.file-name {
  font-weight: 500;
  color: var(--text-primary);
}

.cell-text {
  color: var(--text-secondary);
  font-size: 13px;
}

.status-cell {
  display: flex;
  align-items: center;
  gap: 8px;
  font-size: 13px;
}

.status-dot {
  width: 8px;
  height: 8px;
  border-radius: 50%;
}

.status-pending {
  background: var(--text-muted);
}

.status-parsing {
  background: var(--warning-color);
  animation: pulse 1.5s infinite;
}

.status-success {
  background: var(--success-color);
}

.status-error {
  background: var(--danger-color);
}

.action-cell {
  display: flex;
  align-items: center;
  gap: 4px;
}

.action-link {
  color: var(--text-secondary) !important;
  font-weight: 500;
  transition: color var(--transition-fast);
}

.action-link:hover {
  color: var(--primary-color) !important;
}

.action-link.danger:hover {
  color: var(--danger-color) !important;
}

.action-link:disabled {
  color: var(--text-muted) !important;
  opacity: 0.5;
}

.empty-state {
  padding: 60px 20px;
  text-align: center;
}

.table-skeleton {
  padding: 24px;
}

.pagination-wrapper {
  display: flex;
  justify-content: center;
  padding-top: 8px;
  flex-shrink: 0;
}

@media (max-width: 992px) {
  .files-root {
    padding: 20px 16px;
  }
  
  .page-header {
    flex-direction: column;
    align-items: flex-start;
  }
  
  .header-actions {
    width: 100%;
  }
  
  .filter-bar {
    flex-direction: column;
  }
  
  .search-input,
  .status-select {
    width: 100%;
  }
}
</style>
