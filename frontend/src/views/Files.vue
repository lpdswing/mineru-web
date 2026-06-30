<template>
  <div class="files-root">
    <div class="files-layout">
      <aside class="folder-sidebar">
        <div class="folder-header">
          <span class="folder-title">文件夹</span>
          <el-button class="folder-add" link @click="createFolder">
            <el-icon><Plus /></el-icon>
          </el-button>
        </div>
        <button
          class="folder-item"
          :class="{ active: params.folderId === '' }"
          @click="selectFolder('')"
        >
          <el-icon><FolderOpened /></el-icon>
          <span>全部文件</span>
        </button>
        <button
          class="folder-item"
          :class="{ active: params.folderId === 'none' }"
          @click="selectFolder('none')"
        >
          <el-icon><FolderIcon /></el-icon>
          <span>未分类</span>
        </button>
        <div class="folder-list">
          <div
            v-for="folder in folders"
            :key="folder.id"
            class="folder-row"
            :class="{ active: params.folderId === String(folder.id) }"
            @click="selectFolder(String(folder.id))"
          >
            <div class="folder-row-main">
              <el-icon><FolderIcon /></el-icon>
              <span class="folder-name">{{ folder.name }}</span>
            </div>
            <el-dropdown trigger="click" @command="(command: string) => handleFolderCommand(command, folder)">
              <el-button class="folder-more" link @click.stop>
                <el-icon><MoreFilled /></el-icon>
              </el-button>
              <template #dropdown>
                <el-dropdown-menu>
                  <el-dropdown-item command="rename">重命名</el-dropdown-item>
                  <el-dropdown-item command="delete" divided>删除</el-dropdown-item>
                </el-dropdown-menu>
              </template>
            </el-dropdown>
          </div>
        </div>
      </aside>

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
            :loading="batchDeleting"
            :disabled="!multipleSelection.length || batchExporting"
          >
            <el-icon><Delete /></el-icon>
            <span>批量删除</span>
            <span v-if="multipleSelection.length" class="action-count">({{ multipleSelection.length }})</span>
          </el-button>
          <el-dropdown @command="handleBatchExport" :disabled="selectedExportableFiles.length === 0 || batchDeleting">
            <el-button type="default" :loading="batchExporting" :disabled="selectedExportableFiles.length === 0 || batchDeleting">
              <el-icon><Download /></el-icon>
              <span>批量导出</span>
              <span v-if="selectedExportableFiles.length" class="action-count">({{ selectedExportableFiles.length }})</span>
            </el-button>
            <template #dropdown>
              <el-dropdown-menu>
                <el-dropdown-item v-for="(name, format) in ExportFormatNames" :key="format" :command="format">
                  {{ name }}
                </el-dropdown-item>
              </el-dropdown-menu>
            </template>
          </el-dropdown>
          <el-button type="primary" @click="openUpload">
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
        >
          <template #prefix>
            <el-icon><Search /></el-icon>
          </template>
        </el-input>
        <el-select v-model="params.status" placeholder="全部状态" class="status-select" clearable>
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
          ref="tableRef"
          :data="files"
          v-if="files && files.length > 0 && !loading"
          row-key="id"
          @selection-change="handleSelectionChange"
          :header-cell-style="{ background: 'var(--bg-tertiary)', color: 'var(--text-primary)', fontWeight: 600 }"
        >
          <el-table-column type="selection" width="48" :reserve-selection="true" />
          <el-table-column prop="filename" label="文件名称" min-width="220">
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
          <el-table-column prop="size" label="大小" width="80">
            <template #default="{ row }">
              <span class="cell-text">{{ formatFileSize(row.size) }}</span>
            </template>
          </el-table-column>
          <el-table-column prop="uploadTime" label="上传时间" width="140">
            <template #default="{ row }">
              <span class="cell-text">{{ formatDateTime(row.upload_time) }}</span>
            </template>
          </el-table-column>
          <el-table-column prop="finish_at" label="解析完成时间" width="140">
            <template #default="{ row }">
              <span class="cell-text">{{ formatDateTime(row.finish_at) }}</span>
            </template>
          </el-table-column>
          <el-table-column prop="status" label="状态" width="90">
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
          <el-table-column label="进度" min-width="220">
            <template #default="{ row }">
              <div class="progress-cell">
                <div class="progress-head">
                  <span class="progress-title">{{ getProgressTitle(row) }}</span>
                  <span class="progress-value">{{ getProgressPercent(row) }}%</span>
                </div>
                <el-progress
                  :percentage="getProgressPercent(row)"
                  :status="getProgressStatus(row)"
                  :show-text="false"
                  :stroke-width="7"
                />
                <div class="progress-meta">
                  <span v-for="item in getProgressMeta(row)" :key="item" class="progress-meta-item">
                    {{ item }}
                  </span>
                  <span v-if="isProgressStale(row)" class="progress-meta-item warning">
                    {{ getStaleLabel(row) }}
                  </span>
                </div>
              </div>
            </template>
          </el-table-column>
          <el-table-column label="操作" width="270">
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
                <el-dropdown @command="(fmt: string) => handleExport(row, fmt as ExportFormat)" :disabled="row.status !== 'parsed'">
                  <el-button class="action-link" link :loading="exportingId === row.id" :disabled="row.status !== 'parsed'">
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
                <el-dropdown @command="(folderId: number | null) => moveFile(row, folderId)">
                  <el-button class="action-link" link>
                    移动 <el-icon class="el-icon--right"><ArrowDown /></el-icon>
                  </el-button>
                  <template #dropdown>
                    <el-dropdown-menu>
                      <el-dropdown-item :command="null" :disabled="!row.folder_id">未分类</el-dropdown-item>
                      <el-dropdown-item
                        v-for="folder in folders"
                        :key="folder.id"
                        :command="folder.id"
                        :disabled="row.folder_id === folder.id"
                      >
                        {{ folder.name }}
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
          <el-empty :description="emptyDescription">
            <el-button type="primary" @click="openUpload">
              <el-icon><Upload /></el-icon>
              上传文件
            </el-button>
            <el-button v-if="listLoadError" @click="fetchFiles">重试</el-button>
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
        />
      </div>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, reactive, watch, onMounted, onUnmounted, computed } from 'vue'
