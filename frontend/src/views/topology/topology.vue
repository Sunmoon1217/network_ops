<script setup lang="ts">
import { ref, onMounted, nextTick } from 'vue'
import { useRoute } from 'vue-router'
import TopologyGraph from './components/TopologyGraph.vue'
import TopologyToolbar from './components/TopologyToolbar.vue'
import DeviceSelector from './components/DeviceSelector.vue'
import TopologyNodePanel from './components/TopologyNodePanel.vue'
import TopologyEdgePanel from './components/TopologyEdgePanel.vue'
import { getTopology, createTopology, updateTopology, deleteTopology } from '@/api/topology'
import { fetchAllPages } from '@/utils/fetchAllPages'
import { buildIconDataUri } from '@/assets/device-icons'
import { ElMessage, ElMessageBox } from 'element-plus'

const route = useRoute()

// === 拓扑列表 ===
const topologyList = ref<any[]>([])
const topologyId = ref<number | null>(null)
const editing = ref(false)

// === 图状态 ===
const showDeviceSelector = ref(false)
const graphRef = ref<InstanceType<typeof TopologyGraph>>()
const selectedNode = ref<any>(null)
const selectedEdge = ref<any>(null)
const showNodePopover = ref(false)
const showEdgePopover = ref(false)
const popoverAnchor = ref<HTMLElement | undefined>(undefined)
let savedEdgeSnapshot: any = null

// === 加载拓扑列表 ===
// 该列表用于顶部下拉选择器，必须完整，故走全量分页拉取（后端已启用数字分页）
const loadTopologyList = async () => {
  try {
    topologyList.value = await fetchAllPages('/api/assets/topologies/', { ordering: 'name' })
  } catch {
    ElMessage.error('加载拓扑列表失败')
  }
}

// === 切换拓扑 ===
const switchTopology = async (id: number) => {
  if (editing.value) {
    try {
      await ElMessageBox.confirm('当前有未保存的修改，确认切换？', '提示', { type: 'warning' })
    } catch {
      return // 取消
    }
  }
  editing.value = false
  closePopover()
  selectedNode.value = null
  selectedEdge.value = null
  topologyId.value = id
  await loadTopologyData(id)
}

// === 加载单个拓扑数据 ===
const loadTopologyData = async (id: number) => {
  try {
    const res = await getTopology(id)
    const data = res.data?.graph_data
    if (data && (data.nodes?.length || data.edges?.length)) {
      graphRef.value?.setData(data)
    } else {
      graphRef.value?.setData({ nodes: [], edges: [] })
    }
  } catch {
    ElMessage.error('加载拓扑数据失败')
  }
}

// === 新建拓扑 ===
const handleCreateTopology = async () => {
  try {
    const { value: name } = await ElMessageBox.prompt('请输入拓扑名称', '新建拓扑', {
      inputPattern: /^.{1,50}$/,
      inputErrorMessage: '名称不能为空且不超过50字符',
      confirmButtonText: '创建',
      cancelButtonText: '取消',
    })
    const res = await createTopology({ name, graph_data: { nodes: [], edges: [] } })
    const newTopo = res.data
    topologyList.value.unshift(newTopo)
    topologyId.value = newTopo.id
    graphRef.value?.setData({ nodes: [], edges: [] })
    editing.value = true
    ElMessage.success('拓扑已创建')
  } catch {
    // 用户取消
  }
}

// === 删除拓扑 ===
const handleDeleteTopology = async () => {
  if (!topologyId.value) return
  try {
    await ElMessageBox.confirm('确认删除此拓扑图？不可恢复。', '删除拓扑', {
      type: 'error',
      confirmButtonText: '删除',
      cancelButtonText: '取消',
    })
    await deleteTopology(topologyId.value)
    topologyList.value = topologyList.value.filter(t => t.id !== topologyId.value)
    topologyId.value = topologyList.value[0]?.id ?? null
    if (topologyId.value) {
      await loadTopologyData(topologyId.value)
    } else {
      graphRef.value?.setData({ nodes: [], edges: [] })
    }
    editing.value = false
    ElMessage.success('已删除')
  } catch {
    // 用户取消
  }
}

