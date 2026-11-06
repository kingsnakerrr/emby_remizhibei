<script setup>
import { computed, onMounted, onUnmounted, ref } from 'vue'

const props = defineProps({ api: { type: Object, default: () => ({}) } })
const loading = ref(false)
const message = ref('')
const error = ref('')
const dialog = ref('')
const recordTab = ref('scan')
const scanSearch = ref('')
const overrideOpen = ref(false)
const rulesOpen = ref(false)
const overrideForm = ref({
  tmdb_id: 0, title: '', counts: '', target_tmdb_id: '', target_season: '',
  target_title: '', source: '人工核对', note: '',
})
const state = ref({
  headline: '正在读取状态…', summary: {}, scan_results: [], active_jobs: [],
  success_jobs: [], failed_jobs: [], scan_logs: [], other_logs: [], actions: [], season_overrides: [],
})
let timer

const summary = computed(() => state.value.summary || {})
const dialogOpen = computed({
  get: () => Boolean(dialog.value),
  set: value => { if (!value) dialog.value = '' },
})
const unwrap = response => response?.data?.data ?? response?.data ?? response
const formatDuration = row => row?.duration_seconds === undefined ? '—' : `${row.duration_seconds} 秒`
const scanHeaders = [
  { title: '媒体', key: 'name' },
  { title: '当前季度', key: 'current_summary', width: 230 },
  { title: '判定季度', key: 'official_summary', width: 230 },
  { title: '判断', key: 'status', width: 150 },
  { title: '操作', key: 'actions', sortable: false, width: 170 },
]
const jobHeaders = [
  { title: '媒体', key: 'name' },
  { title: '开始时间', key: 'started_at', width: 190 },
  { title: '结束时间', key: 'finished_at', width: 190 },
  { title: '耗时', key: 'duration', width: 100 },
  { title: '结果', key: 'message' },
]
const operationHeaders = [
  { title: '任务', key: 'title', width: 190 },
  { title: '开始时间', key: 'started_at', width: 190 },
  { title: '结束时间', key: 'finished_at', width: 190 },
  { title: '耗时', key: 'duration', width: 100 },
  { title: '结果', key: 'detail' },
]

async function loadStatus(silent = false) {
  if (!silent) loading.value = true
  try {
    const response = await props.api.post('plugin/TVSeasonRepair/ui_status', {})
    state.value = unwrap(response) || state.value
    error.value = ''
  } catch (err) {
    error.value = err?.message || '读取状态失败'
  } finally {
    if (!silent) loading.value = false
  }
}

async function run(path, payload = {}, successText = '') {
  loading.value = true
  error.value = ''
  message.value = ''
  try {
    const response = await props.api.post(`plugin/TVSeasonRepair/${path}`, payload)
    const body = response?.data ?? response
    if (body?.success === false) error.value = body.message || '操作失败'
    else message.value = body?.message || successText || '操作已提交'
    await loadStatus(true)
  } catch (err) {
    error.value = err?.message || '操作失败'
  } finally {
    loading.value = false
  }
}

function openDialog(name, tab = '') {
  dialog.value = name
  if (tab) recordTab.value = tab
}

function openOverride(item) {
  const saved = (state.value.season_overrides || []).find(row => Number(row.tmdb_id) === Number(item.tmdb_id))
  overrideForm.value = {
    tmdb_id: Number(item.tmdb_id),
    title: item.name || saved?.title || '',
    counts: saved?.counts?.join(',') || '',
    target_tmdb_id: saved?.target_tmdb_id || '',
    target_season: saved?.target_season || '',
    target_title: saved?.target_title || '',
    source: saved?.source || '人工核对',
    note: saved?.note || '',
  }
  overrideOpen.value = true
}

async function saveOverride(remove = false) {
  const payload = { ...overrideForm.value, delete: remove }
  await run('season_override', payload)
  if (!error.value) overrideOpen.value = false
}

async function removeOverride(item) {
  overrideForm.value = {
    ...item,
    counts: (item.counts || []).join(','),
    target_tmdb_id: item.target_tmdb_id || '',
    target_season: item.target_season || '',
  }
  await saveOverride(true)
}

onMounted(() => {
  loadStatus()
  timer = window.setInterval(() => loadStatus(true), 10000)
})
onUnmounted(() => window.clearInterval(timer))
</script>

