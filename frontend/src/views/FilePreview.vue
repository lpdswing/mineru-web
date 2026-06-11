<template>
  <div class="preview-wrapper">
    <!-- 侧边文件列表 -->
    <aside class="preview-sidebar" :class="{ collapsed: sidebarCollapsed }">
      <div class="sidebar-header">
        <div class="sidebar-title" v-show="!sidebarCollapsed">
          <el-icon><FolderOpened /></el-icon>
          <span>文件列表</span>
        </div>
        <el-button 
          class="collapse-btn" 
          link 
          @click="sidebarCollapsed = !sidebarCollapsed"
        >
          <el-icon :size="18">
            <component :is="sidebarCollapsed ? Expand : Fold" />
          </el-icon>
        </el-button>
      </div>
      
      <template v-if="!sidebarCollapsed">
        <el-input 
          v-model="fileSearch" 
          placeholder="搜索文件..." 
          size="small" 
          class="sidebar-search" 
          clearable
        >
          <template #prefix>
            <el-icon><Search /></el-icon>
          </template>
        </el-input>
        
        <el-scrollbar class="sidebar-list">
          <div 
            v-for="file in filteredFiles" 
            :key="file.id" 
            class="sidebar-file"
            :class="{ active: currentFile && file.id === currentFile.id }"
            @click="selectFile(file)"
          >
            <el-icon class="file-icon"><Document /></el-icon>
            <span class="file-name">{{ file.filename }}</span>
          </div>
        </el-scrollbar>
        
        <div class="sidebar-pagination">
          <el-pagination
            v-model:current-page="sidebarPage"
            v-model:page-size="sidebarPageSize"
            :total="sidebarTotal"
            :page-sizes="[10, 20, 50]"
            layout="prev, pager, next"
            size="small"
            :pager-count="3"
          />
        </div>
      </template>
    </aside>

    <!-- 主内容区 -->
    <main class="preview-main">
      <!-- 顶部工具栏 -->
      <header class="preview-header">
        <div class="header-left">
          <span class="current-file-name">{{ currentFile?.filename || '未选择文件' }}</span>
        </div>
        <div class="header-center">
          <div class="view-toggle">
            <button 
              class="toggle-btn" 
              :class="{ active: viewMode === 'origin' || viewMode === 'both' }"
              @click="handleViewMode('origin')"
            >
              <el-icon><Document /></el-icon>
              <span>原文件</span>
            </button>
            <button 
              class="toggle-btn" 
              :class="{ active: viewMode === 'markdown' || viewMode === 'both' }"
              @click="handleViewMode('markdown')"
            >
              <el-icon><EditPen /></el-icon>
              <span>Markdown</span>
            </button>
          </div>
        </div>
        <div class="header-right">
          <el-dropdown @command="handleExport">
            <el-button type="primary">
              <el-icon><Download /></el-icon>
              <span>下载</span>
              <el-icon class="el-icon--right"><ArrowDown /></el-icon>
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
      </header>

      <!-- 预览内容区 -->
      <div class="preview-content">
        <!-- 原文件预览 -->
        <div 
          v-if="viewMode !== 'markdown'" 
          class="preview-panel origin-panel"
          :class="{ 'full-width': viewMode === 'origin' }"
        >
          <div class="panel-content">
            <template v-if="showOrigin && currentFile">
              <template v-if="isPdf(currentFile.filename)">
                <iframe 
                  v-if="fileUrl" 
                  :src="fileUrl" 
                  class="pdf-frame"
                  ref="pdfFrame"
                  @load="handlePdfLoad"
                ></iframe>
              </template>
              <template v-else-if="isOffice(currentFile.filename)">
                <div v-if="loadingOffice" class="loading-state">
                  <el-icon class="is-loading" :size="32"><Loading /></el-icon>
                  <span>正在加载预览...</span>
                </div>
                <div v-else class="office-preview" v-html="officeContent"></div>
              </template>
              <template v-else-if="isImage(currentFile.filename)">
                <img :src="fileUrl" class="image-preview" />
              </template>
              <template v-else-if="isText(currentFile.filename)">
                <el-scrollbar>
                  <pre class="text-preview">{{ textContent }}</pre>
                </el-scrollbar>
              </template>
              <template v-else>
                <el-empty description="暂不支持该类型文件预览" :image-size="100" />
              </template>
            </template>
          </div>
        </div>

        <!-- Markdown预览 -->
        <div 
          v-if="viewMode !== 'origin'" 
          class="preview-panel markdown-panel"
          :class="{ 'full-width': viewMode === 'markdown' }"
        >
          <div class="panel-content">
            <div class="markdown-toolbar">
              <button
                v-for="(name, variant) in markdownVariantNames"
                :key="variant"
                class="markdown-tab"
                :class="{ active: markdownVariant === variant }"
                @click="handleMarkdownVariant(variant as MarkdownVariant)"
              >
                {{ name }}
              </button>
            </div>
            <div v-if="loading" class="loading-state">
              <el-icon class="is-loading" :size="32"><Loading /></el-icon>
              <span>加载中...</span>
            </div>
            <el-empty
              v-else-if="markdownVariant === 'popo' && !parsedContent"
              :description="popoStatus?.message || 'Popo 结果暂不可用'"
              :image-size="100"
            />
            <div v-else class="markdown-content" v-html="renderedContent"></div>
          </div>
        </div>
      </div>
    </main>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, onMounted, watch, nextTick } from 'vue'
