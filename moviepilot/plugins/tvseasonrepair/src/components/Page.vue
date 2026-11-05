<script setup>
import { computed, onMounted, onUnmounted, ref } from 'vue'

const props = defineProps({ api: { type: Object, default: () => ({}) } })
const loading = ref(false)
const message = ref('')
const error = ref('')
const dialog = ref('')
const recordTab = ref('scan')
const state = ref({
  headline: '正在读取状态…', summary: {}, scan_results: [], active_jobs: [],
  success_jobs: [], failed_jobs: [], scan_logs: [], other_logs: [], actions: [],
})
let timer

const summary = computed(() => state.value.summary || {})
const dialogOpen = computed({
  get: () => Boolean(dialog.value),
  set: value => { if (!value) dialog.value = '' },
})
const unwrap = response => response?.data?.data ?? response?.data ?? response
const formatDuration = row => row?.duration_seconds === undefined ? '—' : `${row.duration_seconds} 秒`

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
    <VAlert type="info" variant="tonal" class="mb-4 headline">{{ state.headline }}</VAlert>

    <div class="actions mb-4">
      <VBtn variant="flat" color="primary" prepend-icon="mdi-magnify" @click="run('scan')">扫描媒体库</VBtn>
      <VBtn variant="outlined" prepend-icon="mdi-eye-outline" @click="run('batch', { execute: false })">预览安全项目</VBtn>
      <VBtn variant="outlined" prepend-icon="mdi-tools" @click="run('batch', { execute: true })">批量修复</VBtn>
    </div>

    <div class="dashboard-grid">
      <VCard class="dash-card card-scan" variant="outlined" @click="openDialog('scan')">
        <VCardText>
          <div class="card-label">扫描候选</div>
          <div class="card-value">{{ summary.candidate_count || 0 }}</div>
          <div class="card-note">可安全修复 {{ summary.safe_count || 0 }} 部</div>
          <VIcon class="card-arrow" icon="mdi-chevron-right" />
        </VCardText>
      </VCard>
      <VCard class="dash-card card-active" variant="outlined" @click="openDialog('active')">
        <VCardText>
          <div class="card-label">处理中</div>
          <div class="card-value">{{ summary.active_count || 0 }}</div>
          <div class="card-note">查看队列与实时状态</div>
          <VIcon class="card-arrow" icon="mdi-chevron-right" />
        </VCardText>
      </VCard>
      <VCard class="dash-card card-result" variant="outlined" @click="openDialog('records', 'success')">
        <VCardText>
          <div class="card-label">修复结果</div>
          <div class="card-value">{{ summary.success_count || 0 }}</div>
          <div class="card-note">失败 {{ summary.failed_count || 0 }} 条</div>
          <VIcon class="card-arrow" icon="mdi-chevron-right" />
        </VCardText>
      </VCard>
      <VCard class="dash-card card-log" variant="outlined" @click="openDialog('records', 'scan')">
        <VCardText>
          <div class="card-label">任务记录</div>
          <div class="card-value">{{ summary.log_count || 0 }}</div>
          <div class="card-note">可回滚 {{ summary.rollback_count || 0 }} 条</div>
          <VIcon class="card-arrow" icon="mdi-chevron-right" />
        </VCardText>
      </VCard>
    </div>

    <VDialog v-model="dialogOpen" max-width="1080" scrollable>
      <VCard class="dialog-card">
        <VCardTitle class="dialog-title">
          <span>{{ dialog === 'scan' ? '扫描结果' : dialog === 'active' ? '处理任务' : '任务记录' }}</span>
          <VBtn icon="mdi-close" variant="text" @click="dialog = ''" />
        </VCardTitle>
        <VDivider />

        <VCardText v-if="dialog === 'scan'" class="dialog-body">
          <div v-if="!state.scan_results.length" class="empty">暂无候选项目</div>
          <VCard v-for="item in state.scan_results" :key="item.series_rel" variant="outlined" class="list-card">
            <VCardText>
              <div class="item-title">{{ item.name }}</div>
              <div class="item-meta">当前：{{ item.current_summary }}</div>
              <div class="item-meta">TMDB：{{ item.official_summary }}</div>
              <div class="item-result">{{ item.safe ? '可安全修复' : `需人工核对：${item.reason}` }}</div>
              <div v-if="item.safe" class="item-actions">
                <VBtn size="small" variant="outlined" @click="run('apply', { series_rel: item.series_rel, execute: false })">预览</VBtn>
                <VBtn size="small" variant="flat" color="primary" @click="run('apply', { series_rel: item.series_rel, execute: true })">确认修复</VBtn>
              </div>
            </VCardText>
          </VCard>
        </VCardText>

        <VCardText v-else-if="dialog === 'active'" class="dialog-body">
          <div v-if="!state.active_jobs.length" class="empty">当前没有处理中的任务</div>
          <VCard v-for="job in state.active_jobs" :key="job.id" variant="outlined" class="list-card">
            <VCardText>
              <div class="item-title">{{ job.name }}</div>
              <div class="item-meta">开始：{{ job.started_at || job.created_at || '—' }}</div>
              <div class="item-result">{{ job.message }}</div>
            </VCardText>
          </VCard>
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
          <VWindow v-model="recordTab" class="record-window">
            <VWindowItem value="scan"><div class="dialog-body">
              <div v-if="!state.scan_logs.length" class="empty">暂无扫描日志</div>
              <VCard v-for="row in state.scan_logs" :key="row.id" variant="outlined" class="list-card"><VCardText>
                <div class="item-title">{{ row.title }} · {{ row.status === 'success' ? '成功' : '失败' }}</div>
                <div class="item-meta">开始 {{ row.started_at }}　结束 {{ row.finished_at || '—' }}　耗时 {{ formatDuration(row) }}</div>
                <div class="item-result">{{ row.detail }}</div>
              </VCardText></VCard>
            </div></VWindowItem>
            <VWindowItem value="success"><div class="dialog-body">
              <div v-if="!state.success_jobs.length" class="empty">暂无成功记录</div>
              <VCard v-for="row in state.success_jobs" :key="row.id" variant="outlined" class="list-card"><VCardText>
                <div class="item-title">{{ row.name }}</div>
                <div class="item-meta">开始 {{ row.started_at || row.created_at }}　结束 {{ row.finished_at || row.updated_at }}　耗时 {{ formatDuration(row) }}</div>
                <div class="item-result">{{ row.message }}</div>
              </VCardText></VCard>
            </div></VWindowItem>
            <VWindowItem value="failed"><div class="dialog-body">
              <div v-if="!state.failed_jobs.length" class="empty">暂无失败记录</div>
              <VCard v-for="row in state.failed_jobs" :key="row.id" variant="outlined" class="list-card"><VCardText>
                <div class="item-title">{{ row.name }}</div>
                <div class="item-meta">开始 {{ row.started_at || row.created_at }}　结束 {{ row.finished_at || row.updated_at }}　耗时 {{ formatDuration(row) }}</div>
                <div class="item-result">{{ row.message }}</div>
              </VCardText></VCard>
            </div></VWindowItem>
            <VWindowItem value="operation"><div class="dialog-body">
              <div v-if="!state.other_logs.length" class="empty">暂无预览或回滚日志</div>
              <VCard v-for="row in state.other_logs" :key="row.id" variant="outlined" class="list-card"><VCardText>
                <div class="item-title">{{ row.title }} · {{ row.status }}</div>
                <div class="item-meta">开始 {{ row.started_at }}　结束 {{ row.finished_at || '—' }}　耗时 {{ formatDuration(row) }}</div>
                <div class="item-result">{{ row.detail }}</div>
              </VCardText></VCard>
            </div></VWindowItem>
            <VWindowItem value="rollback"><div class="dialog-body">
              <div v-if="!state.actions.length" class="empty">暂无可回滚记录</div>
              <VCard v-for="row in state.actions" :key="row.action_id" variant="outlined" class="list-card"><VCardText class="rollback-row">
                <div><div class="item-title">{{ row.name }}</div><div class="item-meta">{{ row.finished_at || '旧记录未保存完成时间' }} · {{ row.action_id }}</div></div>
                <VBtn size="small" variant="outlined" @click="run('undo', { action_id: row.action_id })">回滚</VBtn>
              </VCardText></VCard>
            </div></VWindowItem>
          </VWindow>
        </template>
      </VCard>
    </VDialog>
  </div>