<template>
  <div class="season-page">
    <VProgressLinear v-if="loading" indeterminate class="mb-3" />
    <VAlert v-if="error" type="error" variant="tonal" closable class="mb-3">{{ error }}</VAlert>
    <VAlert v-if="message" type="success" variant="tonal" closable class="mb-3">{{ message }}</VAlert>

    <div class="dashboard-grid">
      <VCard class="dash-card card-scan" @click="openDialog('scan')">
        <VCardText>
          <div class="card-label">扫描候选</div>
          <div class="card-value">{{ summary.candidate_count || 0 }}</div>
          <div class="card-note">可安全修复 {{ summary.safe_count || 0 }} 部</div>
          <VIcon class="card-arrow" icon="mdi-chevron-right" />
        </VCardText>
      </VCard>
      <VCard class="dash-card card-active" @click="openDialog('active')">
        <VCardText>
          <div class="card-label">处理中</div>
          <div class="card-value">{{ summary.active_count || 0 }}</div>
          <div class="card-note">查看队列与实时状态</div>
          <VIcon class="card-arrow" icon="mdi-chevron-right" />
        </VCardText>
      </VCard>
      <VCard class="dash-card card-result" @click="openDialog('records', 'success')">
        <VCardText>
          <div class="card-label">修复结果</div>
          <div class="card-value">{{ summary.success_count || 0 }}</div>
          <div class="card-note">失败 {{ summary.failed_count || 0 }} 条</div>
          <VIcon class="card-arrow" icon="mdi-chevron-right" />
        </VCardText>
      </VCard>
      <VCard class="dash-card card-log" @click="openDialog('records', 'scan')">
        <VCardText>
          <div class="card-label">任务记录</div>
          <div class="card-value">{{ summary.log_count || 0 }}</div>
          <div class="card-note">可回滚 {{ summary.rollback_count || 0 }} 条</div>
          <VIcon class="card-arrow" icon="mdi-chevron-right" />
        </VCardText>
      </VCard>
    </div>

    <div class="actions my-4">
      <VBtn class="action-primary" prepend-icon="mdi-magnify" @click="run('scan')">扫描媒体库</VBtn>
      <VBtn class="action-info" prepend-icon="mdi-eye-outline" @click="run('batch', { execute: false })">预览安全项目</VBtn>
      <VBtn class="action-warning" prepend-icon="mdi-tools" @click="run('batch', { execute: true })">批量修复</VBtn>
      <VBtn class="action-info" prepend-icon="mdi-tune" @click="rulesOpen = true">集数与映射规则（{{ state.season_overrides?.length || 0 }}）</VBtn>
      <VBtn class="action-log" prepend-icon="mdi-text-box-outline" @click="openDialog('records', 'scan')">查看任务记录</VBtn>
    </div>

    <VAlert type="info" variant="tonal" class="headline">{{ state.headline }}</VAlert>

    <VDialog v-model="dialogOpen" max-width="1240" scrollable>
      <VCard class="dialog-card">
        <VCardTitle class="dialog-title">
          <span>{{ dialog === 'scan' ? '扫描结果' : dialog === 'active' ? '处理任务' : '任务记录' }}</span>
          <VBtn icon="mdi-close" variant="text" @click="dialog = ''" />
        </VCardTitle>
        <VDivider />

        <VCardText v-if="dialog === 'scan'" class="dialog-body">
          <VAlert type="info" variant="tonal" class="mb-3">默认使用媒体当前绑定的 TMDB。若它是残缺的重复条目，可映射到正确系列的指定季度；只有找不到正确条目时才使用人工集数。</VAlert>
          <VTextField v-model="scanSearch" prepend-inner-icon="mdi-magnify" label="搜索媒体" variant="outlined" density="comfortable" hide-details class="mb-3" />
          <VDataTable :headers="scanHeaders" :items="state.scan_results" :search="scanSearch" :items-per-page="20" class="data-table">
            <template #item.status="{ item }"><span :class="item.safe ? 'status-safe' : 'status-manual'">{{ item.safe ? '可安全修复' : '人工核对' }}</span></template>
            <template #item.actions="{ item }">
              <div v-if="item.safe" class="table-actions">
                <VBtn size="small" class="table-preview" @click="run('apply', { series_rel: item.series_rel, execute: false })">预览</VBtn>
                <VBtn size="small" class="table-fix" @click="run('apply', { series_rel: item.series_rel, execute: true })">修复</VBtn>
              </div>
              <div v-else class="manual-actions">
                <span class="reason-text" :title="item.reason">{{ item.reason }}</span>
                <VBtn size="small" class="table-override" @click="openOverride(item)">设置规则</VBtn>
              </div>
            </template>
          </VDataTable>
        </VCardText>

        <VCardText v-else-if="dialog === 'active'" class="dialog-body">
          <VDataTable :headers="jobHeaders" :items="state.active_jobs" :items-per-page="20" class="data-table">
            <template #item.started_at="{ item }">{{ item.started_at || item.created_at || '—' }}</template>
            <template #item.finished_at>—</template>
            <template #item.duration>运行中</template>
            <template #no-data><div class="empty">当前没有处理中的任务</div></template>
          </VDataTable>
        </VCardText>

        <template v-else>
          <VTabs v-model="recordTab" class="record-tabs" show-arrows>
            <VTab value="scan">扫描日志</VTab>
            <VTab value="success">成功记录</VTab>
            <VTab value="failed">失败记录</VTab>
            <VTab value="operation">预览与回滚</VTab>
            <VTab value="rollback">最近修复</VTab>
          </VTabs>
          <VDivider />
          <div class="record-window">
            <div v-if="recordTab === 'scan'" class="dialog-body"><VDataTable :headers="operationHeaders" :items="state.scan_logs" :items-per-page="20" class="data-table"><template #item.duration="{ item }">{{ formatDuration(item) }}</template><template #no-data><div class="empty">暂无扫描日志</div></template></VDataTable></div>
            <div v-else-if="recordTab === 'success'" class="dialog-body"><VDataTable :headers="jobHeaders" :items="state.success_jobs" :items-per-page="20" class="data-table"><template #item.started_at="{ item }">{{ item.started_at || item.created_at }}</template><template #item.finished_at="{ item }">{{ item.finished_at || item.updated_at }}</template><template #item.duration="{ item }">{{ formatDuration(item) }}</template><template #no-data><div class="empty">暂无成功记录</div></template></VDataTable></div>
            <div v-else-if="recordTab === 'failed'" class="dialog-body"><VDataTable :headers="jobHeaders" :items="state.failed_jobs" :items-per-page="20" class="data-table"><template #item.started_at="{ item }">{{ item.started_at || item.created_at }}</template><template #item.finished_at="{ item }">{{ item.finished_at || item.updated_at }}</template><template #item.duration="{ item }">{{ formatDuration(item) }}</template><template #no-data><div class="empty">暂无失败记录</div></template></VDataTable></div>
            <div v-else-if="recordTab === 'operation'" class="dialog-body"><VDataTable :headers="operationHeaders" :items="state.other_logs" :items-per-page="20" class="data-table"><template #item.duration="{ item }">{{ formatDuration(item) }}</template><template #no-data><div class="empty">暂无预览或回滚日志</div></template></VDataTable></div>
            <div v-else class="dialog-body"><VDataTable :headers="[{ title: '媒体', key: 'name' }, { title: '完成时间', key: 'finished_at', width: 200 }, { title: '动作号', key: 'action_id', width: 260 }, { title: '操作', key: 'actions', sortable: false, width: 100 }]" :items="state.actions" :items-per-page="20" class="data-table"><template #item.finished_at="{ item }">{{ item.finished_at || '旧记录' }}</template><template #item.actions="{ item }"><VBtn size="small" class="table-undo" @click="run('undo', { action_id: item.action_id })">回滚</VBtn></template><template #no-data><div class="empty">暂无可回滚记录</div></template></VDataTable></div>
          </div>
        </template>
      </VCard>
    </VDialog>

    <VDialog v-model="overrideOpen" max-width="620">
      <VCard class="dialog-card">
        <VCardTitle class="dialog-title"><span>集数与正确季度映射</span><VBtn icon="mdi-close" variant="text" @click="overrideOpen = false" /></VCardTitle>
        <VDivider />
        <VCardText class="dialog-body">
          <VAlert type="warning" variant="tonal" class="mb-4">优先填写“正确 TMDB ID + 正确季度”。例如残缺的 291141/S01 对应完整系列 19389/S03；插件会读取正确季度的集数。没有正确条目时，才在人工集数中填写“38”或“20,20,18”。</VAlert>
          <VTextField v-model="overrideForm.title" label="媒体" readonly class="mb-3" />
          <div class="mapping-grid mb-3">
            <VTextField v-model="overrideForm.target_tmdb_id" type="number" label="正确系列 TMDB ID" placeholder="例如：19389" />
            <VTextField v-model="overrideForm.target_season" type="number" label="正确季度" placeholder="例如：3" />
          </div>
          <VTextField v-model="overrideForm.target_title" label="正确系列名称（可选）" placeholder="例如：我和僵尸有个约会" class="mb-3" />
          <VTextField v-model="overrideForm.counts" label="人工集数（映射留空时使用）" placeholder="例如：38 或 20,20,18" class="mb-3" />
          <VTextField v-model="overrideForm.source" label="核对来源" placeholder="例如：百度百科 / 官方资料" class="mb-3" />
          <VTextarea v-model="overrideForm.note" label="备注（可选）" rows="2" />
        </VCardText>
        <VCardActions class="px-4 pb-4">
          <VBtn color="primary" variant="flat" @click="saveOverride(false)">保存规则</VBtn>
          <VBtn v-if="(state.season_overrides || []).some(row => Number(row.tmdb_id) === Number(overrideForm.tmdb_id))" color="error" variant="tonal" @click="saveOverride(true)">删除规则</VBtn>
          <VSpacer /><VBtn variant="text" @click="overrideOpen = false">取消</VBtn>
        </VCardActions>
      </VCard>
    </VDialog>

    <VDialog v-model="rulesOpen" max-width="760" scrollable>
      <VCard class="dialog-card">
        <VCardTitle class="dialog-title"><span>集数与映射规则</span><VBtn icon="mdi-close" variant="text" @click="rulesOpen = false" /></VCardTitle>
        <VDivider />
        <VCardText class="dialog-body">
          <VAlert v-if="!state.season_overrides?.length" type="info" variant="tonal">尚未设置人工规则。</VAlert>
          <VList v-else bg-color="transparent">
            <VListItem v-for="item in state.season_overrides" :key="item.tmdb_id" :title="`${item.title || '未命名'} · TMDB ${item.tmdb_id}`" :subtitle="item.target_tmdb_id ? `映射：TMDB ${item.target_tmdb_id} S${String(item.target_season).padStart(2, '0')}（${item.counts?.[0] || '?'} 集）｜来源：${item.source || '人工核对'}｜更新：${item.updated_at}` : `人工季度：${item.counts.join(', ')}｜来源：${item.source || '人工核对'}｜更新：${item.updated_at}`">
              <template #append><VBtn color="error" variant="tonal" size="small" @click="removeOverride(item)">删除</VBtn></template>
            </VListItem>
          </VList>
        </VCardText>
      </VCard>
    </VDialog>
  </div>
