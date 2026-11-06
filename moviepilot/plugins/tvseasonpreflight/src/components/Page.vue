<script setup>
import { computed, onMounted, ref } from 'vue'

const props = defineProps({ api: { type: Object, default: () => ({}) } })
const loading = ref(false)
const error = ref('')
const message = ref('')
const dialogOpen = ref(false)
const logTab = ref('success')
const state = ref({ installed: false, enabled: false, success_count: 0, skipped_count: 0, success_logs: [], skipped_logs: [], flow: '', path_mode: '' })
const totalLogs = computed(() => (state.value.success_count || 0) + (state.value.skipped_count || 0))
const logHeaders = [
  { title: '时间', key: 'date', width: 200 },
  { title: '处理结果', key: 'result', width: 120 },
  { title: '详细说明', key: 'message' },
]
const unwrap = response => response?.data?.data ?? response?.data ?? response

async function loadStatus() {
  loading.value = true
  try {
    const response = await props.api.post('plugin/TVSeasonPreflight/ui_status', {})
    state.value = unwrap(response) || state.value
    error.value = ''
  } catch (err) { error.value = err?.message || '读取状态失败' }
  finally { loading.value = false }
}

async function toggleEngine(value) {
  loading.value = true
  try {
    const response = await props.api.post('plugin/TVSeasonPreflight/toggle', { enabled: value })
    const body = response?.data ?? response
    if (body?.success === false) error.value = body.message || '操作失败'
    else {
      message.value = body?.message || '设置已保存'
      if (body?.data) state.value = body.data
    }
  } catch (err) { error.value = err?.message || '操作失败' }
  finally { loading.value = false }
}

function openLogs(tab) { logTab.value = tab; dialogOpen.value = true }
onMounted(loadStatus)
</script>

<template>
  <div class="preflight-page">
    <VProgressLinear v-if="loading" indeterminate class="mb-3" />
    <VAlert v-if="error" type="error" variant="tonal" closable class="mb-3">{{ error }}</VAlert>
    <VAlert v-if="message" type="success" variant="tonal" closable class="mb-3">{{ message }}</VAlert>

    <div class="card-grid">
      <VCard class="status-card card-status">
        <VCardText>
          <div class="card-head"><span>引擎状态</span><VSwitch :model-value="state.enabled" color="success" hide-details density="compact" :disabled="!state.installed || loading" @update:model-value="toggleEngine" /></div>
          <div class="card-value">{{ state.installed ? (state.enabled ? '已启用' : '已停用') : '未安装' }}</div>
          <div class="card-note">控制入库前自动分季</div>
        </VCardText>
      </VCard>
      <VCard class="status-card card-flow">
        <VCardText><div class="card-label">执行时机</div><div class="flow-text">下载完成后、移动上传前</div><div class="card-note">先核对 TMDB，再生成目标季度路径</div></VCardText>
      </VCard>
      <VCard class="status-card card-success" @click="openLogs('success')">
        <VCardText><div class="card-label">自动分季成功</div><div class="count-value">{{ state.success_count || 0 }}</div><div class="card-note">查看成功日志</div><VIcon class="arrow" icon="mdi-chevron-right" /></VCardText>
      </VCard>
      <VCard class="status-card card-skipped" @click="openLogs('skipped')">
        <VCardText><div class="card-label">安全阻止</div><div class="count-value">{{ state.skipped_count || 0 }}</div><div class="card-note">缺集、重复或同一 TMDB 已入库时停止整理</div><VIcon class="arrow" icon="mdi-chevron-right" /></VCardText>
      </VCard>
      <VCard class="status-card card-logs" @click="openLogs('success')">
        <VCardText><div class="card-label">处理日志</div><div class="count-value">{{ totalLogs }}</div><div class="card-note">成功与安全跳过记录</div><VIcon class="arrow" icon="mdi-chevron-right" /></VCardText>
      </VCard>
    </div>

    <VAlert type="info" variant="tonal" class="mt-4">{{ state.flow }}<br>{{ state.path_mode }}<br>不会原地重命名做种文件；不满足严格条件时保持原任务不变。</VAlert>

    <VDialog v-model="dialogOpen" max-width="1120" scrollable>
      <VCard class="dialog-card">
        <VCardTitle class="dialog-title"><span>入库前分季日志</span><VBtn icon="mdi-close" variant="text" @click="dialogOpen = false" /></VCardTitle>
        <VDivider />
        <VTabs v-model="logTab" class="log-tabs"><VTab value="success">成功日志（{{ state.success_count || 0 }}）</VTab><VTab value="skipped">安全阻止（{{ state.skipped_count || 0 }}）</VTab></VTabs>
        <VDivider />
        <div v-if="logTab === 'success'" class="dialog-body"><VDataTable :headers="logHeaders" :items="state.success_logs" :items-per-page="20" class="data-table"><template #item.result><span class="success-text">已自动分季</span></template><template #no-data><div class="empty">暂无成功日志</div></template></VDataTable></div>
        <div v-else class="dialog-body"><VDataTable :headers="logHeaders" :items="state.skipped_logs" :items-per-page="20" class="data-table"><template #item.result><span class="skipped-text">已阻止</span></template><template #no-data><div class="empty">暂无阻止日志</div></template></VDataTable></div>
      </VCard>
    </VDialog>
  </div>