import { Upload, Delete, Search, Download, ArrowDown, Folder as FolderIcon, FolderOpened, MoreFilled, Plus } from '@element-plus/icons-vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { useRoute, useRouter } from 'vue-router'
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
import type { FileItem, ExportFormat, FolderItem } from '@/types/file'
import { ExportFormatNames } from '@/types/file'

const files = ref<FileItem[]>([])
const folders = ref<FolderItem[]>([])
const total = ref(0)
const loading = ref(false)
const listLoadError = ref(false)
const pollingTimer = ref<number | null>(null)
const searchTimer = ref<number | null>(null)
const POLLING_INTERVAL = 3000
const SEARCH_DEBOUNCE_MS = 300
const PARSE_STALE_AFTER_SECONDS = Number(import.meta.env.VITE_PARSE_STALE_AFTER_SECONDS || 600)

const params = reactive({
  page: 1,
  pageSize: 10,
  search: '',
  status: '',
  folderId: ''
})

const exportingId = ref<string>('')
const batchExporting = ref(false)
const batchDeleting = ref(false)
const multipleSelection = ref<FileItem[]>([])
const tableRef = ref<{ clearSelection: () => void } | null>(null)
const router = useRouter()
const route = useRoute()

const hasParsingFiles = computed(() => files.value.some(f => f.status === 'parsing'))
const selectedExportableFiles = computed(() => multipleSelection.value.filter(file => file.status === 'parsed'))
const emptyDescription = computed(() => {
  if (listLoadError.value) return '文件列表加载失败'
  if (params.search || params.status || params.folderId) return '没有匹配的文件'
  return '暂无文件'
})

