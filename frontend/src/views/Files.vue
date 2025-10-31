<template>
  <div class="files-root">
    <div class="files-card">
      <div class="files-header">
        <span class="files-title">文件列表</span>
        <div class="files-header-actions">
          <el-button type="danger" size="large" class="batch-delete-btn" @click="handleBatchDelete" :disabled="!multipleSelection.length" plain>
            <el-icon><Delete /></el-icon> 批量删除
          </el-button>
          <el-dropdown @command="handleBatchExport" :disabled="!multipleSelection.length">
            <el-button type="info" size="large" class="batch-export-btn" :loading="batchExporting" plain>
              <el-icon><i class="el-icon-download" /></el-icon> 批量导出 <el-icon><i class="el-icon-arrow-down" /></el-icon>
            </el-button>
            <template #dropdown>
              <el-dropdown-menu>
                <el-dropdown-item v-for="(name, format) in ExportFormatNames" 
                                :key="format" 
                                :command="format">
                  {{ name }}
                </el-dropdown-item>
              </el-dropdown-menu>
            </template>
          </el-dropdown>
          <el-button type="primary" size="large" class="upload-btn" @click="$router.push('/upload')">
            <el-icon><Upload /></el-icon> 上传文件
          </el-button>
        </div>
      </div>
      <div class="files-toolbar">
        <el-input
          v-model="params.search"
          placeholder="请输入文件名称"
          class="search-input"
          clearable
          prefix-icon="Search"
          @input="onParamChange"
        />
        <el-select v-model="params.status" placeholder="筛选状态" class="status-select" clearable @change="onParamChange">
          <el-option label="全部" value="" />
          <el-option label="等待解析" value="pending" />
          <el-option label="解析中" value="parsing" />
          <el-option label="已完成" value="parsed" />
          <el-option label="解析失败" value="parse_failed" />
        </el-select>
      </div>
      <el-table :data="files" border stripe v-if="files && files.length > 0 && !loading" @selection-change="handleSelectionChange">
        <el-table-column type="selection" width="48" />
        <el-table-column prop="filename" label="文件名称">
          <template #default="{ row }">
            <div style="display: flex; align-items: center; gap: 8px;">
              <el-tag
                v-if="row.backend"
                size="small"
                :color="getBackendColor(row.backend)"
                style="color: white; border: none; padding: 0 6px; height: 20px; line-height: 20px;"
              >
                {{ getBackendIcon(row.backend) }}
              </el-tag>
              <span>{{ row.filename }}</span>
            </div>
          </template>
        </el-table-column>
        <el-table-column prop="size" label="大小" width="120">
          <template #default="{ row }">{{ formatFileSize(row.size) }}</template>
        </el-table-column>
        <el-table-column prop="uploadTime" label="创建时间" width="180">
          <template #default="{ row }">{{ formatDateTime(row.upload_time) }}</template>
        </el-table-column>
        <el-table-column prop="start_at" label="开始时间" width="180">
          <template #default="{ row }">{{ formatDateTime(row.start_at) }}</template>
        </el-table-column>
        <el-table-column prop="finish_at" label="结束时间" width="180">
          <template #default="{ row }">{{ formatDateTime(row.finish_at) }}</template>
        </el-table-column>
        <el-table-column prop="status" label="状态" width="120">
          <template #default="{ row }">
            <el-tag :type="getStatusType(row.status)">
              {{ getStatusText(row.status) }}
            </el-tag>
          </template>
        </el-table-column>
        <el-table-column label="操作" width="260">
          <template #default="{ row }">
            <el-button type="primary" link @click="openPreview(row)">查看</el-button>
            <el-button type="success" link @click="downloadFile(row)">下载</el-button>
            <el-button type="danger" link @click="deleteFile(row)">删除</el-button>
            <el-button 
              type="warning" 
              link 
              @click="parseFile(row)"
              :disabled="row.status === 'parsed' || row.status === 'parsing'"
              :title="row.status === 'parsed' ? '文件已解析完成' : (row.status === 'parsing' ? '文件正在解析中' : '开始解析')"
            >解析</el-button>
            <el-dropdown @command="(fmt: string) => handleExport(row, fmt as ExportFormat)">
              <el-button type="info" link :loading="exportingId === row.id">
                导出 <el-icon><i class="el-icon-arrow-down" /></el-icon>
              </el-button>
              <template #dropdown>
                <el-dropdown-menu>
                  <el-dropdown-item v-for="(name, format) in ExportFormatNames" 
                                  :key="format" 
                                  :command="format">
                    {{ name }}
                  </el-dropdown-item>
                </el-dropdown-menu>
              </template>
            </el-dropdown>
          </template>
        </el-table-column>
      </el-table>
      <el-empty v-else-if="!loading" description="暂无数据" :image-size="80" class="files-empty" />
      <el-skeleton v-else :rows="6" animated style="margin:32px 0" />
      <div class="pagination-container">
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
import { Upload, Delete } from '@element-plus/icons-vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { useRouter } from 'vue-router'
import JSZip from 'jszip'
import axios from 'axios'
import { filesApi } from '@/api/files'
import { formatFileSize } from '@/utils/format'
import {
  formatDateTime,
  getFileStatusText as getStatusText,
  getFileStatusType as getStatusType,
  getBackendIcon,
  getBackendColor
} from '@/utils/status'
import type { FileItem, ExportFormat } from '@/types/file'
import { ExportFormatNames } from '@/types/file'