import { useRoute } from 'vue-router'
import { ElMessage } from 'element-plus'
import { 
  FolderOpened, Document, Search, Download, ArrowDown, 
  EditPen, Expand, Fold, Loading 
} from '@element-plus/icons-vue'
import axios from 'axios'
import MarkdownIt from 'markdown-it'
import mk from 'markdown-it-katex'
import 'katex/dist/katex.min.css'
import mammoth from 'mammoth'
import * as XLSX from 'xlsx'
import { getUserId } from '@/utils/user'

const route = useRoute()
const md = MarkdownIt({ html: true, linkify: true, typographer: true }).use(mk)

interface FileItem {
  id: string
  filename: string
  size: number
  uploadTime: string
  status: string
}

type MarkdownVariant = 'markdown' | 'markdown_page' | 'popo'
type PopoStatusValue = 'not_available' | 'processing' | 'success' | 'failed' | 'skipped'

const sidebarCollapsed = ref(false)
const allFiles = ref<FileItem[]>([])
const sidebarPage = ref(1)
const sidebarPageSize = ref(10)
const sidebarTotal = ref(0)
const fileSearch = ref('')
const currentFile = ref<FileItem | null>(null)
const isReady = ref(false)

// 获取侧边栏文件列表
const fetchSidebarFiles = async () => {
  try {
    const res = await axios.get('/api/files', {
      params: { page: sidebarPage.value, page_size: sidebarPageSize.value, search: fileSearch.value },
      headers: { 'X-User-Id': getUserId() }
    })
    allFiles.value = res.data.files
    sidebarTotal.value = res.data.total
  } catch (e) {
    ElMessage.error('获取文件列表失败')
    allFiles.value = []
    sidebarTotal.value = 0
  }
}

// 根据ID获取单个文件信息
const loadFileById = async (fileId: string) => {
  try {
    const res = await axios.get(`/api/files/${fileId}`, {
      headers: { 'X-User-Id': getUserId() }
    })
    if (res.data) {
      currentFile.value = res.data
    }
  } catch (e) {
    console.error('获取文件信息失败', e)
  }
}

// 监听分页变化
watch(sidebarPage, () => {
  if (isReady.value) {
    fetchSidebarFiles()
  }
})

watch([sidebarPageSize, fileSearch], () => {
  if (isReady.value) {
    sidebarPage.value = 1
    fetchSidebarFiles()
  }
})

