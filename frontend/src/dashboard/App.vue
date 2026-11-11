<script setup lang="ts">
import Dashboard from './views/Dashboard.vue'
</script>

<template>
  <Dashboard />
</template>

<style>
* {
  margin: 0;
  padding: 0;
  box-sizing: border-box;
}

html,
body,
#dashboard {
  width: 100%;
  height: 100%;
}

body {
  font-family: 'Segoe UI', 'PingFang SC', 'Microsoft YaHei', sans-serif;
  overscroll-behavior: none;
}
</style>