const files = ref<FileItem[]>([])
const total = ref(0)
const loading = ref(false)
const pollingTimer = ref<number | null>(null)

// 轮询间隔（毫秒）
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

// 智能轮询：只有在有parsing状态的文件时才轮询
const hasParsingFiles = computed(() =>
  files.value.some(f => f.status === 'parsing')
)

const openPreview = (file: FileItem) => {
  router.push({ name: 'FilePreview', params: { id: file.id } })
}

const handleExport = async (file: FileItem, format: ExportFormat) => {
  if (!file || exportingId.value === file.id) return

  exportingId.value = file.id
  try {
    const result = await filesApi.exportFile(file.id, format)

    if (result.status === 'success') {
      // 使用 fetch 下载文件
      const response = await fetch(result.download_url)
      const blob = await response.blob()

      // 创建一个 Blob URL
      const url = window.URL.createObjectURL(blob)

      // 创建一个隐藏的 a 标签来下载文件
      const link = document.createElement('a')
      link.href = url
      link.download = result.filename
      document.body.appendChild(link)
      link.click()

      // 清理
      window.URL.revokeObjectURL(url)
      document.body.removeChild(link)

      ElMessage.success(`导出${ExportFormatNames[format]}成功`)
    }
  } catch (e) {
    // 错误已在拦截器中处理
  } finally {
    exportingId.value = ''
  }
}

// 停止轮询
const stopPolling = () => {
  if (pollingTimer.value) {
    clearInterval(pollingTimer.value)
    pollingTimer.value = null
  }
}

// 智能更新文件列表
const updateFiles = (newFiles: FileItem[]) => {
  if (files.value.length !== newFiles.length) {
    files.value = newFiles
    return
  }

  // 只更新发生变化的文件
  newFiles.forEach((newFile, index) => {
    const oldFile = files.value[index]
    if (oldFile.id === newFile.id && oldFile.status !== newFile.status) {
      files.value[index] = newFile
    }
  })
}

// 开始轮询
const startPolling = () => {
  // 确保不会重复启动轮询
  stopPolling()

  // 立即启动轮询
  pollingTimer.value = window.setInterval(async () => {
    await pollFiles()
  }, POLLING_INTERVAL)
}

// 轮询获取文件列表
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
  } catch (e) {
    // 错误已在拦截器中处理，这里静默失败
  }
}

// 初始加载文件列表
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
  ElMessageBox.confirm(
    '确定要删除该文件吗？',
    '警告',
    {
      confirmButtonText: '确定',
      cancelButtonText: '取消',
      type: 'warning'
    }
  ).then(async () => {
    try {
      await filesApi.deleteFile(file.id)
      ElMessage.success('删除成功')
      fetchFiles()
    } catch (e) {
      // 错误已在拦截器中处理
    }
  }).catch(() => {})
}

const downloadFile = async (file: FileItem) => {
  try {
    const result = await filesApi.getDownloadUrl(file.id)

    // 使用 axios 获取文件内容，设置 responseType 为 blob
    const response = await axios.get(result.url, {
      responseType: 'blob'
    })

    // 创建 Blob URL
    const blob = new Blob([response.data])
    const url = window.URL.createObjectURL(blob)

    // 创建临时链接并下载
    const link = document.createElement('a')
    link.href = url
    link.download = file.filename
    document.body.appendChild(link)
    link.click()

    // 清理
    window.URL.revokeObjectURL(url)
    document.body.removeChild(link)
  } catch (e) {
    // 错误已在拦截器中处理
  }
}

const handleBatchDelete = async () => {
  if (!multipleSelection.value.length || batchExporting.value) return
  
  ElMessageBox.confirm(
    `确定要删除选中的 ${multipleSelection.value.length} 个文件吗？`,
    '批量删除确认',
    {
      confirmButtonText: '确定',
      cancelButtonText: '取消',
      type: 'warning'
    }
  ).then(async () => {
    batchExporting.value = true
    const failedFiles: string[] = []
    
    try {
      // 并发删除所有选中的文件
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
      
      // 重新加载文件列表
      fetchFiles()
    } catch (e) {
      // 错误已在拦截器中处理
    } finally {
      batchExporting.value = false
    }
  }).catch(() => {})
}

