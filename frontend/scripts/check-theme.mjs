import { readFileSync } from 'node:fs'
import { resolve } from 'node:path'

const root = resolve(import.meta.dirname, '..')

const sourceFiles = [
  'src/style.css',
  'src/App.vue',
  'src/views/Home.vue',
  'src/views/Upload.vue',
  'src/views/FilePreview.vue'
]

const requiredTokens = [
  '--primary-color: #0071e3;',
  '--primary-light: #409cff;',
  '--primary-dark: #005bb5;',
  '--bg-secondary: #f5f5f7;',
  '--text-primary: #1d1d1f;'
]

const forbiddenPatterns = [
  '#6366f1',
  '#8b5cf6',
  '#818cf8',
  '#4f46e5',
  '#a5b4fc',
  '#c7d2fe',
  '#e0e7ff',
  'rgb(99 102 241'
]

const styleCss = readFileSync(resolve(root, 'src/style.css'), 'utf8')
const failures = []

for (const token of requiredTokens) {
  if (!styleCss.includes(token)) {
    failures.push(`Missing System Light token: ${token}`)
  }
}

for (const file of sourceFiles) {
  const content = readFileSync(resolve(root, file), 'utf8')
  for (const pattern of forbiddenPatterns) {
    if (content.includes(pattern)) {
      failures.push(`${file} still contains old purple theme value: ${pattern}`)
    }
  }
}

if (failures.length > 0) {
  console.error(failures.join('\n'))
  process.exit(1)
}

console.log('System Light theme tokens are consistent.')