// === 保存 ===
const handleSave = async () => {
  console.log("[SAVE] topologyId:", topologyId.value)
  if (!graphRef.value) return
  // 先 flush 渲染，确保 getData 拿到最新位置
  const data = graphRef.value.getData()
  console.log("[SAVE] data nodes:", data?.nodes?.length, "edges:", data?.edges?.length)
  if (!data) return
  try {
    if (topologyId.value) {
      await updateTopology(topologyId.value, { graph_data: data })
    } else {
      const res = await createTopology({ name: '默认拓扑', graph_data: data, is_default: true })
      topologyId.value = res.data.id
      topologyList.value.unshift(res.data)
    }
    ElMessage.success('保存成功')
  } catch (e: any) {
    ElMessage.error(`保存失败: ${e?.response?.data?.detail ?? e?.message ?? '未知错误'}`)
  }
}

// === 添加设备 ===
const handleAddDevice = (device: any) => {
  showDeviceSelector.value = false
  const iconSrc = buildIconDataUri(device.device_type)
  graphRef.value?.addNode({
    id: `device-${device.id}`,
    label: device.hostname,
    data: { device_type: device.device_type, device_id: device.id },
    style: { iconSrc, iconWidth: 32, iconHeight: 32 },
  })
}

const handleAddCustom = () => {
  graphRef.value?.addNode({
    id: `custom-${Date.now()}`,
    label: '自定义节点',
    data: { device_type: 'custom' },
    style: {},
  })
}

const handleDeleteSelected = () => {
  graphRef.value?.removeSelected()
}

// === 编辑节点（右键菜单触发） ===
let savedNodeSnapshot: any = null

const handleEditNode = (nodeId: string, mouseEvent: MouseEvent) => {
  const data = graphRef.value?.getData()
  const node = data?.nodes?.find((n: any) => n.id === nodeId)
  if (!node) return
  savedNodeSnapshot = JSON.parse(JSON.stringify(node))
  selectedNode.value = node
  // 在鼠标位置创建虚拟锚点
  const anchor = document.createElement('div')
  anchor.style.cssText = `position:fixed;left:${mouseEvent.clientX}px;top:${mouseEvent.clientY}px;width:0;height:0;pointer-events:none;`
  document.body.appendChild(anchor)
  popoverAnchor.value = anchor
  showNodePopover.value = true
}

const closePopover = () => {
  showNodePopover.value = false
  if (popoverAnchor.value) {
    popoverAnchor.value.remove()
    popoverAnchor.value = undefined
  }
  selectedNode.value = null
  savedNodeSnapshot = null
  // 画布随动：关闭后通知 graph 重新适配尺寸
  nextTick(() => graphRef.value?.resize())
}

const handleNodeSave = (updated: any) => {
  // 同步到图数据
  const data = graphRef.value?.getData()
  graphRef.value?.setData({
    nodes: (data?.nodes ?? []).map((n: any) => n.id === updated.id ? { ...n, ...updated } : n),
    edges: data?.edges ?? [],
  })
  closePopover()
}

const handleNodeCancel = () => {
  // 恢复原始数据
  if (savedNodeSnapshot) {
    const data = graphRef.value?.getData()
    graphRef.value?.setData({
      nodes: (data?.nodes ?? []).map((n: any) => n.id === savedNodeSnapshot.id ? savedNodeSnapshot : n),
      edges: data?.edges ?? [],
    })
  }
  closePopover()
}

const handleNodeUpdate = (updated: any) => {
  selectedNode.value = { ...selectedNode.value, ...updated }
}

const handleEdgeUpdate = (updated: any) => {
  selectedEdge.value = { ...selectedEdge.value, ...updated }
}

// === 编辑连线（右键菜单触发） ===
const handleEditEdge = (edgeId: string, mouseEvent: MouseEvent) => {
  const data = graphRef.value?.getData()
  const edge = data?.edges?.find((e: any) => e.id === edgeId)
  if (!edge) return
  savedEdgeSnapshot = JSON.parse(JSON.stringify(edge))
  selectedEdge.value = edge
  // 创建虚拟锚点
  const anchor = document.createElement('div')
  anchor.style.cssText = `position:fixed;left:${mouseEvent.clientX}px;top:${mouseEvent.clientY}px;width:0;height:0;pointer-events:none;`
  document.body.appendChild(anchor)
  popoverAnchor.value = anchor
  showEdgePopover.value = true
}

const closeEdgePopover = () => {
  showEdgePopover.value = false
  if (popoverAnchor.value) {
    popoverAnchor.value.remove()
    popoverAnchor.value = undefined
  }
  selectedEdge.value = null
  savedEdgeSnapshot = null
  nextTick(() => graphRef.value?.resize())
}