onMounted(async () => {
  const fileId = route.params.id as string
  const pageFromQuery = Number(route.query.page) || 1
  
  // 设置初始页码
  sidebarPage.value = pageFromQuery
  
  if (fileId) {
    // 加载指定文件
    await loadFileById(fileId)
  }
  
  // 加载对应页的文件列表
  await fetchSidebarFiles()
  
  // 如果没有指定文件，选中第一个
  if (!currentFile.value && allFiles.value.length > 0) {
    currentFile.value = allFiles.value[0]
  }

  // 初始化完成
  await nextTick()
  isReady.value = true

  // 如果初始视图模式需要显示 markdown，立即加载内容
  if (viewMode.value !== 'origin' && currentFile.value) {
    await fetchParsedContent()
  }
})

const filteredFiles = computed(() => allFiles.value)

const selectFile = (file: FileItem) => {
  currentFile.value = file
  page.value = 1
  markdownVariant.value = 'markdown'
  popoStatus.value = null
  parsedContent.value = ''
  loading.value = false
  hasMore.value = true
  if (viewMode.value !== 'origin') {
    fetchParsedContent()
  }
}

const showOrigin = ref(true)
const isImage = (name?: string) => name ? /\.(png|jpe?g|gif|bmp|webp)$/i.test(name) : false
const isText = (name?: string) => name ? /\.(txt|md|json|log)$/i.test(name) : false
const isWord = (name?: string) => name ? /\.(doc|docx)$/i.test(name) : false
const isExcel = (name?: string) => name ? /\.(xls|xlsx)$/i.test(name) : false
const isOffice = (name?: string) => name ? /\.(doc|docx|xls|xlsx)$/i.test(name) : false
const isPdf = (name?: string) => name ? /\.pdf$/i.test(name) : false

const page = ref(1)
const parsedContent = ref('')
const loading = ref(false)
const hasMore = ref(true)
const markdownVariant = ref<MarkdownVariant>('markdown')
const popoStatus = ref<{ status: PopoStatusValue; message?: string } | null>(null)
const markdownVariantNames: Record<MarkdownVariant, string> = {
  markdown: '原始 Markdown',
  markdown_page: '按页 Markdown',
  popo: 'Popo 增强'
}

const fetchParsedContent = async () => {
  if (!currentFile.value) return
  loading.value = true
  try {
    const res = await axios.get(`/api/files/${currentFile.value.id}/parsed_content`, {
      params: { variant: markdownVariant.value },
      headers: { 'X-User-Id': getUserId() }
    })
    parsedContent.value = res.data || ''
    popoStatus.value = null
  } catch (e) {
    parsedContent.value = ''
    if (markdownVariant.value === 'popo') {
      await fetchPopoStatus()
    } else {
      ElMessage.error('获取解析内容失败')
    }
  } finally {
    loading.value = false
  }
}

const fetchPopoStatus = async () => {
  if (!currentFile.value) {
    popoStatus.value = { status: 'not_available', message: '' }
    return
  }
  try {
    const res = await axios.get(`/api/files/${currentFile.value.id}/popo/status`, {
      headers: { 'X-User-Id': getUserId() }
    })
    popoStatus.value = res.data || { status: 'not_available', message: '' }
  } catch (e) {
    popoStatus.value = { status: 'not_available', message: '' }
  }
}

const handleMarkdownVariant = async (variant: MarkdownVariant) => {
  if (markdownVariant.value === variant) return
  markdownVariant.value = variant
  await fetchParsedContent()
}

const viewMode = ref<'both' | 'origin' | 'markdown'>('both')

const handleViewMode = (mode: 'origin' | 'markdown') => {
  viewMode.value = viewMode.value === mode ? 'both' : mode
}

watch(viewMode, (newMode) => {
  if (newMode !== 'origin') fetchParsedContent()
})

