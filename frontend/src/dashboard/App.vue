<script setup lang="ts">
import { NConfigProvider, NMessageProvider } from 'naive-ui'
import Dashboard from './views/dashboard/Dashboard.vue'
</script>

<template>
  <NConfigProvider>
    <NMessageProvider>
      <Dashboard />
    </NMessageProvider>
  </NConfigProvider>
</template>

<style>
* {
  margin: 0;
  padding: 0;
  box-sizing: border-box;
}

body {
  font-family: Arial, sans-serif;
  overscroll-behavior: none;
}

.app {
  height: 100vh;
}
</style>