const getStatusClass = (status: string) => {
  const map: Record<string, string> = {
    pending: 'status-pending',
    parsing: 'status-parsing',
    parsed: 'status-success',
    parse_failed: 'status-error'
  }
  return map[status] || 'status-pending'
}

const parseStageNames: Record<string, string> = {
  queued: '队列等待',
  fetching_source: '读取源文件',
  submitting_mineru: '提交 MinerU 任务',
  waiting_mineru: '等待 MinerU 状态',
  downloading_result: '下载解析结果',
  syncing_artifacts: '同步解析产物',
  postprocessing_popo: 'Popo 后处理',
  completed: '解析完成',
  failed: '解析失败'
}

const clampProgress = (value?: number | null) => {
  if (typeof value !== 'number' || Number.isNaN(value)) return 0
  return Math.max(0, Math.min(100, Math.round(value)))
}

const getProgressPercent = (file: FileItem) => {
  if (file.status === 'parsed') return 100
  return clampProgress(file.progress_percent)
}

const getProgressTitle = (file: FileItem) => {
  if (file.status === 'parsed') return '解析完成'
  if (file.status === 'parse_failed') return file.progress_message || '解析失败'
  return file.progress_message || parseStageNames[file.parse_stage || ''] || getStatusText(file.status)
}

const getProgressStatus = (file: FileItem): 'success' | 'exception' | 'warning' | undefined => {
  if (file.status === 'parsed') return 'success'
  if (file.status === 'parse_failed' || isProgressStale(file)) return 'exception'
  if (file.status === 'pending') return 'warning'
  return undefined
}

const shortTaskId = (taskId?: string | null) => {
  if (!taskId) return ''
  return taskId.length > 12 ? taskId.slice(-12) : taskId
}

const formatDuration = (milliseconds: number) => {
  const totalSeconds = Math.max(0, Math.floor(milliseconds / 1000))
  const hours = Math.floor(totalSeconds / 3600)
  const minutes = Math.floor((totalSeconds % 3600) / 60)
  const seconds = totalSeconds % 60
  if (hours > 0) return `${hours}h ${minutes}m`
  if (minutes > 0) return `${minutes}m ${seconds}s`
  return `${seconds}s`
}

const durationSince = (dateStr?: string | null) => {
  if (!dateStr) return ''
  const timestamp = new Date(dateStr).getTime()
  if (Number.isNaN(timestamp)) return ''
  return formatDuration(Date.now() - timestamp)
}

const durationBetween = (start?: string | null, end?: string | null) => {
  if (!start || !end) return ''
  const startTime = new Date(start).getTime()
  const endTime = new Date(end).getTime()
  if (Number.isNaN(startTime) || Number.isNaN(endTime)) return ''
  return formatDuration(endTime - startTime)
}

const estimateRemaining = (file: FileItem) => {
  if (file.status !== 'parsing' || !file.start_at) return ''
  const progress = getProgressPercent(file)
  if (progress <= 0 || progress >= 100) return ''
  const startTime = new Date(file.start_at).getTime()
  if (Number.isNaN(startTime)) return ''
  const elapsed = Date.now() - startTime
  const remaining = (elapsed / progress) * (100 - progress)
  return formatDuration(remaining)
}

const getProgressMeta = (file: FileItem) => {
  const meta: string[] = []
  if (file.mineru_task_status) meta.push(`MinerU: ${file.mineru_task_status}`)
  const taskId = shortTaskId(file.mineru_task_id)
  if (taskId) meta.push(`Task ${taskId}`)
  if (file.status === 'parsed') {
    const duration = durationBetween(file.start_at, file.finish_at)
    if (duration) meta.push(`总耗时 ${duration}`)
  } else if (file.status === 'pending') {
    const waiting = durationSince(file.upload_time)
    if (waiting) meta.push(`等待 ${waiting}`)
  } else if (file.start_at) {
    const elapsed = durationSince(file.start_at)
    if (elapsed) meta.push(`已耗时 ${elapsed}`)
    const remaining = estimateRemaining(file)
    if (remaining) meta.push(`约剩余 ${remaining}`)
  }
  const stageName = parseStageNames[file.parse_stage || '']
  if (stageName && stageName !== getProgressTitle(file)) meta.push(stageName)
  return meta
}