</template>

<style scoped>
.season-page { padding: 4px 2px 24px; }
.headline { min-height: 52px; }
.actions { display: flex; flex-wrap: wrap; gap: 10px; }
.dashboard-grid { display: grid; grid-template-columns: repeat(4, minmax(0, 1fr)); gap: 12px; }
.dash-card { position: relative; min-height: 134px; cursor: pointer; overflow: hidden; border-width: 1px; border-color: rgba(255,255,255,.10); box-shadow: 0 8px 24px rgba(0,0,0,.16); transition: border-color .18s, transform .18s, box-shadow .18s; }
.dash-card::before { content: ''; position: absolute; inset: 0 auto 0 0; width: 4px; background: var(--card-accent); }
.card-scan { --card-accent: #4da3ff; background: linear-gradient(135deg, rgba(35,73,108,.72), rgba(24,31,42,.94)); }
.card-active { --card-accent: #9a7cff; background: linear-gradient(135deg, rgba(65,50,103,.66), rgba(27,27,40,.94)); }
.card-result { --card-accent: #52c79a; background: linear-gradient(135deg, rgba(38,83,68,.66), rgba(23,35,34,.94)); }
.card-log { --card-accent: #e6a84d; background: linear-gradient(135deg, rgba(91,67,35,.66), rgba(36,31,25,.94)); }
.dash-card:hover { border-color: rgba(var(--v-theme-primary), .65); transform: translateY(-2px); }
.card-label { color: rgba(255,255,255,.78); font-size: .9rem; margin-bottom: 12px; }
.card-value { color: #fff; font-size: 1.8rem; line-height: 1; font-weight: 700; }
.card-note { margin-top: 12px; color: rgba(255,255,255,.62); font-size: .82rem; }
.card-arrow { position: absolute; right: 16px; top: 50%; transform: translateY(-50%); opacity: .55; }
.dialog-card { max-height: 84vh; background: rgb(var(--v-theme-surface)); border: 1px solid rgba(255,255,255,.10); }
.dialog-title { display: flex; align-items: center; justify-content: space-between; padding: 14px 18px; }
.dialog-body { padding: 18px; max-height: 66vh; overflow-y: auto; }
.record-tabs { padding: 0 10px; }
.record-window { min-height: 260px; }
.list-card { margin-bottom: 10px; background: rgba(var(--v-theme-surface-variant), .34); border-color: rgba(255,255,255,.10); box-shadow: 0 5px 16px rgba(0,0,0,.12); }
.item-title { font-weight: 650; margin-bottom: 7px; }
.item-meta { color: rgb(var(--v-theme-on-surface-variant)); font-size: .82rem; line-height: 1.6; }
.item-result { margin-top: 8px; white-space: pre-wrap; line-height: 1.55; }
.item-actions { display: flex; gap: 8px; margin-top: 12px; }
.rollback-row { display: flex; align-items: center; justify-content: space-between; gap: 16px; }
.empty { padding: 40px 12px; text-align: center; color: rgb(var(--v-theme-on-surface-variant)); }
@media (max-width: 900px) { .dashboard-grid { grid-template-columns: repeat(2, minmax(0, 1fr)); } }
@media (max-width: 560px) { .dashboard-grid { grid-template-columns: 1fr; } .dash-card { min-height: 112px; } }
</style>
