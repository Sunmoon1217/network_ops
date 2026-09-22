<script setup lang="ts">
import DeviceFilter from './DeviceFilter.vue'

/**
 * 列表页通用过滤条：设备下拉 + 附加过滤器（默认插槽）+ 搜索框。
 *
 * 用法（两个 v-model 对接页面状态）：
 *   <FilterBar v-model:device="filterDevice" v-model:search="search" placeholder="搜索名称/设备" />
 *   <FilterBar v-model:device="filterDevice" v-model:search="search">
 *     <el-select v-model="filterMode" ... />   // 页面自定义的附加过滤器
 *   </FilterBar>
 *
 * 设备变化的重新拉取由页面自己 watch（每页的重置目标不同），这里只负责状态。
 */
withDefaults(
  defineProps<{
    /** 选中的设备 id，'' 表示未选 */
    device?: number | ''
    /** 只列该类型的设备（slb / gslb ...）；不传列全部 */
    deviceType?: string
    /** 搜索关键词，对接 useCrudApi 的 search */
    search?: string
    searchPlaceholder?: string
    searchWidth?: string
    /** 不需要设备下拉的页面置 false */
    showDevice?: boolean
    /** 不需要搜索框的页面置 false */
    showSearch?: boolean
  }>(),
  {
    device: '',
    deviceType: undefined,
    search: '',
    searchPlaceholder: '搜索',
    searchWidth: '200px',
    showDevice: true,
    showSearch: true,
  },
)

const emit = defineEmits<{
  (e: 'update:device', v: number | ''): void
  (e: 'update:search', v: string): void
}>()
</script>

<template>
  <DeviceFilter
    v-if="showDevice"
    :model-value="device"
    :device-type="deviceType"
    @update:model-value="emit('update:device', $event)"
  />
  <slot />
  <el-input
    v-if="showSearch"
    :model-value="search"
    :placeholder="searchPlaceholder"
    clearable
    :style="{ width: searchWidth }"
    @update:model-value="emit('update:search', $event)"
  />
</template>