const isProgressStale = (file: FileItem) => {
  if (file.status !== 'parsing' || !file.last_heartbeat_at) return false
  const heartbeat = new Date(file.last_heartbeat_at).getTime()
  if (Number.isNaN(heartbeat)) return false
  return Date.now() - heartbeat > PARSE_STALE_AFTER_SECONDS * 1000
}

const getStaleLabel = (file: FileItem) => {
  const staleFor = durationSince(file.last_heartbeat_at)
  return staleFor ? `可能卡住 · ${staleFor} 无更新` : '可能卡住'
}

const openPreview = (file: FileItem) => {
  router.push({ 
    name: 'FilePreview', 
    params: { id: file.id },
    query: { page: params.page }
  })
}

const openUpload = () => {
  const query = params.folderId ? { folder_id: params.folderId } : undefined
  router.push({ path: '/upload', query })
}

const selectFolder = (folderId: string) => {
  if (params.folderId === folderId) return
  params.folderId = folderId
}

const fetchFolders = async () => {
  const result = await filesApi.getFolders()
  folders.value = result.folders
}

const createFolder = async () => {
  try {
    const { value } = await ElMessageBox.prompt('文件夹名称', '新建文件夹', {
      confirmButtonText: '确定',
      cancelButtonText: '取消',
      inputPattern: /^(?!\s*$).{1,128}$/,
      inputErrorMessage: '请输入 1-128 个字符'
    })
    const folder = await filesApi.createFolder(value)
    folders.value = [...folders.value, folder]
    params.folderId = String(folder.id)
    ElMessage.success('文件夹已创建')
  } catch (e) {}
}

const renameFolder = async (folder: FolderItem) => {
  try {
    const { value } = await ElMessageBox.prompt('文件夹名称', '重命名文件夹', {
      confirmButtonText: '确定',
      cancelButtonText: '取消',
      inputValue: folder.name,
      inputPattern: /^(?!\s*$).{1,128}$/,
      inputErrorMessage: '请输入 1-128 个字符'
    })
    const updated = await filesApi.renameFolder(folder.id, value)
    folders.value = folders.value.map(item => item.id === updated.id ? updated : item)
    ElMessage.success('文件夹已重命名')
  } catch (e) {}
}

const deleteFolder = async (folder: FolderItem) => {
  try {
    await ElMessageBox.confirm(`确定要删除文件夹“${folder.name}”吗？文件会移回未分类。`, '删除文件夹', {
      confirmButtonText: '确定',
      cancelButtonText: '取消',
      type: 'warning'
    })
    await filesApi.deleteFolder(folder.id)
    folders.value = folders.value.filter(item => item.id !== folder.id)
    if (params.folderId === String(folder.id)) {
      params.folderId = ''
    } else {
      fetchFiles()
    }
    ElMessage.success('文件夹已删除')
  } catch (e) {}
}

const handleFolderCommand = (command: string, folder: FolderItem) => {
  if (command === 'rename') {
    renameFolder(folder)
  } else if (command === 'delete') {
    deleteFolder(folder)
  }
}

const moveFile = async (file: FileItem, folderId: number | null) => {
  if ((file.folder_id ?? null) === folderId) return
  try {
    await filesApi.moveFileToFolder(file.id, folderId)
    ElMessage.success('文件已移动')
    fetchFiles()
  } catch (e) {}
}

