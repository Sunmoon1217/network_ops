<script setup lang="ts">
defineProps<{ title: string }>()
</script>

<template>
  <div class="page">
    <div class="page-header">
      <h2>{{ title }}</h2>
      <div class="header-actions">
        <slot name="actions" />
      </div>
    </div>
    <slot />
  </div>
</template>

<style scoped>
.page { display: flex; flex-direction: column; height: 100%; padding: 16px; }
.page-header { display: flex; align-items: center; justify-content: space-between; margin-bottom: 16px; flex-shrink: 0; }
.page-header h2 { margin: 0; font-size: 1.2rem; font-weight: 600; }
.header-actions { display: flex; gap: 8px; }
</style>