const handleBatchExport = async (format: ExportFormat) => {
  if (!multipleSelection.value.length || batchExporting.value) return
  
  batchExporting.value = true
  try {
    // 创建 JSZip 实例
    const zip = new JSZip()
    
    // 对每个文件分别调用导出接口
    for (const file of multipleSelection.value) {
      try {
        const result = await filesApi.exportFile(file.id, format)

        if (result.status === 'success') {
          // 获取文件内容
          const response = await fetch(result.download_url)
          const content = await response.blob()

          // 添加到zip文件
          zip.file(result.filename, content)
        }
      } catch (e) {
        // 单个文件失败不中断整体流程
      }
    }
    
    // 生成zip文件
    const zipBlob = await zip.generateAsync({ type: 'blob' })
    
    // 创建下载链接
    const url = window.URL.createObjectURL(zipBlob)
    const link = document.createElement('a')
    link.href = url
    link.download = `batch_export_${new Date().getTime()}.zip`
    document.body.appendChild(link)
    link.click()
    
    // 清理
    window.URL.revokeObjectURL(url)
    document.body.removeChild(link)
    
    ElMessage.success(`批量导出${ExportFormatNames[format]}完成`)
  } catch (e) {
    // 错误已在拦截器中处理
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

    // 立即更新文件状态为 parsing
    const index = files.value.findIndex(f => f.id === file.id)
    if (index !== -1) {
      files.value[index] = { ...files.value[index], status: 'parsing' }
    }
  } catch (e) {
    // 错误已在拦截器中处理
  }
}

// 处理参数变化
const onParamChange = () => {
  fetchFiles()
}

// 处理搜索和状态筛选
const handleSearch = () => {
  params.page = 1
  fetchFiles()
}

onMounted(() => {
  fetchFiles().then(() => {
    startPolling()
  })
})

// 组件卸载时停止轮询
onUnmounted(() => {
  stopPolling()
})

// 监听搜索和状态变化
watch([() => params.search, () => params.status], () => {
  handleSearch()
})

// 监听分页变化
watch([() => params.page, () => params.pageSize], () => {
  fetchFiles()
})

// 智能轮询：只在有parsing文件时轮询
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
  display: flex;
  justify-content: flex-start;
  align-items: flex-start;
  padding: 24px 32px 0 32px;
  box-sizing: border-box;
  overflow-x: hidden;
}
.files-card {
  width: 100%;
  max-width: none;
  background: transparent;
  border-radius: 0;
  box-shadow: none;
  padding: 0;
  margin: 0;
  display: flex;
  flex-direction: column;
  align-items: stretch;
  overflow-x: auto;
  box-sizing: border-box;
}
.files-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 18px;
}
.files-header-actions {
  display: flex;
  gap: 16px;
  align-items: center;
}
.batch-export-btn {
  border-radius: 8px;
  font-size: 1.05rem;
}
.batch-delete-btn {
  border-radius: 8px;
  font-size: 1.05rem;
}
.files-title {
  font-size: 1.3rem;
  font-weight: 600;
  color: #222;
}
.upload-btn {
  border-radius: 8px;
  font-size: 1.05rem;
}
.files-toolbar {
  display: flex;
  gap: 16px;
  margin-bottom: 18px;
}
.search-input {
  width: 260px;
}
.status-select {
  width: 140px;
}
:deep(.el-table) {
  border-radius: 12px;
  overflow-x: auto;
  min-width: 100%;
  box-sizing: border-box;
  height: calc(100vh - 235px);
}
.files-empty {
  margin: 32px 0 0 0;
}
.pagination-container {
  margin-top: 20px;
  display: flex;
  justify-content: center;
  margin-bottom: 10px;
}

/* 添加导出按钮相关样式 */
:deep(.el-table .el-dropdown) {
  display: inline-flex;
  align-items: center;
  vertical-align: middle;
  margin-left: 8px;
}

:deep(.el-table .el-button--link) {
  display: inline-flex;
  align-items: center;
  height: 28px;
  padding: 0 8px;
  margin: 0 8px;
  vertical-align: middle;
}

:deep(.el-table .el-button--link .el-icon) {
  margin-left: 4px;
}

:deep(.el-table__body-wrapper) {
  overflow-y: auto;
}

:deep(.el-tag) {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  border-radius: 4px;
  font-size: 12px;
  font-weight: 500;
}
@media (max-width: 1200px) {
  .files-root {
    padding: 20px 24px 0 24px;
  }
  :deep(.el-table) {
    height: auto;
  }
}
@media (max-width: 992px) {
  .files-header {
    flex-direction: column;
    align-items: flex-start;
    gap: 12px;
  }
  .files-header-actions {
    width: 100%;
    flex-wrap: wrap;
    justify-content: flex-start;
    gap: 12px;
  }
  .files-toolbar {
    flex-direction: column;
    align-items: stretch;
    gap: 12px;
  }
  .search-input,
  .status-select {
    width: 100%;
  }
}
@media (max-width: 768px) {
  .files-root {
    padding: 16px 16px 0 16px;
  }
  .files-header-actions {
    gap: 8px;
  }
  .files-toolbar {
    margin-bottom: 12px;
  }
  .batch-delete-btn,
  .batch-export-btn,
  .upload-btn {
    width: 100%;
    justify-content: center;
  }
}
</style>