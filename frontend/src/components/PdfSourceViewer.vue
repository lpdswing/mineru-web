<template>
  <div class="pdf-source-viewer">
    <div class="pdf-source-toolbar">
      <div class="pdf-source-title">
        <span>PDF</span>
        <small>{{ pageLabel }}</small>
      </div>
      <div class="pdf-source-actions">
        <button class="icon-btn" type="button" title="缩小" :disabled="zoom <= 0.75" @click="setZoom(zoom - 0.1)">
          <el-icon><ZoomOut /></el-icon>
        </button>
        <button class="icon-btn" type="button" title="适合宽度" @click="setZoom(1)">
          <el-icon><Aim /></el-icon>
        </button>
        <button class="icon-btn" type="button" title="放大" :disabled="zoom >= 1.6" @click="setZoom(zoom + 0.1)">
          <el-icon><ZoomIn /></el-icon>
        </button>
        <button class="icon-btn" type="button" title="重新加载" @click="loadDocument">
          <el-icon><Refresh /></el-icon>
        </button>
      </div>
    </div>

    <div ref="scrollRef" class="pdf-source-scroll" @scroll="handleScroll">
      <div v-if="loading" class="pdf-source-state">正在加载 PDF...</div>
      <div v-else-if="error" class="pdf-source-state error">{{ error }}</div>
      <template v-else>
        <section
          v-for="page in pages"
          :key="page.pageNumber"
          :ref="(el) => setPageRef(el, page.pageNumber)"
          class="pdf-page-shell"
          :class="{ active: page.pageNumber === activePage }"
        >
          <div class="pdf-page-number">Page {{ page.pageNumber }}</div>
          <div class="pdf-page-canvas-wrap" :style="{ width: `${page.width}px`, height: `${page.height}px` }">
            <canvas :ref="(el) => setCanvasRef(el, page.pageNumber)" class="pdf-page-canvas" />
            <div class="pdf-source-layer">
              <button
                v-for="block in blocksForPage(page.pageNumber)"
                :key="block.id"
                :ref="(el) => setBlockRef(el, block.id)"
                class="source-box"
                type="button"
                :data-source-block-id="block.id"
                :class="{
                  visible: page.pageNumber === activePage || block.id === activeBlockId,
                  active: block.id === activeBlockId
                }"
                :style="blockStyle(block, page)"
                :title="blockTitle(block)"
                @click.stop="handleSourceBlockClick(page.pageNumber, block)"
              />
            </div>
          </div>
        </section>
      </template>
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed, nextTick, onBeforeUnmount, ref, shallowRef, watch } from 'vue'
import { Aim, Refresh, ZoomIn, ZoomOut } from '@element-plus/icons-vue'
import * as pdfjsLib from 'pdfjs-dist'
import type { PDFDocumentProxy, PDFPageProxy, RenderTask } from 'pdfjs-dist/types/src/display/api'
import pdfWorkerUrl from 'pdfjs-dist/build/pdf.worker.mjs?url'
import type { SourceBlock, SourceMap, SourcePage } from '@/types/file'
import { sourceTypeLabel } from '@/utils/sourceTypes'

pdfjsLib.GlobalWorkerOptions.workerSrc = `${pdfWorkerUrl}?module=1`

interface RenderedPage {
  pageNumber: number
  width: number
  height: number
  sourceWidth: number
  sourceHeight: number
  pdfPage: PDFPageProxy
}

interface PageGeometry {
  pageNumber: number
  sourceWidth: number
  sourceHeight: number
}

const props = defineProps<{
  url: string
  sourceMap?: SourceMap | null
  activePage?: number
  activeBlockId?: string
}>()

const emit = defineEmits<{
  'page-change': [page: number]
  'block-select': [page: number, blockId: string]
}>()

