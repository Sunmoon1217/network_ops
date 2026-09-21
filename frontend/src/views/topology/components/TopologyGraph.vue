<script setup lang="ts">
import { Graph, type GraphData } from '@/composables/useG6'
import { onMounted, onBeforeUnmount, ref, watch } from 'vue'

const props = withDefaults(defineProps<{
  topologyId?: number
  editing?: boolean
}>(), {
  editing: false,
})

const emit = defineEmits<{
  (e: 'save', data: GraphData): void
  (e: 'edit-node', nodeId: string, mouseEvent: MouseEvent): void
  (e: 'edit-edge', edgeId: string, mouseEvent: MouseEvent): void
}>()

const containerRef = ref<HTMLElement>()
let graph: Graph | null = null
let currentData: GraphData = { nodes: [], edges: [] }
let resizeObserver: ResizeObserver | null = null

// 右键菜单点击兜底
let contextmenuClickHandler: ((e: MouseEvent) => void) | null = null

const getBehaviors = () => {
  const base: any[] = [
    'drag-canvas',
    { type: 'scroll-canvas', minZoom: 0.2, maxZoom: 3 },
  ]

  if (props.editing) {
    return [
      ...base,
      { type: 'drag-element', key: 'drag-element' },
      { type: 'click-select', multiple: false },
      {
        type: 'create-edge',
        key: 'create-edge',
        trigger: 'click',
        enable: false, // 默认禁用，右键菜单触发后启用
        style: { stroke: '#1890ff', lineWidth: 1.5, lineDash: [6, 3] },
        onCreate: (edge: any) => ({
          ...edge,
          id: `edge-${edge.source}-${edge.target}-${Date.now()}`,
          style: { stroke: '#91caff', lineWidth: 1.5 },
        }),
        onFinish: () => {
          // 连线完成，禁用 create-edge
          disableLinking()
          currentData = graph?.getData() ?? { nodes: [], edges: [] }
          emit('save', currentData)
        },
      },
    ]
  }

  return base
}

/** 启用连线模式 */
const enableLinking = () => {
  if (!graph) return
  graph.updateBehavior({ key: 'create-edge', enable: true })
  if (containerRef.value) containerRef.value.style.cursor = 'crosshair'
}

/** 禁用连线模式 */
const disableLinking = () => {
  if (!graph) return
  graph.updateBehavior({ key: 'create-edge', enable: false })
  if (containerRef.value) containerRef.value.style.cursor = ''
}

/** 删除指定节点及其关联边 */
const removeNode = (nodeId: string) => {
  if (!graph) return
  const data = graph.getData()
  const relatedEdges = data.edges?.filter((e: any) => e.source === nodeId || e.target === nodeId).map((e: any) => e.id) ?? []
  if (relatedEdges.length) graph.removeEdgeData(relatedEdges)
  graph.removeNodeData([nodeId])
  graph.draw()
  emit('save', graph.getData())
}

/** 删除指定边 */
const removeEdge = (edgeId: string) => {
  if (!graph) return
  graph.removeEdgeData([edgeId])
  graph.draw()
  emit('save', graph.getData())
}

