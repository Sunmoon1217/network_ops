import { ref, onUnmounted, onActivated, onDeactivated } from 'vue'

export function useInterval(callback: () => void, interval: number | null, immediate = false) {
  const isActive = ref(false)
  let timer: ReturnType<typeof setInterval> | null = null

  const clear = () => {
    if (timer) {
      clearInterval(timer)
      timer = null
    }
    isActive.value = false
  }

  const start = () => {
    if (interval === null) return
    clear()
    if (immediate) callback()

    timer = setInterval(() => {
      callback()
    }, interval)
    isActive.value = true
  }

  const stop = () => {
    clear()
  }

  onUnmounted(() => {
    clear()
  })

  onDeactivated(() => {
    if (isActive.value) stop()
  })

  onActivated(() => {
    if (isActive.value && interval !== null) start()
  })

  return {
    isActive,
    start,
    stop,
  }
}