const ExportFormats = {
  MARKDOWN: 'markdown',
  MARKDOWN_PAGE: 'markdown_page',
  MARKDOWN_POPO: 'markdown_popo'
} as const
type ExportFormat = typeof ExportFormats[keyof typeof ExportFormats]
const ExportFormatNames: Record<ExportFormat, string> = {
  [ExportFormats.MARKDOWN]: 'Markdown',
  [ExportFormats.MARKDOWN_PAGE]: 'Markdown带页码',
  [ExportFormats.MARKDOWN_POPO]: 'Popo Markdown'
}

const handleExport = async (format: ExportFormat) => {
  if (!currentFile.value) return
  try {
    const res = await axios.get(`/api/files/${currentFile.value.id}/export`, {
      params: { format },
      headers: { 'X-User-Id': getUserId() }
    })
    if (res.data.status === 'success') {
      const response = await fetch(res.data.download_url)
      const blob = await response.blob()
      const url = window.URL.createObjectURL(blob)
      const link = document.createElement('a')
      link.href = url
      link.download = res.data.filename
      document.body.appendChild(link)
      link.click()
      window.URL.revokeObjectURL(url)
      document.body.removeChild(link)
      ElMessage.success(`导出${ExportFormatNames[format]}成功`)
    } else {
      ElMessage.error(`导出失败`)
    }
  } catch (e) {
    ElMessage.error(`导出失败`)
  }
}

const fileUrl = ref('')
const textContent = ref('')
const officeContent = ref('')
const loadingOffice = ref(false)

const fetchFileUrl = async () => {
  if (!currentFile.value) return
  try {
    const res = await axios.get(`/api/files/${currentFile.value.id}/download_url`, {
      headers: { 'X-User-Id': getUserId() }
    })
    fileUrl.value = res.data.url
  } catch (e) {
    fileUrl.value = ''
    textContent.value = ''
    officeContent.value = ''
  }
}

const previewOfficeFile = async () => {
  if (!currentFile.value || !fileUrl.value) return
  loadingOffice.value = true
  try {
    const response = await fetch(fileUrl.value)
    const blob = await response.blob()
    if (isWord(currentFile.value.filename)) {
      const arrayBuffer = await blob.arrayBuffer()
      const result = await mammoth.convertToHtml({ arrayBuffer })
      officeContent.value = result.value
    } else if (isExcel(currentFile.value.filename)) {
      const arrayBuffer = await blob.arrayBuffer()
      const workbook = XLSX.read(arrayBuffer, { type: 'array' })
      const firstSheet = workbook.Sheets[workbook.SheetNames[0]]
      officeContent.value = XLSX.utils.sheet_to_html(firstSheet)
    }
  } catch (e) {
    ElMessage.error('预览 Office 文件失败')
    officeContent.value = ''
  } finally {
    loadingOffice.value = false
  }
}

const fetchTextContent = async () => {
  if (!fileUrl.value) return
  try {
    const res = await axios.get(fileUrl.value)
    textContent.value = res.data
  } catch (e) {
    textContent.value = ''
  }
}

watch(currentFile, async (newFile) => {
  if (!newFile) return
  fileUrl.value = ''
  textContent.value = ''
  officeContent.value = ''
  await fetchFileUrl()
  if (isText(newFile.filename)) await fetchTextContent()
  else if (isOffice(newFile.filename)) await previewOfficeFile()
})

const pdfFrame = ref<HTMLIFrameElement | null>(null)
const currentPdfPage = ref(1)

const handlePdfLoad = () => {
  if (!pdfFrame.value) return
  pdfFrame.value.contentWindow?.addEventListener('scroll', handlePdfScroll)
}

const handlePdfScroll = async () => {
  if (!pdfFrame.value) return
  const iframe = pdfFrame.value
  const scrollTop = iframe.contentWindow?.scrollY || 0
  const pageHeight = iframe.contentWindow?.innerHeight || 0
  const newPage = Math.floor(scrollTop / pageHeight) + 1
  if (newPage !== currentPdfPage.value) {
    currentPdfPage.value = newPage
    await loadMarkdownByPage()
  }
}