</template>

<style scoped>
.preflight-page { padding: 6px 2px 28px; }
.card-grid { display: grid; grid-template-columns: repeat(5, minmax(170px, 1fr)); gap: 10px; }
.status-card { position: relative; min-height: 128px; border-radius: 12px; box-shadow: none; }
.card-status { background: #172d1c; color: #62d123; }
.card-flow { background: #132b3b; color: #29b6f6; }
.card-success { background: #172d1c; color: #62d123; cursor: pointer; }
.card-skipped { background: #352c17; color: #ffb300; cursor: pointer; }
.card-logs { background: #251d3d; color: #9b6cff; cursor: pointer; }
.card-success:hover,.card-skipped:hover,.card-logs:hover { filter: brightness(1.14); }
.card-head { display: flex; align-items: center; justify-content: space-between; font-size: .83rem; font-weight: 600; }
.card-label { color: currentColor; font-size: .83rem; font-weight: 600; margin-bottom: 8px; }
.card-value,.count-value { color: rgba(255,255,255,.92); font-size: 1.55rem; line-height: 1.2; font-weight: 750; }
.flow-text { color: rgba(255,255,255,.9); font-size: 1rem; font-weight: 650; margin-top: 15px; }
.card-note { margin-top: 12px; color: currentColor; font-size: .76rem; line-height: 1.35; }
.arrow { position: absolute; right: 14px; top: 50%; transform: translateY(-50%); color: currentColor; }
.dialog-card { max-height: 88vh; background: #12131c; border: 1px solid rgba(255,255,255,.08); }
.dialog-title { display: flex; align-items: center; justify-content: space-between; padding: 14px 18px; }
.log-tabs { padding: 0 12px; }
.dialog-body { padding: 16px; max-height: 70vh; overflow-y: auto; }
.data-table { background: transparent; }
.data-table :deep(thead th) { color: rgba(255,255,255,.82); border-bottom-color: rgba(255,255,255,.12) !important; }
.data-table :deep(tbody td) { color: rgba(255,255,255,.68); border-bottom-color: rgba(255,255,255,.09) !important; }
.success-text { color: #69d62c; }.skipped-text { color: #ffb300; }
.empty { padding: 40px 12px; text-align: center; color: rgba(255,255,255,.55); }
@media (max-width: 1100px) { .card-grid { grid-template-columns: repeat(3, minmax(170px, 1fr)); } }
@media (max-width: 700px) { .card-grid { grid-template-columns: repeat(2, minmax(160px, 1fr)); } }
@media (max-width: 450px) { .card-grid { grid-template-columns: 1fr; } }
</style>