</template>

<style scoped>
.season-page { padding: 6px 2px 28px; }
.headline { min-height: 52px; }
.actions { display: flex; flex-wrap: wrap; gap: 10px; }
.dashboard-grid { display: grid; grid-template-columns: repeat(4, minmax(170px, 1fr)); gap: 10px; max-width: 900px; }
.dash-card { position: relative; min-height: 128px; cursor: pointer; border-radius: 12px; box-shadow: none; transition: filter .16s, transform .16s; }
.card-scan { background: #132b3b; color: #29b6f6; }
.card-active { background: #251d3d; color: #9b6cff; }
.card-result { background: #172d1c; color: #62d123; }
.card-log { background: #352c17; color: #ffb300; }
.dash-card:hover { filter: brightness(1.14); transform: translateY(-1px); }
.card-label { color: currentColor; font-size: .83rem; font-weight: 600; margin-bottom: 8px; }
.card-value { color: rgba(255,255,255,.9); font-size: 1.65rem; line-height: 1; font-weight: 750; }
.card-note { margin-top: 14px; color: currentColor; font-size: .78rem; line-height: 1.35; }
.card-arrow { position: absolute; right: 14px; top: 50%; transform: translateY(-50%); color: currentColor; }
.action-primary, .action-info, .action-warning, .action-log { border-radius: 6px; box-shadow: none; }
.action-primary { background: #40206d; color: #b985ff; }
.action-info { background: #102d3d; color: #28b9ef; }
.action-warning { background: #372b12; color: #ffb300; }
.action-log { background: #211936; color: #a56df5; }
.dialog-card { max-height: 88vh; background: #12131c; border: 1px solid rgba(255,255,255,.08); }
.dialog-title { display: flex; align-items: center; justify-content: space-between; padding: 14px 18px; }
.dialog-body { padding: 16px; max-height: 72vh; overflow-y: auto; }
.record-tabs { padding: 0 12px; background: #12131c; }
.record-window { min-height: 260px; }
.data-table { background: transparent; }
.data-table :deep(thead th) { color: rgba(255,255,255,.82); font-size: .8rem; border-bottom-color: rgba(255,255,255,.12) !important; }
.data-table :deep(tbody td) { color: rgba(255,255,255,.68); border-bottom-color: rgba(255,255,255,.09) !important; }
.data-table :deep(tbody tr:hover) { background: rgba(255,255,255,.035); }
.table-actions { display: flex; gap: 6px; }
.table-preview { background: #211936; color: #a56df5; }
.table-fix { background: #17311c; color: #69d62c; }
.table-undo { background: #351b20; color: #ff5c67; }
.table-override { background: #3b2d12; color: #ffc107; }
.manual-actions { display: flex; align-items: center; gap: 8px; }
.mapping-grid { display: grid; grid-template-columns: 2fr 1fr; gap: 12px; }
.status-safe { color: #69d62c; }
.status-manual { color: #ffb300; }
.reason-text { display: inline-block; max-width: 160px; overflow: hidden; white-space: nowrap; text-overflow: ellipsis; color: #ffb300; }
.empty { padding: 40px 12px; text-align: center; color: rgb(var(--v-theme-on-surface-variant)); }
@media (max-width: 900px) { .dashboard-grid { grid-template-columns: repeat(2, minmax(170px, 1fr)); } }
@media (max-width: 560px) { .dashboard-grid, .mapping-grid { grid-template-columns: 1fr; } .dash-card { min-height: 112px; } }
</style>
