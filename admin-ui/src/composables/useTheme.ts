import { ref, watch, onMounted } from 'vue'

const THEME_KEY = 'forge-armory-theme'
const DARK_MODE_CLASS = 'app-dark'

const isDark = ref(loadTheme())

function loadTheme(): boolean {
  const stored = localStorage.getItem(THEME_KEY)
  if (stored !== null) {
    return stored === 'dark'
  }
  // Default to dark (matching agentic-forge branding)
  return true
}

function saveTheme(dark: boolean): void {
  localStorage.setItem(THEME_KEY, dark ? 'dark' : 'light')
}

function applyThemeToDocument(dark: boolean): void {
  // Apply to <html> element for PrimeVue 4 dark mode
  if (dark) {
    document.documentElement.classList.add(DARK_MODE_CLASS)
  } else {
    document.documentElement.classList.remove(DARK_MODE_CLASS)
  }
}

// Apply theme on initial load
applyThemeToDocument(isDark.value)

// Watch for changes and persist
watch(isDark, (newValue) => {
  saveTheme(newValue)
  applyThemeToDocument(newValue)
})

export function useTheme() {
  // Ensure theme is applied when composable is used
  onMounted(() => {
    applyThemeToDocument(isDark.value)
  })

  function toggleTheme(): void {
    isDark.value = !isDark.value
  }

  function setTheme(dark: boolean): void {
    isDark.value = dark
  }

  return {
    isDark,
    toggleTheme,
    setTheme,
  }
}
