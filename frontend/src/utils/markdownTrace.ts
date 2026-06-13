interface TraceSourceBlock {
  text: string
}

interface TraceExcerptOptions {
  includeNearbyTable?: boolean
}

export const normalizeTraceText = (value: string) => {
  return value
    .replace(/!\[[^\]]*]\([^)]+\)/g, ' ')
    .replace(/[^\p{L}\p{N}\s]+/gu, ' ')
    .replace(/\s+/g, ' ')
    .trim()
    .toLowerCase()
}

export const splitMarkdownChunks = (markdown: string) => {
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

export const scoreTraceMatch = (markdown: string, sourceText: string) => {
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

export const isMarkdownTableChunk = (chunk: string) => {
  if (/<table[\s>]/i.test(chunk)) return true

  const lines = chunk.split('\n').map((line) => line.trim()).filter(Boolean)
  if (lines.length < 2) return false
  const hasTableRow = lines.some((line) => line.startsWith('|') && line.endsWith('|'))
  const hasSeparator = lines.some((line) => /^\|?\s*:?-{3,}:?\s*(\|\s*:?-{3,}:?\s*)+\|?$/.test(line))
  return hasTableRow && hasSeparator
}

export const tableExcerptWithNearbyTable = (chunk: string, index: number, chunks: string[], usedChunks: Set<number>) => {
  if (isMarkdownTableChunk(chunk)) return chunk

  for (let offset = 1; offset < chunks.length; offset += 1) {
    for (const nearbyIndex of [index - offset, index + offset]) {
      const nearbyChunk = chunks[nearbyIndex]
      if (nearbyChunk && !usedChunks.has(nearbyIndex) && isMarkdownTableChunk(nearbyChunk)) {
        usedChunks.add(nearbyIndex)
        return `${chunk}\n\n${nearbyChunk}`
      }
    }
  }
  return chunk
}

export const traceExcerptForBlock = (
  block: TraceSourceBlock,
  chunks: string[],
  usedChunks: Set<number>,
  options: TraceExcerptOptions = {}
) => {
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
    const chunk = chunks[bestIndex]
    const excerpt = options.includeNearbyTable
      ? tableExcerptWithNearbyTable(chunk, bestIndex, chunks, usedChunks)
      : chunk
    return { excerpt, score: bestScore }
  }
  return { excerpt: block.text, score: 0 }
}

export const shouldRenderTraceExcerpt = (excerpt: string, seenExcerpts: Set<string>) => {
  const key = normalizeTraceText(excerpt)
  if (!key) return true
  if (seenExcerpts.has(key)) return false
  seenExcerpts.add(key)
  return true
}
