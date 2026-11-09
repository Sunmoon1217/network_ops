<script setup lang="ts">
import { computed } from 'vue'
interface TableData {
  label: string
  value: number
}
interface Props {
  data: {
    cpu: TableData[]
    memory: TableData[]
  }
}
const props = defineProps<Props>()

const cpu = computed(() => props.data.cpu.slice(0, 5))
const memory = computed(() => props.data.memory.slice(0, 5))
</script>
<template>
  <div class="toplist">
    <section class="column">
      <header class="column-head">
        <span>CPU TOP5</span>
        <span>使用率</span>
      </header>
      <div class="column-body">
        <div v-for="item in cpu" :key="item.label" class="row">
          <span class="name" :title="item.label">{{ item.label }}</span>
          <strong class="value">{{ item.value }}%</strong>
        </div>
      </div>
    </section>

    <section class="column">
      <header class="column-head">
        <span>内存 TOP5</span>
        <span>使用率</span>
      </header>
      <div class="column-body">
        <div v-for="item in memory" :key="item.label" class="row">
          <span class="name" :title="item.label">{{ item.label }}</span>
          <strong class="value">{{ item.value }}%</strong>
        </div>
      </div>
    </section>
  </div>
</template>

<style lang="css" scoped>
.toplist {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  min-width: 360px;
  max-width: 480px;
  border: 1px solid rgba(111, 244, 255, 0.22);
  border-radius: 12px;
  background:
    radial-gradient(circle at top left, rgba(58, 140, 202, 0.16), transparent 80%),
    linear-gradient(180deg, rgba(18, 40, 61, 0.96), rgba(12, 28, 44, 0.96));
  box-shadow:
    inset 0 0 0 1px rgba(255, 255, 255, 0.03),
    0 10px 24px rgba(3, 12, 20, 0.28);
  overflow: hidden;
}

.column {
  min-width: 0;
}

.column:first-child {
  border-right: 1px solid rgba(111, 244, 255, 0.16);
}

.column-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 8px;
  padding: 8px 10px;
  font-size: 12px;
  color: #a9d4f0;
  border-bottom: 1px solid rgba(111, 244, 255, 0.16);
}

.column-body {
  padding: 6px 10px;
}

.row {
  display: grid;
  grid-template-columns: minmax(0, 1fr) auto;
  gap: 10px;
  align-items: center;
  min-height: 28px;
  font-size: 12px;
  color: #d7ecfb;
  border-bottom: 1px solid rgba(111, 244, 255, 0.12);
}

.row:last-child {
  border-bottom: none;
}

.name {
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  color: #ecf7ff;
}

.value {
  color: #6ff4ff;
  font-size: 12px;
  line-height: 1;
}
</style>
