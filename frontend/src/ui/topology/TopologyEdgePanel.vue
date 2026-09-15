<script setup lang="ts">
import { ref, watch } from 'vue'
import { fetchAllPages } from '@/utils/fetchAllPages'

const props = defineProps<{
  edge: any
  graphData?: { nodes?: any[]; edges?: any[] }
}>()
const emit = defineEmits<{
  (e: 'update', data: any): void
  (e: 'save', data: any): void
  (e: 'cancel'): void
}>()

const sourceInterface = ref('')
const targetInterface = ref('')
const edgeType = ref('physical')
const label = ref('')

// 接口选项
const sourceInterfaces = ref<any[]>([])
const targetInterfaces = ref<any[]>([])
const loadingInterfaces = ref(false)

// 两端设备信息
const sourceDeviceName = ref('')
const targetDeviceName = ref('')

watch(() => props.edge, async (e) => {
  if (!e) return
  sourceInterface.value = e.data?.source_interface || e.sourceInterface || ''
  targetInterface.value = e.data?.target_interface || e.targetInterface || ''
  edgeType.value = e.data?.edge_type || 'physical'
  label.value = e.label || e.data?.label || ''

  // 根据连线两端节点获取设备接口
  await loadInterfaces(e.source, e.target)
}, { immediate: true })

const loadInterfaces = async (sourceId: string, targetId: string) => {
  if (!props.graphData?.nodes) return
  loadingInterfaces.value = true
  try {
    // 找到两端节点关联的设备 ID 和名称
    const sourceNode = props.graphData.nodes.find((n: any) => n.id === sourceId)
    const targetNode = props.graphData.nodes.find((n: any) => n.id === targetId)
    const sourceDeviceId = sourceNode?.data?.device_id
    const targetDeviceId = targetNode?.data?.device_id
    sourceDeviceName.value = sourceNode?.label || sourceNode?.id || '未知设备'
    targetDeviceName.value = targetNode?.label || targetNode?.id || '未知设备'

    // 并行加载两端接口
    const promises: Promise<any>[] = []
    if (sourceDeviceId) {
      promises.push(
        // 接口下拉需覆盖该设备全部接口，分页会截断（page_size=500 会被后端上限截断且仅返回第一页）
        fetchAllPages('/api/assets/interfaces/', { device: sourceDeviceId })
          .then(list => { sourceInterfaces.value = list })
          .catch(() => { sourceInterfaces.value = [] })
      )
    } else {
      sourceInterfaces.value = []
    }
    if (targetDeviceId) {
      promises.push(
        fetchAllPages('/api/assets/interfaces/', { device: targetDeviceId })
          .then(list => { targetInterfaces.value = list })
          .catch(() => { targetInterfaces.value = [] })
      )
    } else {
      targetInterfaces.value = []
    }
    await Promise.all(promises)
  } finally {
    loadingInterfaces.value = false
  }
}

const getUpdatedEdge = () => {
  return {
    ...props.edge,
    label: label.value,
    sourceInterface: sourceInterface.value,
    targetInterface: targetInterface.value,
    data: {
      ...(props.edge.data || {}),
      source_interface: sourceInterface.value,
      target_interface: targetInterface.value,
      edge_type: edgeType.value,
      label: label.value,
    },
  }
}

const handleSave = () => {
  emit('save', getUpdatedEdge())
}

const handleCancel = () => {
  emit('cancel')
}
</script>

<template>
  <el-form label-position="top" size="small" v-loading="loadingInterfaces">
    <el-form-item :label="`源接口（${sourceDeviceName}）`">
      <el-select
        v-model="sourceInterface"
        :placeholder="sourceInterfaces.length ? '选择或输入接口' : '输入接口名称'"
        filterable
        allow-create
        clearable
        default-first-option
        style="width: 100%"
      >
        <el-option
          v-for="iface in sourceInterfaces"
          :key="iface.id"
          :label="iface.interface"
          :value="iface.interface"
        />
      </el-select>
    </el-form-item>
    <el-form-item :label="`目标接口（${targetDeviceName}）`">
      <el-select
        v-model="targetInterface"
        :placeholder="targetInterfaces.length ? '选择或输入接口' : '输入接口名称'"
        filterable
        allow-create
        clearable
        default-first-option
        style="width: 100%"
      >
        <el-option
          v-for="iface in targetInterfaces"
          :key="iface.id"
          :label="iface.interface"
          :value="iface.interface"
        />
      </el-select>
    </el-form-item>
    <el-form-item label="连接类型">
      <el-select v-model="edgeType" style="width: 100%">
        <el-option label="物理连接" value="physical" />
        <el-option label="逻辑连接" value="logical" />
        <el-option label="VRF连接" value="vrf" />
      </el-select>
    </el-form-item>
    <el-form-item label="标签">
      <el-input v-model="label" />
    </el-form-item>
    <el-form-item>
      <div style="display:flex;gap:8px;justify-content:flex-end;width:100%;">
        <el-button size="small" @click="handleCancel">取消</el-button>
        <el-button type="primary" size="small" @click="handleSave">保存</el-button>
      </div>
    </el-form-item>
  </el-form>
</template>
