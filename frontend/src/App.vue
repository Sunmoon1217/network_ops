<script setup lang="ts">
import { RouterView } from 'vue-router'
import Navbar from './components/Navbar.vue'
</script>

<template>
  <div class="app">
    <nav class="nav-contianer">
      <Navbar />
    </nav>
    <main class="main-container">
      <RouterView />
    </main>
  </div>
</template>

<style>
* {
  margin: 0;
  padding: 0;
  box-sizing: border-box;
}

body {
  font-family: Arial, sans-serif;
  background-color: #f5f5f5;
}

.app {
  height: 100vh;
  display: flex;
  flex-direction: column;
}

.nav-contianer {
  flex: 5;
  width: 100%;
  display: flex;
  background-color: #2c3e50;
  box-shadow: 0 2px 4px rgba(0, 0, 0, 0.1);
  position: sticky;
  z-index: 1000;
}

.main-container {
  flex: 95;
  /* padding: 20px; */
  /* max-width: 1200px; */
  margin: 0 auto;
  width: 90%;
  overflow: hidden;
}
</style>
