import { readFileSync } from 'node:fs'
import { resolve } from 'node:path'

const root = resolve(import.meta.dirname, '..')

const sourceFiles = [
  'src/style.css',
  'src/utils/theme.ts',
  'src/App.vue',
  'src/views/Home.vue',
  'src/views/Upload.vue',
  'src/views/FilePreview.vue'
]

const requiredTokens = [
  '--primary-color: #0071e3;',
  '--primary-light: #409cff;',
  '--primary-dark: #005bb5;',
  '--bg-page: #f5f5f7;',
  '--bg-surface: #ffffff;',
  '--bg-card: #e9e9ed;',
  '--text-primary: #1d1d1f;'
]

const requiredDarkTokens = [
  ':root.theme-dark',
  '--primary-color: #2f8cff;',
  '--bg-page: #000000;',
  '--bg-surface: #0d0d0d;',
  '--bg-card: #212121;',
  '--bg-card-hover: #2a2a2a;',
  '--text-primary: #f2f2f2;',
  '--text-secondary: #b4b4b4;',
  '--border-color: #2f2f2f;'
]

const requiredThemeBehavior = [
  "const THEME_STORAGE_KEY = 'mineru-theme'",
  "window.matchMedia('(prefers-color-scheme: dark)')",
  "document.documentElement.classList.toggle('theme-dark'"
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

for (const token of requiredDarkTokens) {
  if (!styleCss.includes(token)) {
    failures.push(`Missing System Dark token: ${token}`)
  }
}

const themeUtility = readFileSync(resolve(root, 'src/utils/theme.ts'), 'utf8')
for (const pattern of requiredThemeBehavior) {
  if (!themeUtility.includes(pattern)) {
    failures.push(`Missing theme behavior: ${pattern}`)
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

console.log('System light and dark theme tokens are consistent.')
