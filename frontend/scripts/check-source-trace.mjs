import assert from 'node:assert/strict'
import { readFile } from 'node:fs/promises'
import { pathToFileURL } from 'node:url'
import ts from 'typescript'

const root = new URL('..', import.meta.url)
const sourceUrl = new URL('src/utils/markdownTrace.ts', `${root}/`)
const source = await readFile(sourceUrl, 'utf8')
const compiled = ts.transpileModule(source, {
  compilerOptions: {
    module: ts.ModuleKind.ES2022,
    target: ts.ScriptTarget.ES2022,
    strict: true
  }
}).outputText

const moduleUrl = `data:text/javascript;base64,${Buffer.from(compiled).toString('base64')}`
const { shouldRenderTraceExcerpt, splitMarkdownChunks, traceExcerptForBlock } = await import(moduleUrl)

const markdown = `
Table 2 | Comparison of DeepSeek-R1-Zero and OpenAI o1 models on reasoning-related benchmarks.

Figure 2 | AIME accuracy of DeepSeek-R1-Zero during training.

DeepSeek-R1-Zero to attain robust reasoning capabilities without supervised fine-tuning.

<table><tbody><tr><td>Model</td><td>AIME 2024</td></tr><tr><td>DeepSeek-R1-Zero</td><td>71.0</td></tr></tbody></table>
`

const chunks = splitMarkdownChunks(markdown)
const traced = traceExcerptForBlock(
  {
    id: 'p7-b1',
    type: 'table',
    text: 'Table 2 | Comparison of DeepSeek-R1-Zero and OpenAI o1 models on reasoning-related benchmarks.',
    bbox: [0, 0, 1, 1]
  },
  chunks,
  new Set(),
  { includeNearbyTable: true }
)

assert.match(traced.excerpt, /Table 2 \| Comparison/)
assert.match(traced.excerpt, /<table>/)
assert.match(traced.excerpt, /DeepSeek-R1-Zero<\/td><td>71\.0/)

const mineruOrderedMarkdown = `
<table><tbody><tr><td>Model</td><td>AIME 2024</td></tr><tr><td>DeepSeek-R1-Zero</td><td>71.0</td></tr></tbody></table>

Table 2 | Comparison of DeepSeek-R1-Zero and OpenAI o1 models on reasoning-related benchmarks.

Figure 2 | AIME accuracy of DeepSeek-R1-Zero during training.
`

const mineruChunks = splitMarkdownChunks(mineruOrderedMarkdown)
const mineruTraced = traceExcerptForBlock(
  {
    id: 'p7-b1',
    type: 'table',
    text: 'Table 2 | Comparison of DeepSeek-R1-Zero and OpenAI o1 models on reasoning-related benchmarks.',
    bbox: [0, 0, 1, 1]
  },
  mineruChunks,
  new Set(),
  { includeNearbyTable: true }
)

assert.match(mineruTraced.excerpt, /<table>/)
assert.match(mineruTraced.excerpt, /Table 2 \| Comparison/)

const seenExcerpts = new Set()
assert.equal(shouldRenderTraceExcerpt('Repeated paragraph with enough text to identify it.', seenExcerpts), true)
assert.equal(shouldRenderTraceExcerpt('Repeated paragraph with enough text to identify it.', seenExcerpts), false)
assert.equal(shouldRenderTraceExcerpt('A different paragraph should still render.', seenExcerpts), true)

console.log('source trace checks passed')
