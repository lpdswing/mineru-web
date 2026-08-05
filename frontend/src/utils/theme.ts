import { computed, ref } from 'vue'

export type Theme = 'light' | 'dark'

const THEME_STORAGE_KEY = 'mineru-theme'

const getInitialTheme = (): Theme => {
  const savedTheme = localStorage.getItem(THEME_STORAGE_KEY)
  if (savedTheme === 'light' || savedTheme === 'dark') return savedTheme

  return window.matchMedia('(prefers-color-scheme: dark)').matches ? 'dark' : 'light'
}

const theme = ref<Theme>(getInitialTheme())

const applyTheme = (value: Theme) => {
  document.documentElement.classList.toggle('theme-dark', value === 'dark')
}

applyTheme(theme.value)

export const useTheme = () => {
  const isDark = computed(() => theme.value === 'dark')

  const setTheme = (value: Theme) => {
    theme.value = value
    localStorage.setItem(THEME_STORAGE_KEY, value)
    applyTheme(value)
  }

  const toggleTheme = () => {
    setTheme(isDark.value ? 'light' : 'dark')
  }

  return { theme, isDark, setTheme, toggleTheme }
}
