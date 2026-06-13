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
              :class="{ active: viewMode === 'origin' }"
              @click="setViewMode('origin')"
            >
              <el-icon><Document /></el-icon>
              <span>原文件</span>
            </button>
            <button 
              class="toggle-btn" 
              :class="{ active: viewMode === 'both' }"
              @click="setViewMode('both')"
            >
              <el-icon><Document /></el-icon>
              <span>左右对照</span>
            </button>
            <button 
              class="toggle-btn" 
              :class="{ active: viewMode === 'markdown' }"
              @click="setViewMode('markdown')"
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
          v-if="viewMode !== 'markdown' && markdownVariant !== 'compare'"
          class="preview-panel origin-panel"
          :class="{ 'full-width': viewMode === 'origin' }"
        >
          <div class="panel-content">
            <div v-if="loadingOrigin" class="loading-state">
              <el-icon class="is-loading" :size="32"><Loading /></el-icon>
              <span>正在加载原文件...</span>
            </div>
            <el-empty v-else-if="originLoadError" :description="originLoadError" :image-size="100">
              <el-button type="primary" @click="reloadOriginPreview">重试</el-button>
            </el-empty>
            <template v-else-if="showOrigin && currentFile">
              <template v-if="isPdf(currentFile.filename)">
                <PdfSourceViewer
                  v-if="fileUrl"
                  ref="pdfViewerRef"
                  :url="fileUrl"
                  :source-map="sourceMap"
                  :active-page="activeSourcePage"
                  :active-block-id="activeSourceBlockId"
                  @page-change="handlePdfPageChange"
                  @block-select="handlePdfBlockSelect"
                />
                <el-empty v-else description="原文件暂不可预览" :image-size="100" />
              </template>
              <template v-else-if="isOffice(currentFile.filename)">
                <div v-if="loadingOffice" class="loading-state">
                  <el-icon class="is-loading" :size="32"><Loading /></el-icon>
                  <span>正在加载预览...</span>
                </div>
                <div v-else class="office-preview" v-html="officeContent"></div>
              </template>
              <template v-else-if="isImage(currentFile.filename)">
                <img v-if="fileUrl" :src="fileUrl" class="image-preview" />
                <el-empty v-else description="原文件暂不可预览" :image-size="100" />
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
          :class="{ 'full-width': viewMode === 'markdown' || markdownVariant === 'compare' }"
        >
          <div class="panel-content">
            <div v-if="isPdf(currentFile?.filename)" class="pdf-review-bar">
              <div class="pdf-review-title">
                <span>{{ markdownVariant === 'compare' ? 'OCR / Popo 对照' : 'Markdown 预览' }}</span>
                <small>
                  {{ markdownVariant === 'compare' ? '原始 OCR 结果 / Popo 增强结果' : `Page ${activeSourcePage} / ${pageSections.length || 0}` }}
                </small>
              </div>
              <div class="pdf-review-actions">
                <button
                  v-for="(name, variant) in pdfMarkdownVariantNames"
                  :key="variant"
                  class="pdf-review-mode"
                  :class="{ active: markdownVariant === variant }"
                  @click="handleMarkdownVariant(variant)"
                >
                  {{ name }}
                </button>
                <span v-if="markdownVariant !== 'compare'" class="source-trace-chip">{{ sourceTraceLabel }}</span>
              </div>
            </div>
            <div v-else class="markdown-toolbar">
              <button
                v-for="(name, variant) in markdownVariantNames"
                :key="variant"
                class="markdown-tab"
                :class="{ active: markdownVariant === variant }"
                @click="handleMarkdownVariant(variant as MarkdownViewVariant)"
              >
                {{ name }}
              </button>
            </div>
            <div v-if="loading" class="loading-state">
              <el-icon class="is-loading" :size="32"><Loading /></el-icon>
              <span>加载中...</span>
            </div>
            <el-empty v-else-if="markdownLoadError" :description="markdownLoadError" :image-size="100">
              <el-button type="primary" @click="fetchParsedContent">重试</el-button>
            </el-empty>
            <div v-else-if="markdownVariant === 'compare'" class="markdown-compare">
              <section class="compare-column">
                <div class="compare-header">
                  <span>原始 OCR Markdown</span>
                  <small>MinerU 原始解析结果</small>
                </div>
                <div
                  v-if="compareMarkdownContent"
                  class="markdown-content compare-content"
                  v-html="compareRenderedMarkdown"
                ></div>
                <el-empty v-else description="Markdown 结果暂不可用" :image-size="100" />
              </section>
              <section class="compare-column">
                <div class="compare-header">
                  <span>Popo 增强 Markdown</span>
                  <small>{{ comparePopoStatusLabel }}</small>
                </div>
                <div
                  v-if="comparePopoContent"
                  class="markdown-content compare-content"
                  v-html="compareRenderedPopo"
                ></div>
                <el-empty v-else :description="comparePopoEmptyDescription" :image-size="100" />
              </section>
            </div>
            <el-empty
              v-else-if="markdownVariant === 'popo' && !parsedContent"
              :description="popoEmptyDescription"
              :image-size="100"
            />
            <div
              v-else-if="showPageLinkedMarkdown"
              ref="markdownScrollRef"
              class="markdown-pages markdown-reader-pages"
            >
              <section
                v-for="section in pageTraceSections"
                :key="section.page"
                class="markdown-page-section"
                :class="{ active: section.page === activeSourcePage }"
                :data-page="section.page"
              >
                <button
                  class="markdown-page-meta reader-page-marker"
                  type="button"
                  @click="handleMarkdownPageClick(section)"
                >
                  <span>Page {{ section.page }}</span>
                  <small>{{ sourceStatusForPage(section.page) }}</small>
                </button>
                <div v-if="section.traceBlocks.length" class="markdown-source-list">
                  <article
                    v-for="trace in section.traceBlocks"
                    :key="trace.block.id"
                    class="markdown-reader-block"
                    :class="{
                      active: trace.block.id === activeSourceBlockId,
                      'no-source-pill': trace.block.type === 'page_number'
                    }"
                    :data-source-block-id="trace.block.id"
                    tabindex="0"
                    role="button"
                    @click="handleMarkdownBlockClick(section, trace)"
                    @keydown.enter.prevent="handleMarkdownBlockClick(section, trace)"
                    @keydown.space.prevent="handleMarkdownBlockClick(section, trace)"
                  >
                    <div class="markdown-content trace-content" v-html="trace.html"></div>
                    <span v-if="trace.block.type !== 'page_number'" class="reader-source-pill">
                      P{{ section.page }} · {{ trace.block.type }}
                    </span>
                  </article>
                </div>
                <div v-else class="markdown-content page-content" v-html="section.html"></div>
              </section>
            </div>
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
import api from '@/api'
import { filesApi } from '@/api/files'
import PdfSourceViewer from '@/components/PdfSourceViewer.vue'
import {
  ExportFormatNames,
  type ExportFormat,
  type MarkdownVariant,
  type PopoStatus,
  type PopoStatusValue,
  type SourceBlock,
  type SourceMap
} from '@/types/file'

