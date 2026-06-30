<template>
  <div class="popo-tree">
    <div class="popo-tree-toolbar">
      <div class="popo-tree-stats">
        <span class="stat-chip">节点 {{ stats.total }}</span>
        <span class="stat-chip">标题 {{ stats.title }}</span>
        <span class="stat-chip">表格 {{ stats.table }}</span>
        <span class="stat-chip">图片 {{ stats.image }}</span>
      </div>
      <div class="popo-tree-actions">
        <el-input
          v-model="keyword"
          size="small"
          placeholder="筛选标题/内容"
          clearable
          class="popo-tree-filter"
        />
        <el-button size="small" @click="expandAll(true)">展开全部</el-button>
        <el-button size="small" @click="expandAll(false)">折叠全部</el-button>
        <el-button size="small" type="primary" :icon="Download" @click="downloadJson">下载 JSON</el-button>
      </div>
    </div>

    <el-tree
      ref="treeRef"
      class="popo-tree-body"
      :data="treeData"
      :props="treeProps"
      node-key="__id"
      :default-expand-all="true"
      :filter-node-method="filterNode"
      :expand-on-click-node="false"
    >
      <template #default="{ data }">
        <div class="popo-node">
          <span class="popo-node-type" :class="`type-${typeClass(data.type)}`">
            {{ typeLabel(data.type) }}
          </span>
          <span v-if="data.title && !isPlaceholderTitle(data.title)" class="popo-node-title">
            {{ data.title }}
          </span>
          <span v-if="data.type === 'table'" class="popo-node-extra">
            <span class="popo-node-badge">{{ data.content ? 'HTML' : '空' }}</span>
          </span>
          <span
            v-else-if="data.content"
            class="popo-node-preview"
          >{{ preview(data.content) }}</span>
        </div>
      </template>
    </el-tree>

    <div v-if="!treeData.length" class="popo-tree-empty">结构树为空</div>
  </div>
</template>

<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import { Download } from '@element-plus/icons-vue'
import type { PopoTreeNode } from '@/types/file'

interface KeyedNode extends PopoTreeNode {
  __id: string
  children?: KeyedNode[]
}

const props = defineProps<{
  tree: PopoTreeNode | null
  filename?: string
}>()

const treeRef = ref<{ filter: (value: string) => void; store: { nodesMap: Record<string, { expanded: boolean }> } } | null>(null)
const keyword = ref('')

const treeProps = { children: 'children', label: 'title' }

// 给每个节点分配稳定 key，并把 root 摊平成顶层数组
const keyed = computed<KeyedNode[]>(() => {
  if (!props.tree) return []
  let counter = 0
  const assign = (node: PopoTreeNode): KeyedNode => {
    const id = `n${counter++}`
    const children = (node.children || []).map(assign)
    return { ...node, __id: id, children }
  }
  const root = assign(props.tree)
  return root.type === 'root' ? (root.children || []) : [root]
})

const treeData = computed(() => keyed.value)

const stats = computed(() => {
  const acc = { total: 0, title: 0, table: 0, image: 0 }
  const walk = (nodes: KeyedNode[]) => {
    for (const node of nodes) {
      acc.total += 1
      if (node.type === 'title' || (node.type === 'text' && node.title && !isPlaceholderTitle(node.title))) {
        acc.title += 1
      }
      if (node.type === 'table') acc.table += 1
      if (['image', 'chart', 'seal', 'image_block'].includes(node.type)) acc.image += 1
      if (node.children?.length) walk(node.children)
    }
  }
  walk(keyed.value)
  return acc
})

const TYPE_LABELS: Record<string, string> = {
  text: '正文',
  title: '标题',
  table: '表格',
  image: '图片',
  chart: '图表',
  seal: '印章',
  image_block: '图块',
  page_title: '页眉标题',
  page_number: '页码',
  page_footnote: '脚注',
  header: '页眉',
  footer: '页脚',
  aside_text: '边栏'
}

const typeLabel = (type: string) => TYPE_LABELS[type] || type || '节点'

const typeClass = (type: string) => {
  if (type === 'title') return 'title'
  if (type === 'table') return 'table'
  if (['image', 'chart', 'seal', 'image_block'].includes(type)) return 'image'
  return 'text'
}

const isPlaceholderTitle = (title?: string) => !title || title === 'Default Title' || title === 'N/A'

const preview = (content?: string) => {
  const text = (content || '').replace(/<\|txt_(split|contd)\|>/g, ' ').replace(/\s+/g, ' ').trim()
  return text.length > 80 ? `${text.slice(0, 80)}…` : text
}

const filterNode = (value: string, data: KeyedNode) => {
  if (!value) return true
  const haystack = `${data.title || ''} ${data.content || ''}`.toLowerCase()
  return haystack.includes(value.toLowerCase())
}

watch(keyword, (value) => {
  treeRef.value?.filter(value)
})

const expandAll = (expand: boolean) => {
  const nodesMap = treeRef.value?.store?.nodesMap
  if (!nodesMap) return
  Object.values(nodesMap).forEach((node) => {
    node.expanded = expand
  })
}

const downloadJson = () => {
  if (!props.tree) return
  const blob = new Blob([JSON.stringify(props.tree, null, 2)], { type: 'application/json' })
  const url = window.URL.createObjectURL(blob)
  const link = document.createElement('a')
  link.href = url
  link.download = `${props.filename || 'document'}_popo.json`
  document.body.appendChild(link)
  link.click()
  window.URL.revokeObjectURL(url)
  document.body.removeChild(link)
}
</script>

<style scoped>
.popo-tree {
  display: flex;
  flex-direction: column;
  height: 100%;
  min-height: 0;
}

.popo-tree-toolbar {
  display: flex;
  flex-wrap: wrap;
  gap: 12px;
  align-items: center;
  justify-content: space-between;
  padding: 8px 12px;
  border-bottom: 1px solid var(--el-border-color-lighter, #ebeef5);
}

.popo-tree-stats {
  display: flex;
  gap: 8px;
  flex-wrap: wrap;
}

.stat-chip {
  font-size: 12px;
  color: var(--el-text-color-regular, #606266);
  background: var(--el-fill-color-light, #f5f7fa);
  border-radius: 10px;
  padding: 2px 10px;
}

.popo-tree-actions {
  display: flex;
  gap: 8px;
  align-items: center;
}

.popo-tree-filter {
  width: 160px;
}

.popo-tree-body {
  flex: 1;
  min-height: 0;
  overflow: auto;
  padding: 8px 12px;
}

.popo-node {
  display: flex;
  align-items: center;
  gap: 8px;
  min-width: 0;
}

.popo-node-type {
  flex: none;
  font-size: 11px;
  line-height: 18px;
  padding: 0 8px;
  border-radius: 4px;
  color: #fff;
}

.type-title { background: #409eff; }
.type-table { background: #e6a23c; }
.type-image { background: #67c23a; }
.type-text { background: #909399; }

.popo-node-title {
  font-weight: 600;
  color: var(--el-text-color-primary, #303133);
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

.popo-node-preview {
  color: var(--el-text-color-secondary, #909399);
  font-size: 12px;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

.popo-node-badge {
  font-size: 11px;
  color: var(--el-text-color-regular, #606266);
  border: 1px solid var(--el-border-color, #dcdfe6);
  border-radius: 4px;
  padding: 0 6px;
}

.popo-tree-empty {
  padding: 24px;
  text-align: center;
  color: var(--el-text-color-secondary, #909399);
}
</style>
