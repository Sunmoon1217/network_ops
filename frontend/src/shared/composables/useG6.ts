/**
 * G6 按需引入
 *
 * 绕过 @antv/g6 主入口（会触发 preset.js 全量注册 150+ 组件），
 * 直接从子模块导入 Graph 运行时 + 仅注册实际使用的行为/布局/元素。
 */
import { Graph } from '@antv/g6/esm/runtime/graph'
import type { GraphData } from '@antv/g6/esm/spec/data'
import { register } from '@antv/g6/esm/registry/register'
import { ExtensionCategory } from '@antv/g6/esm/constants/registry'

// 行为
import { DragCanvas } from '@antv/g6/esm/behaviors/drag-canvas'
import { ScrollCanvas } from '@antv/g6/esm/behaviors/scroll-canvas'
import { DragElement } from '@antv/g6/esm/behaviors/drag-element'
import { ClickSelect } from '@antv/g6/esm/behaviors/click-select'
import { CreateEdge } from '@antv/g6/esm/behaviors/create-edge'

// 布局
import { GridLayout } from '@antv/g6/esm/layouts'

// 元素
import { Rect } from '@antv/g6/esm/elements/nodes/rect'
import { Circle } from '@antv/g6/esm/elements/nodes/circle'
import { Line } from '@antv/g6/esm/elements/edges/line'

// 插件
import { Tooltip } from '@antv/g6/esm/plugins/tooltip'
import { Contextmenu } from '@antv/g6/esm/plugins/contextmenu'

// 主题
import { light } from '@antv/g6/esm/themes/light'
import { dark } from '@antv/g6/esm/themes/dark'

// 动画（Graph 运行时依赖）
import {
  Fade,
  Translate,
  NodeCollapse,
  NodeExpand,
  PathIn,
  PathOut,
  ComboCollapse,
  ComboExpand,
} from '@antv/g6/esm/animations'

// Transform（Graph 运行时依赖）
import { UpdateRelatedEdge } from '@antv/g6/esm/transforms/update-related-edge'
import { CollapseExpandNode } from '@antv/g6/esm/transforms/collapse-expand-node'
import { CollapseExpandCombo } from '@antv/g6/esm/transforms/collapse-expand-combo'
import { GetEdgeActualEnds } from '@antv/g6/esm/transforms/get-edge-actual-ends'
import { ArrangeDrawOrder } from '@antv/g6/esm/transforms/arrange-draw-order'

// === 注册 ===

// 行为
register(ExtensionCategory.BEHAVIOR, 'drag-canvas', DragCanvas)
register(ExtensionCategory.BEHAVIOR, 'scroll-canvas', ScrollCanvas)
register(ExtensionCategory.BEHAVIOR, 'drag-element', DragElement)
register(ExtensionCategory.BEHAVIOR, 'click-select', ClickSelect)
register(ExtensionCategory.BEHAVIOR, 'create-edge', CreateEdge)

// 布局
register(ExtensionCategory.LAYOUT, 'grid', GridLayout)

// 元素
register(ExtensionCategory.NODE, 'rect', Rect)
register(ExtensionCategory.NODE, 'circle', Circle)
register(ExtensionCategory.EDGE, 'line', Line)

// 插件
register(ExtensionCategory.PLUGIN, 'tooltip', Tooltip)
register(ExtensionCategory.PLUGIN, 'contextmenu', Contextmenu)

// 主题
register(ExtensionCategory.THEME, 'light', light)
register(ExtensionCategory.THEME, 'dark', dark)

// 动画
register(ExtensionCategory.ANIMATION, 'fade', Fade)
register(ExtensionCategory.ANIMATION, 'translate', Translate)
register(ExtensionCategory.ANIMATION, 'node-collapse', NodeCollapse)
register(ExtensionCategory.ANIMATION, 'node-expand', NodeExpand)
register(ExtensionCategory.ANIMATION, 'path-in', PathIn)
register(ExtensionCategory.ANIMATION, 'path-out', PathOut)
register(ExtensionCategory.ANIMATION, 'combo-collapse', ComboCollapse)
register(ExtensionCategory.ANIMATION, 'combo-expand', ComboExpand)

// Transform
register(ExtensionCategory.TRANSFORM, 'update-related-edges', UpdateRelatedEdge)
register(ExtensionCategory.TRANSFORM, 'collapse-expand-node', CollapseExpandNode)
register(ExtensionCategory.TRANSFORM, 'collapse-expand-combo', CollapseExpandCombo)
register(ExtensionCategory.TRANSFORM, 'get-edge-actual-ends', GetEdgeActualEnds)
register(ExtensionCategory.TRANSFORM, 'arrange-draw-order', ArrangeDrawOrder)

export { Graph }
export type { GraphData }
export { register, ExtensionCategory }