const initGraph = async () => {
  if (!containerRef.value) return
  const w = containerRef.value.clientWidth
  const h = containerRef.value.clientHeight || 600

  graph = new Graph({
    container: containerRef.value,
    width: w,
    height: h,
    behaviors: getBehaviors(),
    autoFit: 'center',
    background: 'transparent',
    plugins: props.editing
      ? [{
          key: 'contextmenu',
          type: 'contextmenu',
          trigger: 'contextmenu',
          // 全画布触发，不再限制 targetType
          getItems: (event: any) => {
            const { targetType } = event
            if (targetType === 'node') {
              return [
                { name: '🔗 连线', value: 'link' },
                { name: '✏️ 编辑属性', value: 'edit' },
                { name: '🗑️ 删除节点', value: 'delete-node' },
              ]
            } else if (targetType === 'edge') {
              return [
                { name: '✏️ 编辑连线', value: 'edit-edge' },
                { name: '🗑️ 删除连线', value: 'delete-edge' },
              ]
            } else {
              // 画布空白处
              return [
                { name: '🔗 连线', value: 'link' },
                { name: '➕ 添加自定义节点', value: 'add-custom' },
              ]
            }
          },
          onClick: (value: string, _target: HTMLElement, current: any) => {
            switch (value) {
              case 'delete-node':
                if (current?.id) removeNode(current.id)
                break
              case 'delete-edge':
                if (current?.id) removeEdge(current.id)
                break
            }
          },
        }]
      : [],
    node: {
      style: {
        size: 64,
        fill: '#ffffff',
        stroke: '#d9d9d9',
        lineWidth: 1.5,
        radius: 10,
        labelFill: '#333',
        labelFontSize: 11,
        labelPlacement: 'bottom',
        labelOffsetY: 8,
        labelText: (d: any) => d.label || '',
        labelWordWrap: true,
        labelMaxWidth: 120,
        cursor: 'pointer',
        ports: [],
      },
      state: {
        hover: {
          stroke: '#40a9ff',
          lineWidth: 2,
        },
        selected: {
          stroke: '#1890ff',
          lineWidth: 2.5,
          shadowColor: 'rgba(24,144,255,0.35)',
          shadowBlur: 12,
        },
      },
    },
    edge: {
      style: {
        stroke: '#91caff',
        lineWidth: 1.5,
        endArrow: false,
      },
      state: {
        selected: { stroke: '#1890ff', lineWidth: 2.5 },
      },
    },
  })

  await graph.render()
  if (currentData.nodes?.length || currentData.edges?.length) {
    graph.setData(currentData)
    await graph.render()
  }

  // 拖拽过程中持续同步节点位置到 currentData
  if (props.editing) {
    graph.on('node:drag', () => {
      if (graph) currentData = graph.getData()
    })
    graph.on('node:dragend', () => {
      if (graph) currentData = graph.getData()
    })
  }

  // 右键菜单点击兜底（事件委托）
  if (props.editing) {
    contextmenuClickHandler = (e: MouseEvent) => {
      const target = e.target as HTMLElement
      if (!target) return
      const li = target.closest('.g6-contextmenu-li') as HTMLElement | null
      if (!li) return
      const value = li.getAttribute('value')
      if (!value) return
      const menuEl = document.querySelector('.g6-contextmenu')
      if (!menuEl || (menuEl as HTMLElement).style.display === 'none') return
      const plugin = graph?.getPluginInstance?.('contextmenu') as any
      const currentElement = plugin?.targetElement
      const elementId = currentElement?.id
      setTimeout(() => {
        switch (value) {
          case 'link':
            enableLinking()
            break
          case 'edit':
            if (elementId) emit('edit-node', elementId, e)
            break
          case 'edit-edge':
            if (elementId) emit('edit-edge', elementId, e)
            break
          case 'add-custom':
            if (graph) {
              const pos = {
                x: containerRef.value ? containerRef.value.clientWidth / 2 + (Math.random() - 0.5) * 200 : 400,
                y: containerRef.value ? containerRef.value.clientHeight / 2 + (Math.random() - 0.5) * 200 : 300,
              }
              graph.addNodeData([{
                id: `custom-${Date.now()}`,
                label: '自定义节点',
                data: { device_type: 'custom' },
                ...pos,
              } as any])
              currentData = graph.getData()
              graph.draw()
            }
            break
        }
      }, 0)
    }
    document.addEventListener('click', contextmenuClickHandler, true)
  }

  resizeObserver = new ResizeObserver((entries) => {
    if (!graph || !containerRef.value) return
    const entry = entries[0]; if (!entry) return
    const { width, height } = entry.contentRect
    if (width > 0 && height > 0) {
      graph.resize(width, height)
      graph.render()
    }
  })
  resizeObserver.observe(containerRef.value)
}

