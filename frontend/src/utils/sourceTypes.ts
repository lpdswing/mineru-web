export type SourceTypeFilter = 'all' | 'text' | 'title' | 'table' | 'image' | 'formula' | 'assist' | 'other'

export interface SourceTypeFilterOption {
  key: SourceTypeFilter
  label: string
}

type SourceTypeCategory = Exclude<SourceTypeFilter, 'all' | 'other'>

export const SOURCE_TYPE_FILTER_OPTIONS: SourceTypeFilterOption[] = [
  { key: 'all', label: '全部' },
  { key: 'text', label: '正文' },
  { key: 'title', label: '标题' },
  { key: 'table', label: '表格' },
  { key: 'image', label: '图片' },
  { key: 'formula', label: '公式' },
  { key: 'assist', label: '页眉页脚' },
  { key: 'other', label: '其他' }
]

const SOURCE_TYPE_LABELS: Record<string, string> = {
  text: '正文',
  abstract: '摘要',
  ref_text: '引用',
  list: '列表',
  title: '标题',
  index: '目录',
  table: '表格',
  table_body: '表格',
  table_caption: '表注',
  table_footnote: '表脚注',
  image: '图片',
  image_body: '图片',
  image_caption: '图注',
  image_footnote: '图脚注',
  chart: '图表',
  chart_body: '图表',
  chart_caption: '图注',
  chart_footnote: '图脚注',
  equation: '公式',
  inline_equation: '行内公式',
  interline_equation: '行间公式',
  header: '页眉',
  footer: '页脚',
  page_number: '页码',
  aside_text: '旁注',
  page_footnote: '脚注',
  code: '代码',
  code_body: '代码',
  code_caption: '代码说明',
  code_footnote: '代码脚注'
}

const SOURCE_TYPE_CATEGORIES: Record<string, SourceTypeCategory> = {
  text: 'text',
  abstract: 'text',
  ref_text: 'text',
  list: 'text',
  title: 'title',
  index: 'title',
  table: 'table',
  table_body: 'table',
  table_caption: 'table',
  table_footnote: 'table',
  image: 'image',
  image_body: 'image',
  image_caption: 'image',
  image_footnote: 'image',
  chart: 'image',
  chart_body: 'image',
  chart_caption: 'image',
  chart_footnote: 'image',
  equation: 'formula',
  inline_equation: 'formula',
  interline_equation: 'formula',
  header: 'assist',
  footer: 'assist',
  page_number: 'assist',
  aside_text: 'assist',
  page_footnote: 'assist'
}

const normalizeSourceType = (type?: string) => (type || '').trim().toLowerCase()

export const sourceTypeLabel = (type?: string) => {
  const normalized = normalizeSourceType(type)
  return SOURCE_TYPE_LABELS[normalized] || type || '未知'
}

export const sourceTypeFilterFor = (type?: string): Exclude<SourceTypeFilter, 'all'> => {
  const normalized = normalizeSourceType(type)
  return SOURCE_TYPE_CATEGORIES[normalized] || 'other'
}

export const sourceTypeFilterMatches = (type: string | undefined, filter: SourceTypeFilter) => {
  return filter === 'all' || sourceTypeFilterFor(type) === filter
}