const handleEdgeSave = (updated: any) => {
  const data = graphRef.value?.getData()
  graphRef.value?.setData({
    nodes: data?.nodes ?? [],
    edges: (data?.edges ?? []).map((e: any) => e.id === updated.id ? { ...e, ...updated } : e),
  })
  closeEdgePopover()
}

const handleEdgeCancel = () => {
  if (savedEdgeSnapshot) {
    const data = graphRef.value?.getData()
    graphRef.value?.setData({
      nodes: data?.nodes ?? [],
      edges: (data?.edges ?? []).map((e: any) => e.id === savedEdgeSnapshot.id ? savedEdgeSnapshot : e),
    })
  }
  closeEdgePopover()
}

onMounted(async () => {
  await loadTopologyList()
  // 默认加载第一个或路由参数指定的
  const idParam = route.params.id ? Number(route.params.id) : null
  const targetId = idParam ?? topologyList.value[0]?.id
  if (targetId) {
    topologyId.value = targetId
    await loadTopologyData(targetId)
  }
})
</script>

<template>
  <div class="topology-page">
    <!-- 顶栏：拓扑选择 + 操作 -->
    <div class="topology-header">
      <div class="topology-selector">
        <el-select
          :model-value="topologyId"
          placeholder="选择拓扑图"
          style="width: 240px"
          @update:model-value="(v: number) => switchTopology(v)"
        >
          <el-option
            v-for="t in topologyList"
            :key="t.id"
            :label="t.name"
            :value="t.id"
          />
        </el-select>
        <el-button type="primary" plain @click="handleCreateTopology">
          <el-icon><Plus /></el-icon>新建
        </el-button>
        <el-button
          v-if="topologyId"
          type="danger"
          plain
          @click="handleDeleteTopology"
        >
          删除
        </el-button>
      </div>
      <TopologyToolbar
        :editing="editing"
        @toggle-edit="editing = !editing"
        @add-device="showDeviceSelector = true"
        @add-custom="handleAddCustom"
        @delete-selected="handleDeleteSelected"
        @save="handleSave"
      />
    </div>

    <!-- 画布 -->
    <div class="topology-content">
      <TopologyGraph
        ref="graphRef"
        :topology-id="topologyId ?? undefined"
        :editing="editing"
        @edit-node="handleEditNode"
        @edit-edge="handleEditEdge"
      />
    </div>

    <!-- 节点属性弹窗 -->
    <el-popover
      v-model:visible="showNodePopover"
      :virtual-ref="popoverAnchor"
      :virtual-triggering="true"
      placement="right"
      :width="280"
      trigger="contextmenu"
    >
      <template #header>
        <div style="display:flex;justify-content:space-between;align-items:center;">
          <span>节点属性</span>
          <el-icon style="cursor:pointer" @click="closePopover"><Close /></el-icon>
        </div>
      </template>
      <template #default>
        <TopologyNodePanel
          v-if="selectedNode"
          :node="selectedNode"
          @update="handleNodeUpdate"
          @save="handleNodeSave"
          @cancel="handleNodeCancel"
        />
      </template>
    </el-popover>

    <!-- 连线属性弹窗 -->
    <el-popover
      v-model:visible="showEdgePopover"
      :virtual-ref="popoverAnchor"
      :virtual-triggering="true"
      placement="right"
      :width="320"
      trigger="contextmenu"
    >
      <template #header>
        <div style="display:flex;justify-content:space-between;align-items:center;">
          <span>连线属性</span>
          <el-icon style="cursor:pointer" @click="closeEdgePopover"><Close /></el-icon>
        </div>
      </template>
      <template #default>
        <TopologyEdgePanel
          v-if="selectedEdge"
          :edge="selectedEdge"
          :graph-data="graphRef?.getData()"
          @update="handleEdgeUpdate"
          @save="handleEdgeSave"
          @cancel="handleEdgeCancel"
        />
      </template>
    </el-popover>

    <DeviceSelector
      :visible="showDeviceSelector"
      @select="handleAddDevice"
      @update:visible="showDeviceSelector = $event"
    />
  </div>
</template>

<script lang="ts">
import { Plus, Close } from '@element-plus/icons-vue'
export default { components: { Plus, Close } }
</script>

<style scoped>
.topology-page {
  padding: 16px;
  height: calc(100vh - 60px);
  display: flex;
  flex-direction: column;
  box-sizing: border-box;
  gap: 12px;
}
.topology-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  flex-shrink: 0;
}
.topology-selector {
  display: flex;
  align-items: center;
  gap: 8px;
}
.topology-content {
  display: flex;
  flex: 1;
  min-height: 0;
}
</style>
