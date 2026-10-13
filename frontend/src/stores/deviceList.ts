import { defineStore } from 'pinia'
import { ref } from 'vue'

/**
 * 设备列表的「脏标记」：新建 / 编辑设备保存成功后置脏，
 * 列表页在 keep-alive 的 onActivated 里消费一次、据此决定是否重新查询。
 *
 * 为什么需要它：keep-alive 下 onMounted 只在首次进入时跑一次，
 * 返回列表时只能靠 onActivated；若 onActivated 无条件 refetch，
 * 就退回了「每次返回都重查」，违背缓存初衷。脏标记只让「数据真的被改过」的返回刷新一次。
 *
 * consume() 是「读后即清」：一次置脏只在紧接着的一次激活时生效，
 * 避免 token 粘住导致之后每次返回都重查。
 */
export const useDeviceListStore = defineStore('device-list', () => {
  const dirty = ref(false)

  const touch = () => {
    dirty.value = true
  }

  const consume = () => {
    const v = dirty.value
    dirty.value = false
    return v
  }

  return { dirty, touch, consume }
})