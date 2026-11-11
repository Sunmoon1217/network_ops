<script setup lang="ts">
import { computed } from 'vue'
import { useRoute } from 'vue-router'

const route = useRoute()

// 路由 meta.title 由 router 配置提供，缺省显示通用文案
const title = computed(() => (route.meta.title as string | undefined) ?? '该功能')
</script>

<template>
  <div class="under-construction">
    <el-empty :description="`${title} 功能建设中，敬请期待`" />
  </div>
</template>

<style scoped>
.under-construction {
  display: flex;
  align-items: center;
  justify-content: center;
  min-height: 60vh;
}
</style>