const route = useRoute()
const md = MarkdownIt({ html: true, linkify: true, typographer: true }).use(mk)

interface FileItem {
  id: string
  filename: string
  size: number
  uploadTime: string
  status: string
}

interface MarkdownPageSection {
  page: number
  markdown: string
  html: string
}

interface MarkdownTraceBlock {
  block: SourceBlock
  excerpt: string
  html: string
  index: number
  score: number
}

interface MarkdownTraceSection extends MarkdownPageSection {
  traceBlocks: MarkdownTraceBlock[]
}

interface PdfSourceViewerRef {
  scrollToPage: (pageNumber: number) => Promise<void> | void
  scrollToBlock: (pageNumber: number, blockId: string) => Promise<void> | void
}

type MarkdownViewVariant = MarkdownVariant | 'compare'

const sidebarCollapsed = ref(false)
const allFiles = ref<FileItem[]>([])
const sidebarPage = ref(1)
const sidebarPageSize = ref(10)
const sidebarTotal = ref(0)
const fileSearch = ref('')
const currentFile = ref<FileItem | null>(null)
const isReady = ref(false)
const pdfViewerRef = ref<PdfSourceViewerRef | null>(null)
const markdownScrollRef = ref<HTMLElement | null>(null)
const sourceMap = ref<SourceMap>({ pages: [] })
const sourceMapLoading = ref(false)
const activeSourcePage = ref(1)
const activeSourceBlockId = ref('')
const currentPdfPage = ref(1)
let sourceMapRequestSeq = 0