const scrollRef = ref<HTMLElement | null>(null)
const pages = shallowRef<RenderedPage[]>([])
const loading = ref(false)
const error = ref('')
const zoom = ref(1)
const currentPage = ref(1)
const pdfDoc = shallowRef<PDFDocumentProxy | null>(null)
const canvasRefs = new Map<number, HTMLCanvasElement>()
const pageRefs = new Map<number, HTMLElement>()
const blockRefs = new Map<string, HTMLElement>()
const renderTasks = new Map<number, RenderTask>()
let loadToken = 0

const activePage = computed(() => props.activePage || currentPage.value)
const sourcePages = computed(() => props.sourceMap?.pages || [])
const sourceBlockCount = computed(() => sourcePages.value.reduce((total, page) => total + page.blocks.length, 0))
const pageLabel = computed(() => {
  const total = pages.value.length
  const trace = sourceBlockCount.value ? `${sourceBlockCount.value} 个溯源框` : '暂无 bbox'
  return total ? `第 ${activePage.value} / ${total} 页 · ${trace}` : trace
})

const pageSource = (pageNumber: number): SourcePage | undefined => {
  return sourcePages.value.find((page) => page.page === pageNumber)
}

const blocksForPage = (pageNumber: number): SourceBlock[] => {
  return pageSource(pageNumber)?.blocks || []
}

const setCanvasRef = (el: unknown, pageNumber: number) => {
  if (el instanceof HTMLCanvasElement) {
    canvasRefs.set(pageNumber, el)
  }
}

const setPageRef = (el: unknown, pageNumber: number) => {
  if (el instanceof HTMLElement) {
    pageRefs.set(pageNumber, el)
  }
}

const setBlockRef = (el: unknown, blockId: string) => {
  if (el instanceof HTMLElement) {
    blockRefs.set(blockId, el)
  }
}

const cleanupRenderTasks = () => {
  renderTasks.forEach((task) => task.cancel())
  renderTasks.clear()
}

const destroyDocument = async () => {
  cleanupRenderTasks()
  const doc = pdfDoc.value
  pdfDoc.value = null
  if (doc) await doc.destroy()
}

const renderPage = async (page: RenderedPage, token: number) => {
  const canvas = canvasRefs.get(page.pageNumber)
  if (!canvas || token !== loadToken) return
  const context = canvas.getContext('2d', { alpha: false })
  if (!context) return

  const ratio = window.devicePixelRatio || 1
  const viewport = page.pdfPage.getViewport({ scale: page.width / page.sourceWidth })
  canvas.width = Math.floor(page.width * ratio)
  canvas.height = Math.floor(page.height * ratio)
  canvas.style.width = `${page.width}px`
  canvas.style.height = `${page.height}px`
  context.setTransform(ratio, 0, 0, ratio, 0, 0)

  const renderTask = page.pdfPage.render({ canvasContext: context, viewport })
  renderTasks.set(page.pageNumber, renderTask)
  try {
    await renderTask.promise
  } catch (e) {
    if (String((e as Error).name) !== 'RenderingCancelledException') throw e
  } finally {
    renderTasks.delete(page.pageNumber)
  }
}

const loadDocument = async () => {
  if (!props.url) return
  const token = ++loadToken
  loading.value = true
  error.value = ''
  pages.value = []
  canvasRefs.clear()
  pageRefs.clear()
  blockRefs.clear()
  await destroyDocument()

  try {
    const sourceUrl = new URL(props.url, window.location.href).toString()
    const doc = await pdfjsLib.getDocument({ url: sourceUrl, withCredentials: true }).promise
    if (token !== loadToken) {
      await doc.destroy()
      return
    }
    pdfDoc.value = doc
    const containerWidth = scrollRef.value?.clientWidth || 760
    const targetWidth = Math.max(320, Math.min(980, containerWidth - 48)) * zoom.value
    const nextPages: RenderedPage[] = []

    for (let pageNumber = 1; pageNumber <= doc.numPages; pageNumber += 1) {
      const pdfPage = await doc.getPage(pageNumber)
      const baseViewport = pdfPage.getViewport({ scale: 1 })
      const scale = targetWidth / baseViewport.width
      const viewport = pdfPage.getViewport({ scale })
      nextPages.push({
        pageNumber,
        width: viewport.width,
        height: viewport.height,
        sourceWidth: baseViewport.width,
        sourceHeight: baseViewport.height,
        pdfPage
      })
    }

    if (token !== loadToken) return
    pages.value = nextPages
    currentPage.value = 1
    loading.value = false
    await nextTick()
    for (const page of nextPages) {
      await renderPage(page, token)
    }
  } catch (e) {
    if (token === loadToken) {
      const message = e instanceof Error && e.message ? `：${e.message}` : ''
      error.value = `PDF 加载失败${message}`
    }
  } finally {
    if (token === loadToken) {
      loading.value = false
    }
  }
}