const loadMarkdownByPage = async () => {
  if (!currentFile.value || loading.value) return
  loading.value = true
  try {
    const res = await axios.get(`/api/files/${currentFile.value.id}/parsed_content`, {
      params: { variant: markdownVariant.value },
      headers: { 'X-User-Id': getUserId() }
    })
    parsedContent.value = res.data || ''
    popoStatus.value = null
    hasMore.value = false
  } catch (e) {
    parsedContent.value = ''
    if (markdownVariant.value === 'popo') {
      await fetchPopoStatus()
    } else {
      ElMessage.error('加载内容失败')
    }
  } finally {
    loading.value = false
  }
}

const renderedContent = computed(() => md.render(parsedContent.value || ''))
</script>

<style scoped>
.preview-wrapper {
  display: flex;
  min-height: 100vh;
  background: var(--bg-secondary);
}

/* 侧边栏 */
.preview-sidebar {
  width: 260px;
  background: var(--bg-primary);
  border-right: 1px solid var(--border-light);
  display: flex;
  flex-direction: column;
  transition: width var(--transition-normal);
  flex-shrink: 0;
}

.preview-sidebar.collapsed {
  width: 48px;
}

.sidebar-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 16px;
  border-bottom: 1px solid var(--border-light);
}

.sidebar-title {
  display: flex;
  align-items: center;
  gap: 8px;
  font-weight: 600;
  color: var(--text-primary);
}

.collapse-btn {
  color: var(--text-muted);
}

.sidebar-search {
  margin: 12px 16px;
}

.sidebar-list {
  flex: 1;
  padding: 0 8px;
}

.sidebar-file {
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 10px 12px;
  border-radius: var(--radius-md);
  cursor: pointer;
  transition: all var(--transition-fast);
  margin-bottom: 4px;
}

.sidebar-file:hover {
  background: var(--bg-tertiary);
}

.sidebar-file.active {
  background: rgb(99 102 241 / 0.1);
  color: var(--primary-color);
}

.file-icon {
  color: var(--text-muted);
  flex-shrink: 0;
}

.sidebar-file.active .file-icon {
  color: var(--primary-color);
}

.file-name {
  font-size: 13px;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

.sidebar-pagination {
  padding: 12px 16px;
  border-top: 1px solid var(--border-light);
}

/* 主内容区 */
.preview-main {
  flex: 1;
  display: flex;
  flex-direction: column;
  min-width: 0;
}

.preview-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 12px 24px;
  background: var(--bg-primary);
  border-bottom: 1px solid var(--border-light);
  gap: 16px;
}

.header-left {
  flex: 1;
  min-width: 0;
}

