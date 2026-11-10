import { defineStore } from 'pinia'
import { ref } from 'vue'

const PRIMARY = '#34c8ff'
const PRIMARY_LIGHT_3 = '#5ed4ff'
const PRIMARY_DARK_2 = '#20a8d8'

const CSS_VARS_LIGHT: Record<string, string> = {
  '--color-success': '#18a058',
  '--color-warning': '#f0a020',
  '--color-danger': '#d03050',
  '--color-info': '#909399',
}

const CSS_VARS_DARK: Record<string, string> = {
  '--color-success': '#36ad6a',
  '--color-warning': '#f0c040',
  '--color-danger': '#e85454',
  '--color-info': '#a0a0a0',
}

export const useThemeStore = defineStore('theme', () => {
  const stored = localStorage.getItem('darkMode')
  const isDark = ref<boolean>(
    stored !== null
      ? stored === 'true'
      : window.matchMedia('(prefers-color-scheme: dark)').matches,
  )

  const toggleDark = () => {
    isDark.value = !isDark.value
    localStorage.setItem('darkMode', String(isDark.value))
    applyTheme()
  }

  const setDark = (value: boolean) => {
    isDark.value = value
    localStorage.setItem('darkMode', String(value))
    applyTheme()
  }

  const applyTheme = () => {
    const d = isDark.value
    document.documentElement.classList.toggle('dark', d)
    document.body.setAttribute('theme', d ? 'dark' : 'light')

    const root = document.documentElement
    root.style.setProperty('--el-color-primary', PRIMARY)
    root.style.setProperty('--el-color-primary-light-3', PRIMARY_LIGHT_3)
    root.style.setProperty('--el-color-primary-dark-2', PRIMARY_DARK_2)

    const vars = d ? CSS_VARS_DARK : CSS_VARS_LIGHT
    for (const [key, value] of Object.entries(vars)) {
      root.style.setProperty(key, value)
    }
  }

  applyTheme()

  return { isDark, toggleDark, setDark }
})