const setZoom = (nextZoom: number) => {
  zoom.value = Math.min(1.6, Math.max(0.75, Number(nextZoom.toFixed(2))))
}

const blockStyle = (block: SourceBlock, page: PageGeometry) => {
  const sourcePage = pageSource(page.pageNumber)
  const sourceWidth = sourcePage?.width || page.sourceWidth
  const sourceHeight = sourcePage?.height || page.sourceHeight
  const [x0, y0, x1, y1] = block.bbox
  const left = Math.min(x0, x1)
  const top = Math.min(y0, y1)
  const width = Math.abs(x1 - x0)
  const height = Math.abs(y1 - y0)

  return {
    left: `${(left / sourceWidth) * 100}%`,
    top: `${(top / sourceHeight) * 100}%`,
    width: `${(width / sourceWidth) * 100}%`,
    height: `${(height / sourceHeight) * 100}%`
  }
}

const blockTitle = (block: SourceBlock) => {
  const text = block.text.length > 80 ? `${block.text.slice(0, 80)}...` : block.text
  return `${sourceTypeLabel(block.type)}: ${text}`
}

const scrollToPage = async (pageNumber: number) => {
  await nextTick()
  const scroller = scrollRef.value
  const page = pageRefs.get(pageNumber)
  if (!scroller || !page) return
  const scrollerRect = scroller.getBoundingClientRect()
  const pageRect = page.getBoundingClientRect()
  scroller.scrollTo({
    top: Math.max(0, scroller.scrollTop + pageRect.top - scrollerRect.top - 8),
    behavior: 'smooth'
  })
}

const scrollToBlock = async (pageNumber: number, blockId: string) => {
  await nextTick()
  const scroller = scrollRef.value
  const block = blockRefs.get(blockId)
  if (!scroller || !block) {
    await scrollToPage(pageNumber)
    return
  }
  const scrollerRect = scroller.getBoundingClientRect()
  const blockRect = block.getBoundingClientRect()
  scroller.scrollTo({
    top: Math.max(0, scroller.scrollTop + blockRect.top - scrollerRect.top - scroller.clientHeight * 0.35),
    behavior: 'smooth'
  })
}

const handleSourceBlockClick = (pageNumber: number, block: SourceBlock) => {
  currentPage.value = pageNumber
  emit('block-select', pageNumber, block.id)
}

const handleScroll = () => {
  const scroller = scrollRef.value
  if (!scroller || !pages.value.length) return
  const scrollerTop = scroller.getBoundingClientRect().top
  const probeTop = scrollerTop + scroller.clientHeight * 0.35
  let nextPage = currentPage.value
  let nearestDistance = Number.POSITIVE_INFINITY

  pageRefs.forEach((el, pageNumber) => {
    const distance = Math.abs(el.getBoundingClientRect().top - probeTop)
    if (distance < nearestDistance) {
      nearestDistance = distance
      nextPage = pageNumber
    }
  })

  if (nextPage !== currentPage.value) {
    currentPage.value = nextPage
    emit('page-change', nextPage)
  }
}

watch(() => props.url, loadDocument, { immediate: true })
watch(zoom, loadDocument)

