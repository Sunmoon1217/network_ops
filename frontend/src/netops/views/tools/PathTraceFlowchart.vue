<script setup lang="ts">
import { actionColor, actionLabel, deviceLabel, hasTranslation } from './usePathTrace'
import type { TraceResult } from '@/types'

defineProps<{ result: TraceResult; srcIp: string }>()
</script>

<template>
  <div class="flowchart-area">
    <el-empty v-if="result.hops.length === 0 && result.lb_backend.length === 0" description="未找到匹配路径" />

    <template v-else>
      <div v-if="result.blocked" class="blocked-alert">流量被阻断：{{ result.blocked_by }}</div>

      <div class="flowchart-scroll">
        <div class="flowchart">
          <div class="flow-node source-node">
            <div class="node-label">源地址</div>
            <div class="node-value">{{ srcIp }}</div>
          </div>

          <template v-for="(hop, idx) in result.hops" :key="idx">
            <div class="flow-edge">
              <svg width="60" height="24"><line x1="0" y1="12" x2="50" y2="12" :stroke="actionColor[hop.action] || '#34c8ff'" stroke-width="2" marker-end="`url(#arrow-${idx})`" /><defs><marker :id="`arrow-${idx}`" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="8" markerHeight="8"><path d="M0 0 L10 5 L0 10z" :fill="actionColor[hop.action] || '#34c8ff'" /></marker></defs></svg>
            </div>

            <div class="flow-node device-node" :style="{ borderLeftColor: actionColor[hop.action] || '#34c8ff' }">
              <div class="node-header">
                <strong>{{ hop.device_name }}</strong>
                <el-tag size="small" effect="plain">{{ deviceLabel[hop.device_type] || hop.device_type }}</el-tag>
                <el-tag v-if="hop.zone" size="small" effect="plain" type="info">{{ hop.zone }}</el-tag>
                <el-tag v-if="hop.vrf && hop.vrf !== 'default'" size="small" effect="plain" type="warning">{{ hop.vrf }}</el-tag>
              </div>
              <div class="node-body">
                <el-tag size="small" :type="hop.action === 'allow' ? 'success' : 'danger'">{{ actionLabel[hop.action] || hop.action }}</el-tag>
                <div v-if="hop.matched_route" class="detail">
                  <span class="label">路由</span> {{ hop.matched_route.destination }}
                  <template v-if="hop.matched_route.nexthop"> → {{ hop.matched_route.nexthop }}</template>
                  <template v-else-if="hop.matched_route.interface"> via {{ hop.matched_route.interface }}</template>
                </div>
                <div v-if="hop.matched_policy" class="detail">
                  <span class="label">策略</span> [{{ hop.matched_policy.policy_id }}] {{ hop.matched_policy.name }}
                </div>
                <div v-if="hop.matched_nat && hasTranslation(hop)" class="detail">
                  <span class="label">{{ hop.matched_nat.nat_type.toUpperCase() }}</span>
                  <span v-if="hop.src_after">{{ hop.src_before }} → {{ hop.src_after }}</span>
                  <span v-if="hop.dst_after">{{ hop.dst_before }} → {{ hop.dst_after }}</span>
                </div>
              </div>
            </div>
          </template>

          <template v-if="!result.blocked && result.hops.length > 0">
            <div class="flow-edge">
              <svg width="60" height="24"><line x1="0" y1="12" x2="50" y2="12" stroke="#18a058" stroke-width="2" marker-end="url(#arrow-dest)" /><defs><marker id="arrow-dest" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="8" markerHeight="8"><path d="M0 0 L10 5 L0 10z" fill="#18a058" /></marker></defs></svg>
            </div>
            <div class="flow-node dest-node">
              <div class="node-label">目的地址</div>
              <div class="node-value">{{ result.final_dst }}<template v-if="result.final_port">:{{ result.final_port }}</template></div>
            </div>
          </template>
        </div>
      </div>
    </template>
  </div>
</template>

<style scoped>
.flowchart-area { flex: 1; min-height: 0; display: flex; flex-direction: column; gap: 12px; }
.blocked-alert { padding: 10px 16px; border-radius: 8px; background: rgba(208, 48, 80, 0.08); border: 1px solid rgba(208, 48, 80, 0.2); color: #d03050; font-size: 14px; }
.flowchart-scroll { flex: 1; min-height: 0; overflow: auto; border-radius: 8px; border: 1px solid var(--el-border-color-lighter); padding: 24px; }
.flowchart { display: flex; align-items: center; gap: 0; min-width: max-content; }
.flow-node { display: flex; flex-direction: column; gap: 6px; border-radius: 10px; border: 1px solid var(--el-border-color-lighter); padding: 12px; min-width: 160px; max-width: 240px; flex-shrink: 0; }
.source-node { border-color: rgba(52, 200, 255, 0.3); background: rgba(52, 200, 255, 0.06); }
.dest-node { border-color: rgba(24, 160, 88, 0.3); background: rgba(24, 160, 88, 0.06); }
.device-node { border-left: 3px solid #34c8ff; }
.node-label { font-size: 11px; color: var(--el-text-color-secondary); text-transform: uppercase; }
.node-value { font-size: 13px; font-weight: 600; font-family: monospace; }
.node-header { display: flex; align-items: center; gap: 6px; flex-wrap: wrap; }
.node-body { display: flex; flex-direction: column; gap: 4px; }
.detail { font-size: 12px; }
.label { font-size: 11px; color: var(--el-text-color-secondary); margin-right: 4px; }
.flow-edge { display: flex; align-items: center; width: 60px; flex-shrink: 0; }
</style>