watch(() => props.editing, () => {
  // 退出编辑前，同步最新数据（包括节点位置）
  if (graph) {
    currentData = graph.getData()
    // 禁用连线模式，清理临时状态
    try { graph.updateBehavior({ key: 'create-edge', enable: false }) } catch {}
  }
  if (contextmenuClickHandler) {
    document.removeEventListener('click', contextmenuClickHandler, true)
    contextmenuClickHandler = null
  }
  if (graph) { graph.destroy(); graph = null }
  initGraph()
})

onMounted(() => { initGraph() })

onBeforeUnmount(() => {
  if (contextmenuClickHandler) {
    document.removeEventListener('click', contextmenuClickHandler, true)
    contextmenuClickHandler = null
  }
  if (resizeObserver) { resizeObserver.disconnect(); resizeObserver = null }
  if (graph) { graph.destroy(); graph = null }
})

const getCenter = (): { x: number; y: number } => {
  if (!containerRef.value) return { x: 400, y: 300 }
  return {
    x: containerRef.value.clientWidth / 2 + (Math.random() - 0.5) * 200,
    y: containerRef.value.clientHeight / 2 + (Math.random() - 0.5) * 200,
  }
}

const getData = (): GraphData => { return graph?.getData() ?? { nodes: [], edges: [] } }

const setData = (data: GraphData) => {
  currentData = data
  if (!graph) return
  graph.setData(data)
  graph.render()
}

const addNode = (node: { id: string; [key: string]: any }) => {
  if (!graph) return
  const pos = node.x != null && node.y != null ? { x: node.x, y: node.y } : getCenter()
  graph.addNodeData([{ ...node, ...pos } as any])
  currentData = graph.getData()
  graph.draw()
}

const removeSelected = () => {
  if (!graph) return
  const data = graph.getData()
  const selNodes = data.nodes?.filter((n: any) => n.states?.includes('selected')).map((n: any) => n.id) ?? []
  const selEdges = data.edges?.filter((e: any) => e.states?.includes('selected')).map((e: any) => e.id) ?? []
  if (selNodes.length) graph.removeNodeData(selNodes)
  if (selEdges.length) graph.removeEdgeData(selEdges)
  currentData = graph.getData()
  graph.draw()
}

const resize = () => {
  if (!graph || !containerRef.value) return
  const w = containerRef.value.clientWidth
  const h = containerRef.value.clientHeight
  if (w > 0 && h > 0) {
    graph.resize(w, h)
    graph.draw()
  }
}

defineExpose({ getData, setData, addNode, removeNode, removeEdge, removeSelected, getCenter, resize })
</script>

<template>
  <div ref="containerRef" class="topology-canvas" />
</template>

<style scoped>
.topology-canvas {
  flex: 1;
  min-height: 0;
  width: 100%;
  background: var(--el-bg-color, #fafafa);
  border: 1px solid var(--el-border-color, #d9d9d9);
  border-radius: 4px;
  box-shadow: inset 0 1px 4px rgba(0, 0, 0, 0.12);
}
</style>

<style>
/* 禁用拓扑画布的被动事件，消除 G6 contextmenu 的 console 警告 */
.topology-canvas {
  touch-action: manipulation;
}
.g6-contextmenu {
  min-width: 140px;
  background: #fff !important;
  border-radius: 6px !important;
  box-shadow: 0 6px 16px rgba(0, 0, 0, 0.12), 0 3px 6px rgba(0, 0, 0, 0.08) !important;
  font-size: 13px;
  color: #333;
  padding: 4px 0;
}
.g6-contextmenu-ul {
  max-width: none !important;
}
.g6-contextmenu-li {
  padding: 8px 14px !important;
  cursor: pointer;
  user-select: none;
  transition: background 0.15s;
  white-space: nowrap;
}
.g6-contextmenu-li:hover {
  background: #f0f5ff !important;
}
.g6-contextmenu-li[value^="delete"] {
  color: #f5222d;
}
.g6-contextmenu-li[value^="delete"]:hover {
  background: #fff1f0 !important;
}
</style>
