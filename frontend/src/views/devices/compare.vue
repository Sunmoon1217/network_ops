<script setup lang="ts">
import { useRoute, useRouter } from 'vue-router'
import CodeDiffView from '@/components/CodeDiffView.vue'
import { getDevice, getGitConfigContent, getGitDiff } from '@/api/devices'

const route = useRoute()
const router = useRouter()
const deviceId = Number(route.params.id)

const device = ref<any>(null)
const diffText = ref('')
const oldText = ref('')
const newText = ref('')
const oldHash = ref('')
const newHash = ref('')
const loading = ref(true)

const fetchDiff = async () => {
  loading.value = true
  oldHash.value = (route.query.old as string) || ''
  newHash.value = (route.query.new as string) || ''

  if (!oldHash.value || !newHash.value) {
    loading.value = false
    return
  }

  try {
    const deviceRes = await getDevice(deviceId)
    device.value = deviceRes.data
    const hostname = device.value.hostname

    // 全文喂组件显示完整配置；后端 diff 只用来判空态（unified diff 只带变更±3行）
    const [oldRes, newRes, diffRes] = await Promise.all([
      getGitConfigContent(hostname, oldHash.value),
      getGitConfigContent(hostname, newHash.value),
      getGitDiff(hostname, oldHash.value, newHash.value),
    ])
    oldText.value = oldRes.data.config_text || ''
    newText.value = newRes.data.config_text || ''
    diffText.value = diffRes.data.diff || ''
  } catch {
    ElMessage.error('加载失败')
  } finally {
    loading.value = false
  }
}

onMounted(fetchDiff)
</script>

<template>
  <div class="compare-page">
    <div class="page-header">
      <el-button text @click="router.back()">← 返回</el-button>
      <h2>配置对比 — {{ device?.hostname || '...' }}</h2>
    </div>

    <div class="compare-info" v-if="oldHash && newHash">
      <span>基准: <code>{{ oldHash.slice(0, 8) }}</code></span>
      <span>→</span>
      <span>对比: <code>{{ newHash.slice(0, 8) }}</code></span>
    </div>

    <div v-if="loading" v-loading="true" class="compare-body" />
    <div v-else class="compare-body">
      <CodeDiffView
        :diff="diffText"
        :old-text="oldText"
        :new-text="newText"
        :filename="oldHash.slice(0, 8)"
        :new-filename="newHash.slice(0, 8)"
      >
        <!-- toolbar 插槽：版本信息 + 导航 + 统计 + 切换，同一排 -->
        <template #toolbar="{ addNum, delNum, prev, next, outputFormat, setOutputFormat }">
          <div class="compare-info" v-if="oldHash && newHash">
            <span>基准: <code>{{ oldHash.slice(0, 8) }}</code></span>
            <span>→</span>
            <span>对比: <code>{{ newHash.slice(0, 8) }}</code></span>

            <span v-if="diffText" class="toolbar-right">
              <span class="nav-group">
                <el-button size="small" @click="prev">↑</el-button>
                <el-button size="small" @click="next">↓</el-button>
              </span>
              <span class="diff-stat">
                <span class="stat-added">+{{ addNum }} additions</span>
                <span class="stat-deleted">-{{ delNum }} deletions</span>
              </span>
              <el-radio-group :model-value="outputFormat" size="small" @update:model-value="setOutputFormat">
                <el-radio-button value="side-by-side">并排</el-radio-button>
                <el-radio-button value="line-by-line">行对行</el-radio-button>
              </el-radio-group>
            </span>
          </div>
        </template>

        <template #empty>
          <el-empty description="缺少对比参数或无变更" />
        </template>
      </CodeDiffView>
    </div>
  </div>
</template>

<style scoped>
.compare-page {
  display: flex;
  flex-direction: column;
  height: 100%;
  padding: 20px;
}
.page-header {
  display: flex;
  align-items: center;
  gap: 12px;
  margin-bottom: 16px;
  flex-shrink: 0;
}
.page-header h2 {
  margin: 0;
  font-size: 1.2rem;
  font-weight: 600;
}
.compare-info {
  display: flex;
  align-items: center;
  gap: 12px;
  padding: 10px 16px;
  background: var(--el-bg-color);
  border-radius: 8px;
  font-size: 13px;
  color: var(--el-text-color-regular);
  flex-shrink: 0;
}
.compare-info code {
  background: var(--el-fill-color-light);
  padding: 2px 8px;
  border-radius: 4px;
  font-family: monospace;
}
/* 工具栏右半：导航 + 统计 + 切换，靠右对齐 */
.toolbar-right {
  display: flex;
  align-items: center;
  gap: 16px;
  margin-left: auto;
}
.nav-group {
  display: inline-flex;
  gap: 4px;
}
.diff-stat {
  display: inline-flex;
  gap: 10px;
  font-size: 12px;
  font-family: monospace;
}
.stat-added {
  color: var(--el-color-success);
}
.stat-deleted {
  color: var(--el-color-danger);
}
.compare-body {
  flex: 1;
  min-height: 0;
  background: var(--el-bg-color);
  border-radius: 8px;
  overflow: hidden;
}
</style>
