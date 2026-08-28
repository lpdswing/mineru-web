import DOMPurify from 'dompurify'
import type { Config } from 'dompurify'

/**
 * 统一的 HTML 净化配置。
 *
 * 本项目所有 v-html 出口的内容都来自不可信输入（用户上传文件的解析结果、
 * 手动编辑保存的 Markdown、mammoth/xlsx 转出的 Office 内容），必须净化后再渲染。
 *
 * 同时必须保留以下刚需语义：
 * - OCR 输出的 HTML 表格：table/thead/tbody/tr/td/th/caption + colspan/rowspan + 内联 style
 * - markdown-it-katex 的公式：可视层（katex-html，靠内联 style 定位）与 mathMl 层都要保留
 * - mammoth(docx) / sheet_to_html(xlsx) 的排版标签、表格与 base64 图片
 *
 * 已知取舍：mathMl profile 会剥掉 <semantics>/<annotation>（DOMPurify 出于 mXSS
 * 风险刻意排除，见其 mathMlDisallowed 列表）。这会让 TeX 源码以纯文本形式留在
 * <math> 内，但 katex-mathml 被 KaTeX 的 CSS 视觉隐藏，且可视层完全不受影响，
 * 因此保持 DOMPurify 的默认安全策略，不重新放开这两个标签。
 */
const SANITIZE_CONFIG: Config = {
  USE_PROFILES: { html: true, mathMl: true, svg: true },
  // 关闭 Trusted Types 返回值，确保 sanitize 返回 string 而非 TrustedHTML
  RETURN_TRUSTED_TYPE: false,
  // 表格合并单元格、尺寸与对齐：OCR/Office 表格依赖这些属性还原版式
  ADD_ATTR: [
    'colspan',
    'rowspan',
    'align',
    'valign',
    'width',
    'height',
    'start',
    'target',
    'rel',
  ],
  FORBID_TAGS: [
    'script',
    'style',
    'iframe',
    'object',
    'embed',
    'form',
    'input',
    'button',
    'link',
    'meta',
    'base',
    'noscript',
  ],
  FORBID_ATTR: [
    'srcdoc',
    'http-equiv',
    'formaction',
    'xlink:href',
    'autofocus',
  ],
  ALLOW_DATA_ATTR: true,
}

/** 净化一段 HTML。用于所有 v-html 出口。 */
export const sanitizeHtml = (html: string): string =>
  DOMPurify.sanitize(html || '', SANITIZE_CONFIG)

/** 带 LRU 缓存的净化。用于逐块渲染的场景（如按页溯源，每页每块都要渲染一次）。 */
const CACHE_LIMIT = 500
const cache = new Map<string, string>()

export const sanitizeHtmlCached = (html: string): string => {
  const hit = cache.get(html)
  if (hit !== undefined) return hit

  const out = sanitizeHtml(html)
  if (cache.size >= CACHE_LIMIT) {
    const oldest = cache.keys().next().value
    if (oldest !== undefined) cache.delete(oldest)
  }
  cache.set(html, out)
  return out
}