onBeforeUnmount(() => {
  loadToken += 1
  void destroyDocument()
})

defineExpose({ scrollToPage, scrollToBlock })
</script>

<style scoped>
.pdf-source-viewer {
  height: calc(100vh - 120px);
  min-height: 420px;
  display: flex;
  flex-direction: column;
  overflow: hidden;
  border: 1px solid var(--border-light);
  border-radius: var(--radius-lg);
  background: var(--bg-secondary);
}

.pdf-source-toolbar {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  padding: 10px 12px;
  border-bottom: 1px solid var(--border-light);
  background: color-mix(in srgb, var(--bg-primary) 88%, transparent);
}

.pdf-source-title {
  min-width: 0;
  display: flex;
  flex-direction: column;
  gap: 2px;
}

.pdf-source-title span {
  color: var(--text-primary);
  font-size: 13px;
  font-weight: 600;
}

.pdf-source-title small {
  color: var(--text-muted);
  font-size: 12px;
  white-space: nowrap;
}

.pdf-source-actions {
  display: flex;
  align-items: center;
  gap: 4px;
  flex-shrink: 0;
}

.icon-btn {
  width: 30px;
  height: 30px;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  border: 1px solid transparent;
  border-radius: var(--radius-sm);
  color: var(--text-secondary);
  background: transparent;
  cursor: pointer;
  transition: all var(--transition-fast);
}

.icon-btn:hover:not(:disabled) {
  color: var(--text-primary);
  background: var(--bg-tertiary);
}

.icon-btn:disabled {
  cursor: default;
  opacity: 0.35;
}

.pdf-source-scroll {
  flex: 1;
  min-height: 0;
  overflow: auto;
  padding: 18px;
  background:
    linear-gradient(90deg, color-mix(in srgb, var(--bg-secondary) 94%, #000 6%) 1px, transparent 1px),
    linear-gradient(color-mix(in srgb, var(--bg-secondary) 94%, #000 6%) 1px, transparent 1px),
    var(--bg-secondary);
  background-size: 28px 28px;
}

.pdf-source-state {
  min-height: 360px;
  display: flex;
  align-items: center;
  justify-content: center;
  color: var(--text-muted);
  font-size: 14px;
}

.pdf-source-state.error {
  color: var(--danger-color);
}

.pdf-page-shell {
  width: fit-content;
  margin: 0 auto 18px;
  transition: filter var(--transition-fast), transform var(--transition-fast);
}

.pdf-page-shell.active {
  filter: drop-shadow(0 10px 28px rgb(0 0 0 / 10%));
}

.pdf-page-number {
  padding: 0 2px 8px;
  color: var(--text-muted);
  font-size: 12px;
  font-weight: 600;
}

.pdf-page-canvas-wrap {
  position: relative;
  overflow: hidden;
  border-radius: var(--radius-sm);
  background: #fff;
  box-shadow: 0 1px 2px rgb(0 0 0 / 8%), 0 16px 42px rgb(0 0 0 / 10%);
}

.pdf-page-canvas {
  display: block;
}

.pdf-source-layer {
  position: absolute;
  inset: 0;
  pointer-events: none;
}

.source-box {
  position: absolute;
  border: 1px solid rgb(245 158 11 / 70%);
  border-radius: 3px;
  background: rgb(245 158 11 / 16%);
  opacity: 0;
  pointer-events: auto;
  transition: opacity var(--transition-fast), background var(--transition-fast), border-color var(--transition-fast);
}

.source-box.visible {
  opacity: 0.42;
}

.source-box.active {
  z-index: 2;
  opacity: 0.95;
  border-color: rgb(217 119 6 / 90%);
  background: rgb(251 191 36 / 32%);
  box-shadow: 0 0 0 2px rgb(251 191 36 / 16%);
}

@media (max-width: 768px) {
  .pdf-source-viewer {
    height: 50vh;
    min-height: 360px;
  }

  .pdf-source-scroll {
    padding: 12px;
  }
}
</style>