.current-file-name {
  font-weight: 600;
  color: var(--text-primary);
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

.view-toggle {
  display: flex;
  background: var(--bg-tertiary);
  border-radius: var(--radius-md);
  padding: 4px;
}

.toggle-btn {
  display: flex;
  align-items: center;
  gap: 6px;
  padding: 8px 16px;
  border: none;
  background: transparent;
  border-radius: var(--radius-sm);
  cursor: pointer;
  font-size: 13px;
  color: var(--text-muted);
  transition: all var(--transition-fast);
}

.toggle-btn:hover {
  color: var(--text-primary);
}

.toggle-btn.active {
  background: var(--bg-primary);
  color: var(--primary-color);
  box-shadow: var(--shadow-sm);
}

/* 预览内容 */
.preview-content {
  flex: 1;
  display: flex;
  gap: 1px;
  background: var(--border-light);
  overflow: hidden;
}

.preview-panel {
  flex: 1;
  background: var(--bg-primary);
  display: flex;
  flex-direction: column;
  min-width: 0;
  transition: flex var(--transition-normal);
}

.preview-panel.full-width {
  flex: 1 0 100%;
}

.panel-content {
  flex: 1;
  overflow: auto;
  padding: 24px;
}

.pdf-frame {
  width: 100%;
  height: calc(100vh - 120px);
  border: none;
}

.image-preview {
  max-width: 100%;
  height: auto;
  border-radius: var(--radius-md);
}

.text-preview {
  font-family: 'Monaco', 'Menlo', monospace;
  font-size: 13px;
  line-height: 1.6;
  color: var(--text-primary);
  white-space: pre-wrap;
  margin: 0;
}

.loading-state {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  gap: 12px;
  padding: 60px;
  color: var(--text-muted);
}

/* Markdown样式 */
.markdown-toolbar {
  display: inline-flex;
  align-items: center;
  gap: 2px;
  padding: 3px;
  margin-bottom: 16px;
  background: var(--bg-tertiary);
  border-radius: var(--radius-md);
}

.markdown-tab {
  min-width: 92px;
  height: 30px;
  padding: 0 12px;
  border: none;
  background: transparent;
  border-radius: var(--radius-sm);
  color: var(--text-muted);
  cursor: pointer;
  font-size: 13px;
  transition: all var(--transition-fast);
}

.markdown-tab:hover {
  color: var(--text-primary);
}

.markdown-tab.active {
  background: var(--bg-primary);
  color: var(--primary-color);
  box-shadow: var(--shadow-sm);
}

.markdown-content {
  font-size: 15px;
  line-height: 1.8;
  color: var(--text-primary);
}

.markdown-content :deep(h1),
.markdown-content :deep(h2),
.markdown-content :deep(h3) {
  margin-top: 1.5em;
  margin-bottom: 0.5em;
  font-weight: 600;
  color: var(--text-primary);
}

.markdown-content :deep(h1) { font-size: 1.75em; border-bottom: 1px solid var(--border-light); padding-bottom: 0.3em; }
.markdown-content :deep(h2) { font-size: 1.5em; }
.markdown-content :deep(h3) { font-size: 1.25em; }

.markdown-content :deep(p) { margin: 1em 0; }

.markdown-content :deep(code) {
  background: var(--bg-tertiary);
  padding: 2px 6px;
  border-radius: 4px;
  font-family: 'Monaco', monospace;
  font-size: 0.9em;
}

.markdown-content :deep(pre) {
  background: var(--bg-tertiary);
  padding: 16px;
  border-radius: var(--radius-md);
  overflow-x: auto;
}

.markdown-content :deep(pre code) {
  background: transparent;
  padding: 0;
}

.markdown-content :deep(table) {
  width: 100%;
  border-collapse: collapse;
  margin: 1em 0;
}

.markdown-content :deep(th),
.markdown-content :deep(td) {
  border: 1px solid var(--border-color);
  padding: 10px 14px;
  text-align: left;
}

.markdown-content :deep(th) {
  background: var(--bg-tertiary);
  font-weight: 600;
}

.markdown-content :deep(img) {
  max-width: 100%;
  border-radius: var(--radius-md);
}

.markdown-content :deep(blockquote) {
  margin: 1em 0;
  padding: 0 1em;
  border-left: 4px solid var(--primary-color);
  color: var(--text-secondary);
}

.markdown-content :deep(.katex-display) {
  overflow-x: auto;
  margin: 1em 0;
}

.markdown-content :deep(.katex-mathml) {
  display: none !important;
}

@media (max-width: 1024px) {
  .preview-sidebar {
    position: fixed;
    left: 0;
    top: 0;
    bottom: 0;
    z-index: 100;
    box-shadow: var(--shadow-xl);
  }
  
  .preview-sidebar.collapsed {
    transform: translateX(-100%);
    width: 260px;
  }
  
  .preview-content {
    flex-direction: column;
  }
  
  .preview-panel {
    min-height: 50vh;
  }
}

@media (max-width: 768px) {
  .preview-header {
    flex-wrap: wrap;
    padding: 12px 16px;
  }
  
  .header-center {
    order: 3;
    width: 100%;
    margin-top: 12px;
  }
  
  .view-toggle {
    width: 100%;
    justify-content: center;
  }
  
  .panel-content {
    padding: 16px;
  }
}
</style>