const handleExport = async (file: FileItem, format: ExportFormat) => {
  if (!file || exportingId.value === file.id) return
  if (file.status !== 'parsed') {
    ElMessage.warning('解析完成后才能导出')
    return
  }
  exportingId.value = file.id
  try {
    const result = await filesApi.exportFile(file.id, format)
    if (result.status === 'success') {
      const response = await fetch(result.download_url)
      if (!response.ok) throw new Error('download failed')
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
  } catch (e) {
    ElMessage.error(`导出${ExportFormatNames[format]}失败`)
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

const clearSearchTimer = () => {
  if (searchTimer.value) {
    clearTimeout(searchTimer.value)
    searchTimer.value = null
  }
}

const updateFiles = (newFiles: FileItem[]) => {
  // 原地合并：存活行复用原对象引用（仅更新字段），新增行追加，删除行剔除。
  // 保留引用可避免轮询刷新时 el-table 丢失多选勾选。
  const existingById = new Map(files.value.map((file) => [file.id, file]))
  files.value = newFiles.map((newFile) => {
    const existing = existingById.get(newFile.id)
    if (existing) {
      Object.assign(existing, newFile)
      return existing
    }
    return newFile
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
      status: params.status,
      folder_id: params.folderId
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
      status: params.status,
      folder_id: params.folderId
    })
    files.value = result.files
    total.value = result.total
    listLoadError.value = false
  } catch (e) {
    files.value = []
    total.value = 0
    listLoadError.value = true
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
  } catch (e) {
    ElMessage.error('下载文件失败')
  }
}

const handleBatchDelete = async () => {
  if (!multipleSelection.value.length || batchDeleting.value || batchExporting.value) return
  ElMessageBox.confirm(
    `确定要删除选中的 ${multipleSelection.value.length} 个文件吗？`,
    '批量删除确认',
    { confirmButtonText: '确定', cancelButtonText: '取消', type: 'warning' }
  ).then(async () => {
    batchDeleting.value = true
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
      // 清掉 el-table 的预留选中（reserve-selection 会保留已删除行的 key）
      tableRef.value?.clearSelection()
      multipleSelection.value = []
      fetchFiles()
    } finally {
      batchDeleting.value = false
    }
  }).catch(() => {})
}

const handleBatchExport = async (format: ExportFormat) => {
  const exportableFiles = selectedExportableFiles.value
  if (!exportableFiles.length || batchExporting.value || batchDeleting.value) {
    ElMessage.warning('请选择已完成解析的文件')
    return
  }
  batchExporting.value = true
  let successCount = 0
  const failedFiles: string[] = []
  try {
    const zip = new JSZip()
    for (const file of exportableFiles) {
      try {
        const result = await filesApi.exportFile(file.id, format)
        if (result.status === 'success') {
          const response = await fetch(result.download_url)
          if (!response.ok) throw new Error('download failed')
          const content = await response.blob()
          zip.file(result.filename, content)
          successCount += 1
        }
      } catch (e) {
        failedFiles.push(file.filename)
      }
    }
    if (successCount === 0) {
      ElMessage.error('批量导出失败')
      return
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
    if (failedFiles.length > 0 || exportableFiles.length < multipleSelection.value.length) {
      const skippedCount = multipleSelection.value.length - exportableFiles.length
      ElMessage.warning(`成功导出 ${successCount} 个文件，${failedFiles.length + skippedCount} 个文件未导出`)
    } else {
      ElMessage.success(`批量导出${ExportFormatNames[format]}完成`)
    }
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

const scheduleSearch = () => {
  clearSearchTimer()
  searchTimer.value = window.setTimeout(() => {
    if (params.page !== 1) {
      params.page = 1
      return
    }
    fetchFiles()
  }, SEARCH_DEBOUNCE_MS)
}

onMounted(() => {
  const folderId = route.query.folder_id
  if (typeof folderId === 'string') {
    params.folderId = folderId
  }
  Promise.all([fetchFolders(), fetchFiles()]).then(() => {
    startPolling()
  })
})

onUnmounted(() => {
  stopPolling()
  clearSearchTimer()
})

watch([() => params.search, () => params.status, () => params.folderId], () => {
  scheduleSearch()
})

watch(() => route.query.folder_id, (folderId) => {
  const nextFolderId = typeof folderId === 'string' ? folderId : ''
  if (params.folderId !== nextFolderId) {
    params.folderId = nextFolderId
  }
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

.files-layout {
  width: 100%;
  height: 100%;
  display: flex;
  gap: 16px;
  overflow: hidden;
}

.folder-sidebar {
  width: 220px;
  flex-shrink: 0;
  background: var(--bg-primary);
  border: 1px solid var(--border-light);
  border-radius: var(--radius-lg);
  padding: 14px;
  display: flex;
  flex-direction: column;
  gap: 8px;
  overflow: hidden;
}

.folder-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 0 4px 8px;
  border-bottom: 1px solid var(--border-light);
  margin-bottom: 4px;
}

.folder-title {
  color: var(--text-primary);
  font-size: 14px;
  font-weight: 700;
}

.folder-add {
  color: var(--text-secondary) !important;
}

.folder-add:hover {
  color: var(--primary-color) !important;
}

.folder-item,
.folder-row {
  width: 100%;
  min-height: 36px;
  border: 0;
  border-radius: var(--radius-md);
  background: transparent;
  color: var(--text-secondary);
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 8px 10px;
  font-size: 13px;
  text-align: left;
  cursor: pointer;
  transition: background var(--transition-fast), color var(--transition-fast);
}

.folder-item:hover,
.folder-row:hover {
  background: var(--bg-tertiary);
  color: var(--text-primary);
}

.folder-item.active,
.folder-row.active {
  background: color-mix(in srgb, var(--primary-color) 12%, var(--bg-primary));
  color: var(--primary-color);
}

.folder-list {
  display: flex;
  flex-direction: column;
  gap: 4px;
  overflow-y: auto;
  min-height: 0;
}

.folder-row {
  justify-content: space-between;
}

.folder-row-main {
  min-width: 0;
  display: flex;
  align-items: center;
  gap: 8px;
}

.folder-name {
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.folder-more {
  color: var(--text-muted) !important;
  padding: 0 !important;
  opacity: 0;
}

.folder-row:hover .folder-more,
.folder-row.active .folder-more {
  opacity: 1;
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
  min-width: 0;
}

.file-name {
  font-weight: 500;
  color: var(--text-primary);
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
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

.progress-cell {
  display: flex;
  flex-direction: column;
  gap: 6px;
  min-width: 0;
}

.progress-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 10px;
}

.progress-title {
  color: var(--text-primary);
  font-size: 13px;
  font-weight: 600;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.progress-value {
  color: var(--primary-color);
  font-size: 12px;
  font-weight: 700;
  flex-shrink: 0;
}

.progress-meta {
  display: flex;
  align-items: center;
  gap: 6px;
  flex-wrap: wrap;
  color: var(--text-muted);
  font-size: 11px;
  line-height: 1.4;
}

.progress-meta-item {
  padding: 2px 6px;
  border-radius: 999px;
  background: var(--bg-tertiary);
  color: var(--text-secondary);
}

.progress-meta-item.warning {
  color: var(--danger-color);
  background: color-mix(in srgb, var(--danger-color) 10%, var(--bg-primary));
}

.action-cell {
  display: flex;
  align-items: center;
  gap: 6px;
  min-width: 0;
}

.action-cell .el-button {
  margin-left: 0 !important;
  padding: 0;
}

.action-cell .el-dropdown {
  flex-shrink: 0;
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

  .files-layout {
    flex-direction: column;
    overflow-y: auto;
  }

  .folder-sidebar {
    width: 100%;
    max-height: 220px;
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