// 获取侧边栏文件列表
const fetchSidebarFiles = async () => {
  try {
    const res = await api.get('/files', {
      params: { page: sidebarPage.value, page_size: sidebarPageSize.value, search: fileSearch.value }
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
    const res = await api.get(`/files/${fileId}`)
    if (res.data) {
      currentFile.value = res.data
    }
  } catch (e) {
    ElMessage.error('获取文件信息失败')
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

  if (currentFile.value) {
    markdownVariant.value = preferredMarkdownVariant(currentFile.value)
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
  markdownVariant.value = preferredMarkdownVariant(file)
  popoStatus.value = null
  parsedContent.value = ''
  markdownLoadError.value = ''
  originLoadError.value = ''
  loading.value = false
  hasMore.value = true
  sourceMap.value = { pages: [] }
  activeSourcePage.value = 1
  activeSourceBlockId.value = ''
  currentPdfPage.value = 1
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
const preferredMarkdownVariant = (file: FileItem): MarkdownViewVariant => {
  return isPdf(file.filename) ? 'markdown_page' : 'markdown'
}

const page = ref(1)
const parsedContent = ref('')
const loading = ref(false)
const markdownLoadError = ref('')
const hasMore = ref(true)
let markdownRequestSeq = 0
const markdownVariant = ref<MarkdownViewVariant>('markdown')
const popoStatus = ref<PopoStatus | null>(null)
const compareMarkdownContent = ref('')
const comparePopoContent = ref('')
const comparePopoStatus = ref<PopoStatus | null>(null)
const markdownVariantNames: Record<MarkdownViewVariant, string> = {
  markdown: '原始 Markdown',
  markdown_page: '按页 Markdown',
  popo: 'Popo 增强',
  compare: '对比'
}
const pdfMarkdownVariantNames: Record<'markdown_page' | 'compare', string> = {
  markdown_page: '溯源阅读',
  compare: 'OCR-Popo 对照'
}
const popoStatusNames: Record<PopoStatusValue, string> = {
  not_available: 'Popo 结果暂不可用',
  processing: 'Popo 结果生成中',
  success: 'Popo 结果可用',
  failed: 'Popo 处理失败',
  skipped: 'Popo 已跳过'
}
const popoEmptyDescription = computed(() => {
  if (!popoStatus.value) return 'Popo 结果暂不可用'
  return popoStatus.value.message || popoStatusNames[popoStatus.value.status]
})
const comparePopoEmptyDescription = computed(() => {
  if (!comparePopoStatus.value) return 'Popo 结果暂不可用'
  return comparePopoStatus.value.message || popoStatusNames[comparePopoStatus.value.status]
})
const comparePopoStatusLabel = computed(() => {
  if (comparePopoContent.value) return '可对比'
  if (!comparePopoStatus.value) return '未加载'
  return popoStatusNames[comparePopoStatus.value.status]
})
const sourceBlockTotal = computed(() => {
  return sourceMap.value.pages.reduce((total, item) => total + item.blocks.length, 0)
})
const sourceTraceLabel = computed(() => {
  if (sourceMapLoading.value) return '溯源加载中'
  if (sourceBlockTotal.value) return `${sourceBlockTotal.value} 个 bbox`
  return '暂无 bbox'
})
const sourcePageFor = (page: number) => {
  return sourceMap.value.pages.find((item) => item.page === page)
}
const sourceStatusForPage = (page: number) => {
  const count = sourcePageFor(page)?.blocks.length || 0
  return count ? `${count} 个 bbox` : '无 bbox'
}
const parseMarkdownPages = (content: string): MarkdownPageSection[] => {
  const matches = Array.from(content.matchAll(/^#\s+Page\s+(\d+)\s*$/gim))
  if (!matches.length) return []

  return matches
    .map((match, index) => {
      const page = Number(match[1])
      const start = match.index ?? 0
      const bodyStart = start + match[0].length
      const nextStart = matches[index + 1]?.index ?? content.length
      const markdown = content.slice(bodyStart, nextStart).trim()
      return {
        page,
        markdown,
        html: md.render(markdown || ' ')
      }
    })
    .filter((section) => Number.isFinite(section.page))
}
const pageSections = computed(() => parseMarkdownPages(parsedContent.value || ''))
const showPageLinkedMarkdown = computed(() => {
  return markdownVariant.value === 'markdown_page' && pageSections.value.length > 0
})
const normalizeTraceText = (value: string) => {
  return value
    .replace(/!\[[^\]]*]\([^)]+\)/g, ' ')
    .replace(/[^\p{L}\p{N}\s]+/gu, ' ')
    .replace(/\s+/g, ' ')
    .trim()
    .toLowerCase()
}
const splitMarkdownChunks = (markdown: string) => {
  const chunks: string[] = []
  const current: string[] = []
  const flush = () => {
    const chunk = current.join('\n').trim()
    if (chunk) chunks.push(chunk)
    current.length = 0
  }

  markdown.replace(/\r\n/g, '\n').split('\n').forEach((line) => {
    if (!line.trim()) {
      flush()
      return
    }
    if (/^#{1,6}\s+/.test(line.trim())) {
      flush()
      chunks.push(line.trim())
      return
    }
    current.push(line)
  })
  flush()
  return chunks
}
const scoreTraceMatch = (markdown: string, sourceText: string) => {
  const markdownText = normalizeTraceText(markdown)
  const blockText = normalizeTraceText(sourceText)
  if (!markdownText || !blockText) return 0
  const sample = blockText.slice(0, Math.min(96, blockText.length))
  const head = markdownText.slice(0, Math.min(96, markdownText.length))
  if (sample && markdownText.includes(sample)) return sample.length + 120
  if (head && blockText.includes(head)) return head.length + 80

  const blockWords = blockText.split(' ').filter((word) => word.length > 2)
  if (!blockWords.length) return 0
  const markdownWords = new Set(markdownText.split(' ').filter((word) => word.length > 2))
  const overlap = blockWords.filter((word) => markdownWords.has(word)).length
  return overlap / blockWords.length
}
const traceExcerptForBlock = (block: SourceBlock, chunks: string[], usedChunks: Set<number>) => {
  let bestIndex = -1
  let bestScore = 0
  chunks.forEach((chunk, index) => {
    const score = scoreTraceMatch(chunk, block.text) - (usedChunks.has(index) ? 0.25 : 0)
    if (score > bestScore) {
      bestScore = score
      bestIndex = index
    }
  })
  if (bestIndex >= 0 && bestScore > 0) {
    usedChunks.add(bestIndex)
    return { excerpt: chunks[bestIndex], score: bestScore }
  }
  return { excerpt: block.text, score: 0 }
}
const traceBlocksForSection = (section: MarkdownPageSection): MarkdownTraceBlock[] => {
  const blocks = sourcePageFor(section.page)?.blocks || []
  const chunks = splitMarkdownChunks(section.markdown)
  const usedChunks = new Set<number>()
  return blocks.map((block, index) => {
    const trace = traceExcerptForBlock(block, chunks, usedChunks)
    return {
      block,
      excerpt: trace.excerpt,
      html: md.render(trace.excerpt || block.text || ' '),
      index: index + 1,
      score: trace.score
    }
  })
}
const pageTraceSections = computed<MarkdownTraceSection[]>(() => {
  return pageSections.value.map((section) => ({
    ...section,
    traceBlocks: traceBlocksForSection(section)
  }))
})
const traceSectionForPage = (page: number) => {
  return pageTraceSections.value.find((section) => section.page === page)
}
const findBestBlockForSection = (section: MarkdownPageSection): SourceBlock | null => {
  const tracedBlock = traceSectionForPage(section.page)?.traceBlocks[0]?.block
  if (tracedBlock) return tracedBlock
  const blocks = sourcePageFor(section.page)?.blocks || []
  if (!blocks.length) return null
  const sectionText = normalizeTraceText(section.markdown)
  if (!sectionText) return blocks[0]

  let bestBlock: SourceBlock | null = null
  let bestScore = 0
  for (const block of blocks) {
    const blockText = normalizeTraceText(block.text)
    if (!blockText) continue
    const sample = blockText.slice(0, Math.min(80, blockText.length))
    const head = sectionText.slice(0, Math.min(80, sectionText.length))
    let score = 0
    if (sample && sectionText.includes(sample)) {
      score = sample.length
    } else if (head && blockText.includes(head)) {
      score = head.length
    } else {
      score = blockText
        .split(' ')
        .filter((word) => word.length > 2 && sectionText.includes(word))
        .length
    }
    if (score > bestScore) {
      bestScore = score
      bestBlock = block
    }
  }
  return bestBlock || blocks[0]
}
const scrollMarkdownPageIntoView = async (page: number) => {
  if (!showPageLinkedMarkdown.value) return
  await nextTick()
  const target = markdownScrollRef.value?.querySelector(`[data-page="${page}"]`) as HTMLElement | null
  target?.scrollIntoView({ behavior: 'smooth', block: 'nearest' })
}
const scrollMarkdownBlockIntoView = async (blockId: string) => {
  if (!showPageLinkedMarkdown.value || !blockId) return
  await nextTick()
  const target = markdownScrollRef.value?.querySelector(`[data-source-block-id="${blockId}"]`) as HTMLElement | null
  target?.scrollIntoView({ behavior: 'smooth', block: 'center' })
}
const handleMarkdownPageClick = async (section: MarkdownPageSection) => {
  const block = findBestBlockForSection(section)
  currentPdfPage.value = section.page
  activeSourcePage.value = section.page
  activeSourceBlockId.value = block?.id || ''
  if (block) {
    await pdfViewerRef.value?.scrollToBlock(section.page, block.id)
  } else {
    await pdfViewerRef.value?.scrollToPage(section.page)
  }
}
const handleMarkdownBlockClick = async (section: MarkdownTraceSection, trace: MarkdownTraceBlock) => {
  currentPdfPage.value = section.page
  activeSourcePage.value = section.page
  activeSourceBlockId.value = trace.block.id
  await pdfViewerRef.value?.scrollToBlock(section.page, trace.block.id)
}
const handlePdfBlockSelect = (page: number, blockId: string) => {
  currentPdfPage.value = page
  activeSourcePage.value = page
  activeSourceBlockId.value = blockId
  void scrollMarkdownBlockIntoView(blockId)
}
const handlePdfPageChange = (page: number) => {
  const pageChanged = activeSourcePage.value !== page
  currentPdfPage.value = page
  activeSourcePage.value = page
  if (pageChanged) {
    activeSourceBlockId.value = sourcePageFor(page)?.blocks[0]?.id || ''
  }
  if (activeSourceBlockId.value) {
    void scrollMarkdownBlockIntoView(activeSourceBlockId.value)
  } else {
    void scrollMarkdownPageIntoView(page)
  }
}

const isLatestMarkdownRequest = (seq: number, fileId: string, variant: MarkdownViewVariant) => {
  return seq === markdownRequestSeq
    && currentFile.value?.id === fileId
    && markdownVariant.value === variant
}

const fetchParsedContent = async () => {
  if (!currentFile.value) return
  if (markdownVariant.value === 'compare') {
    await fetchCompareContent()
    return
  }
  const fileId = currentFile.value.id
  const variant = markdownVariant.value as MarkdownVariant
  const seq = ++markdownRequestSeq
  loading.value = true
  markdownLoadError.value = ''
  try {
    const data = await filesApi.getParsedContent(fileId, variant)
    if (!isLatestMarkdownRequest(seq, fileId, variant)) return
    parsedContent.value = data || ''
    popoStatus.value = null
  } catch (e) {
    if (!isLatestMarkdownRequest(seq, fileId, variant)) return
    parsedContent.value = ''
    if (variant === 'popo') {
      await fetchPopoStatus(fileId, seq, variant)
    } else {
      markdownLoadError.value = '解析内容暂不可用或加载失败'
      ElMessage.error('获取解析内容失败')
    }
  } finally {
    if (isLatestMarkdownRequest(seq, fileId, variant)) {
      loading.value = false
    }
  }
}

const fetchPopoStatus = async (
  fileId = currentFile.value?.id,
  seq = markdownRequestSeq,
  variant: MarkdownViewVariant = markdownVariant.value
) => {
  if (!fileId) {
    popoStatus.value = { status: 'not_available', message: '' }
    return
  }
  try {
    const res = await filesApi.getPopoStatus(fileId)
    if (!isLatestMarkdownRequest(seq, fileId, variant)) return
    popoStatus.value = res || { status: 'not_available', message: '' }
  } catch (e) {
    if (!isLatestMarkdownRequest(seq, fileId, variant)) return
    popoStatus.value = { status: 'not_available', message: '' }
  }
}

const fetchVariantContent = async (fileId: string, variant: MarkdownVariant) => {
  return await filesApi.getParsedContent(fileId, variant)
}

const fetchCompareContent = async () => {
  if (!currentFile.value) return
  const fileId = currentFile.value.id
  const variant: MarkdownViewVariant = 'compare'
  const seq = ++markdownRequestSeq
  loading.value = true
  markdownLoadError.value = ''
  compareMarkdownContent.value = ''
  comparePopoContent.value = ''
  comparePopoStatus.value = null
  try {
    const [markdownResult, popoResult] = await Promise.allSettled([
      fetchVariantContent(fileId, 'markdown'),
      fetchVariantContent(fileId, 'popo')
    ])
    if (!isLatestMarkdownRequest(seq, fileId, variant)) return

    compareMarkdownContent.value = markdownResult.status === 'fulfilled' ? markdownResult.value : ''
    if (popoResult.status === 'fulfilled') {
      comparePopoContent.value = popoResult.value
    } else {
      try {
        const statusRes = await filesApi.getPopoStatus(fileId)
        if (!isLatestMarkdownRequest(seq, fileId, variant)) return
        comparePopoStatus.value = statusRes || { status: 'not_available', message: '' }
      } catch (e) {
        if (!isLatestMarkdownRequest(seq, fileId, variant)) return
        comparePopoStatus.value = { status: 'not_available', message: '' }
      }
    }
  } finally {
    if (isLatestMarkdownRequest(seq, fileId, variant)) {
      loading.value = false
    }
  }
}

const handleMarkdownVariant = async (variant: MarkdownViewVariant) => {
  if (markdownVariant.value === variant) return
  markdownVariant.value = variant
  await fetchParsedContent()
}

const viewMode = ref<'both' | 'origin' | 'markdown'>('both')

const setViewMode = (mode: 'both' | 'origin' | 'markdown') => {
  viewMode.value = mode
}

watch(viewMode, (newMode) => {
  if (newMode !== 'origin') fetchParsedContent()
})

const handleExport = async (format: ExportFormat) => {
  if (!currentFile.value) return
  if (currentFile.value.status !== 'parsed') {
    ElMessage.warning('解析完成后才能导出')
    return
  }
  try {
    const res = await filesApi.exportFile(currentFile.value.id, format)
    if (res.status === 'success') {
      const response = await fetch(res.download_url)
      if (!response.ok) throw new Error('download failed')
      const blob = await response.blob()
      const url = window.URL.createObjectURL(blob)
      const link = document.createElement('a')
      link.href = url
      link.download = res.filename
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
const loadingOrigin = ref(false)
const loadingOffice = ref(false)
const originLoadError = ref('')

const fetchFileUrl = async () => {
  if (!currentFile.value) return
  loadingOrigin.value = true
  originLoadError.value = ''
  try {
    const res = await filesApi.getDownloadUrl(currentFile.value.id)
    fileUrl.value = res.url
  } catch (e) {
    fileUrl.value = ''
    textContent.value = ''
    officeContent.value = ''
    originLoadError.value = '获取原文件地址失败'
  } finally {
    loadingOrigin.value = false
  }
}

const fetchSourceMap = async () => {
  const file = currentFile.value
  const seq = ++sourceMapRequestSeq
  if (!file || !isPdf(file.filename)) {
    sourceMap.value = { pages: [] }
    sourceMapLoading.value = false
    return
  }

  sourceMapLoading.value = true
  try {
    const data = await filesApi.getSourceMap(file.id)
    if (seq !== sourceMapRequestSeq || currentFile.value?.id !== file.id) return
    sourceMap.value = data || { pages: [] }
    if (!activeSourceBlockId.value) {
      const activePageSource = sourceMap.value.pages.find((item) => item.page === activeSourcePage.value)
      activeSourceBlockId.value = activePageSource?.blocks[0]?.id || sourceMap.value.pages[0]?.blocks[0]?.id || ''
    }
  } catch (e) {
    if (seq !== sourceMapRequestSeq || currentFile.value?.id !== file.id) return
    sourceMap.value = { pages: [] }
  } finally {
    if (seq === sourceMapRequestSeq && currentFile.value?.id === file.id) {
      sourceMapLoading.value = false
    }
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
    originLoadError.value = '预览 Office 文件失败，可下载原文件后查看'
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
    originLoadError.value = '文本预览加载失败'
  }
}

const reloadOriginPreview = async () => {
  if (!currentFile.value) return
  fileUrl.value = ''
  textContent.value = ''
  officeContent.value = ''
  originLoadError.value = ''
  activeSourcePage.value = 1
  activeSourceBlockId.value = ''
  currentPdfPage.value = 1
  if (isPdf(currentFile.value.filename)) {
    loadingOrigin.value = true
    fileUrl.value = filesApi.getContentUrl(currentFile.value.id)
    await fetchSourceMap()
    loadingOrigin.value = false
  } else {
    sourceMap.value = { pages: [] }
    await fetchFileUrl()
  }
  if (isText(currentFile.value.filename)) await fetchTextContent()
  else if (isOffice(currentFile.value.filename)) await previewOfficeFile()
}

watch(currentFile, async (newFile) => {
  if (!newFile) return
  fileUrl.value = ''
  textContent.value = ''
  officeContent.value = ''
  originLoadError.value = ''
  await reloadOriginPreview()
})

const renderedContent = computed(() => md.render(parsedContent.value || ''))
const compareRenderedMarkdown = computed(() => md.render(compareMarkdownContent.value || ''))
const compareRenderedPopo = computed(() => md.render(comparePopoContent.value || ''))
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
  width: calc(100% - 32px);
  margin: 12px 16px;
  box-sizing: border-box;
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
  background: var(--primary-tint);
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
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 2px;
  padding: 3px;
  margin-bottom: 16px;
  max-width: 100%;
  background: var(--bg-tertiary);
  border-radius: var(--radius-md);
}

.pdf-review-bar {
  position: sticky;
  top: -24px;
  z-index: 3;
  display: flex;
  align-items: center;
  justify-content: space-between;
  flex-wrap: wrap;
  gap: 12px;
  margin: -24px -24px 18px;
  padding: 14px 24px 12px;
  border-bottom: 1px solid var(--border-light);
  background: color-mix(in srgb, var(--bg-primary) 94%, transparent);
  backdrop-filter: blur(14px);
}

.pdf-review-title {
  min-width: 0;
  display: flex;
  flex-direction: column;
  gap: 2px;
}

.pdf-review-title span {
  color: var(--text-primary);
  font-size: 14px;
  font-weight: 700;
}

.pdf-review-title small {
  color: var(--text-muted);
  font-size: 12px;
}

.pdf-review-actions {
  display: flex;
  align-items: center;
  flex-wrap: wrap;
  gap: 8px;
  margin-left: auto;
}

.pdf-review-mode {
  height: 28px;
  padding: 0 12px;
  border: 1px solid transparent;
  border-radius: var(--radius-sm);
  background: transparent;
  color: var(--text-muted);
  cursor: pointer;
  font-size: 12px;
  font-weight: 600;
  white-space: nowrap;
  transition: background var(--transition-fast), border-color var(--transition-fast), color var(--transition-fast);
}

.pdf-review-mode:hover {
  color: var(--text-primary);
  background: color-mix(in srgb, var(--bg-tertiary) 72%, transparent);
}

.pdf-review-mode.active {
  border-color: var(--border-light);
  background: var(--bg-primary);
  color: var(--primary-color);
}

.source-trace-chip {
  margin-left: auto;
  padding: 0 10px;
  height: 26px;
  display: inline-flex;
  align-items: center;
  border: 1px solid var(--border-light);
  border-radius: var(--radius-sm);
  background: color-mix(in srgb, var(--bg-primary) 86%, transparent);
  color: var(--text-muted);
  font-size: 12px;
  white-space: nowrap;
}

.pdf-review-actions .source-trace-chip {
  margin-left: 2px;
}

.markdown-tab {
  flex: 0 1 auto;
  min-width: 88px;
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

.markdown-pages {
  display: flex;
  flex-direction: column;
  gap: 26px;
}

.markdown-reader-pages {
  max-width: 760px;
  margin: 0 auto;
}

.markdown-page-section {
  position: relative;
  padding-left: 18px;
  border-left: 1px solid var(--border-light);
  transition: border-color var(--transition-fast);
}

.markdown-page-section.active {
  border-left-color: color-mix(in srgb, var(--primary-color) 58%, var(--border-light));
}

.markdown-page-meta {
  width: 100%;
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  margin-bottom: 8px;
  padding: 0 2px;
  border: none;
  background: transparent;
  cursor: pointer;
}

.markdown-page-meta span {
  color: var(--text-primary);
  font-size: 13px;
  font-weight: 600;
}

.reader-page-marker {
  position: sticky;
  top: -24px;
  z-index: 1;
  min-height: 30px;
  border-radius: var(--radius-sm);
  color: var(--text-muted);
}

.reader-page-marker:hover {
  color: var(--text-primary);
}

.markdown-page-meta small {
  min-width: 0;
  color: var(--text-muted);
  font-size: 12px;
  text-align: right;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.markdown-source-list {
  display: flex;
  flex-direction: column;
  gap: 2px;
}

.markdown-reader-block {
  position: relative;
  display: block;
  width: 100%;
  padding: 8px 74px 8px 14px;
  border: 1px solid transparent;
  border-left: 2px solid transparent;
  border-radius: var(--radius-sm);
  background: transparent;
  color: var(--text-primary);
  cursor: pointer;
  outline: none;
  transition: border-color var(--transition-fast), box-shadow var(--transition-fast), background var(--transition-fast);
}

.markdown-reader-block:hover,
.markdown-reader-block:focus-visible {
  border-color: color-mix(in srgb, var(--primary-color) 22%, transparent);
  border-left-color: color-mix(in srgb, var(--primary-color) 42%, var(--border-light));
  background: color-mix(in srgb, var(--primary-tint) 18%, transparent);
}

.markdown-reader-block.active {
  border-color: color-mix(in srgb, var(--primary-color) 30%, var(--border-light));
  border-left-color: color-mix(in srgb, var(--primary-color) 82%, var(--border-light));
  background: color-mix(in srgb, var(--primary-tint) 30%, var(--bg-primary));
  box-shadow: 0 8px 22px rgb(0 0 0 / 4%);
}

.markdown-reader-block.no-source-pill {
  padding-right: 14px;
}

.reader-source-pill {
  position: absolute;
  top: 10px;
  right: 10px;
  max-width: 58px;
  height: 20px;
  padding: 0 7px;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  overflow: hidden;
  border: 1px solid var(--border-light);
  border-radius: 999px;
  background: color-mix(in srgb, var(--bg-primary) 82%, transparent);
  color: var(--text-muted);
  font-size: 11px;
  line-height: 1;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.markdown-reader-block.active .reader-source-pill {
  border-color: color-mix(in srgb, var(--primary-color) 36%, var(--border-light));
  color: var(--primary-color);
  background: var(--bg-primary);
}

.trace-content {
  font-size: 14px;
  line-height: 1.72;
}

.trace-content :deep(h1),
.trace-content :deep(h2),
.trace-content :deep(h3) {
  margin-top: 0.25em;
  font-size: 1.06em;
}

.trace-content :deep(p),
.trace-content :deep(ul),
.trace-content :deep(ol) {
  margin: 0.45em 0;
}

.trace-content :deep(:first-child) {
  margin-top: 0;
}

.trace-content :deep(:last-child) {
  margin-bottom: 0;
}

.page-content {
  padding: 6px 16px 16px;
}

.markdown-compare {
  display: grid;
  grid-template-columns: minmax(0, 1fr) minmax(0, 1fr);
  gap: 16px;
  height: calc(100vh - 190px);
  min-height: 420px;
  overflow: hidden;
}

.compare-column {
  display: flex;
  flex-direction: column;
  min-width: 0;
  min-height: 0;
  border: 1px solid var(--border-light);
  border-radius: var(--radius-md);
  background: var(--bg-primary);
  overflow: hidden;
}

.compare-header {
  display: flex;
  align-items: baseline;
  justify-content: space-between;
  gap: 12px;
  padding: 10px 14px;
  border-bottom: 1px solid var(--border-light);
  background: var(--bg-secondary);
}

.compare-header span {
  font-size: 14px;
  font-weight: 600;
  color: var(--text-primary);
}

.compare-header small {
  min-width: 0;
  color: var(--text-muted);
  font-size: 12px;
  text-align: right;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.compare-content {
  flex: 1;
  min-height: 0;
  overflow: auto;
  padding: 16px;
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
  .preview-content {
    flex-direction: column;
  }
  
  .preview-panel {
    min-height: 50vh;
  }

  .markdown-compare {
    grid-template-columns: 1fr;
    height: auto;
    min-height: 0;
    overflow: visible;
  }

  .compare-column {
    min-height: 360px;
  }
}

@media (max-width: 768px) {
  .preview-sidebar {
    position: fixed;
    left: 0;
    top: 0;
    bottom: 0;
    z-index: 100;
    box-shadow: var(--shadow-xl);
  }

  .preview-sidebar.collapsed {
    width: 48px;
  }

  .preview-main {
    padding-left: 48px;
  }

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
