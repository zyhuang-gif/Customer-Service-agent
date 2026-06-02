<script setup>
import { computed, onMounted, ref } from 'vue'
import { Refresh } from '@element-plus/icons-vue'
import { api } from '../api/client'
import { useAuthStore } from '../stores/auth'

const auth = useAuthStore()
const loading = ref(false)
const error = ref('')
const summary = ref(null)

const STATUS_LABEL = {
  ai_handling: 'AI处理中',
  awaiting_confirmation: '待确认',
  human_handling: '人工处理',
  resolved: '已解决',
  closed: '已关闭',
  needs_followup: '需回访',
}

function percent(value) {
  return `${((value || 0) * 100).toFixed(1)}%`
}

function countLabel(value) {
  return `${value || 0}`
}

const metrics = computed(() => {
  const data = summary.value || {}
  return [
    {
      label: 'AI独立解决率',
      value: percent(data.ai_resolution_rate),
      hint: 'resolved + closed / total',
      tone: 'blue',
    },
    {
      label: '转人工率',
      value: percent(data.handoff_rate),
      hint: 'handoff audit / total',
      tone: 'orange',
    },
    {
      label: '工单量',
      value: countLabel(data.conversation_total),
      hint: `待确认 ${data.pending_actions || 0}`,
      tone: 'green',
    },
    {
      label: '知识命中率',
      value: percent(data.knowledge_hit_rate),
      hint: 'search_knowledge hit rate',
      tone: 'purple',
    },
  ]
})

const statusRows = computed(() => {
  const counts = summary.value?.status_counts || {}
  const max = Math.max(...Object.values(counts), 1)
  return Object.entries(counts).map(([status, count]) => ({
    status,
    label: STATUS_LABEL[status] || status,
    count,
    width: `${Math.max((count / max) * 100, 4)}%`,
  }))
})

async function loadSummary() {
  loading.value = true
  error.value = ''
  try {
    summary.value = await api('/dashboard/summary', { token: auth.token })
  } catch (e) {
    error.value = e.message || '看板数据加载失败'
  } finally {
    loading.value = false
  }
}

onMounted(loadSummary)
</script>

<template>
  <div class="dashboard-page">
    <header class="dashboard-header">
      <div>
        <h1>运营看板</h1>
        <p>AI 处理效果、人工介入和知识库缺口</p>
      </div>
      <el-button :icon="Refresh" :loading="loading" @click="loadSummary">刷新</el-button>
    </header>

    <el-alert v-if="error" :title="error" type="error" show-icon class="dashboard-alert" />

    <section class="metric-grid">
      <el-card v-for="item in metrics" :key="item.label" class="metric-card" shadow="never">
        <div class="metric-label">{{ item.label }}</div>
        <div class="metric-value" :class="`tone-${item.tone}`">{{ item.value }}</div>
        <div class="metric-hint">{{ item.hint }}</div>
      </el-card>
    </section>

    <section class="dashboard-main">
      <div class="panel">
        <div class="panel-header">
          <h2>会话状态分布</h2>
          <span>{{ summary?.conversation_total || 0 }} 个会话</span>
        </div>
        <div v-if="statusRows.length" class="status-chart">
          <div v-for="row in statusRows" :key="row.status" class="status-row">
            <div class="status-meta">
              <span>{{ row.label }}</span>
              <strong>{{ row.count }}</strong>
            </div>
            <div class="bar-track">
              <div class="bar-fill" :style="{ width: row.width }" />
            </div>
          </div>
        </div>
        <el-empty v-else description="暂无会话数据" />
      </div>

      <div class="panel">
        <div class="panel-header">
          <h2>无答案问题</h2>
          <span>知识缺口</span>
        </div>
        <div v-if="summary?.knowledge_gaps?.length" class="gap-list">
          <div v-for="gap in summary.knowledge_gaps" :key="gap.query" class="gap-row">
            <span class="gap-query">{{ gap.query }}</span>
            <el-tag type="warning" size="small">{{ gap.count }}次</el-tag>
          </div>
        </div>
        <div v-else class="empty-state">暂无无答案问题</div>
      </div>
    </section>
  </div>
</template>

<style scoped>
.dashboard-page {
  min-height: 100vh;
  padding: 24px;
  background: #f5f7fa;
  color: #303133;
}

.dashboard-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 18px;
}

.dashboard-header h1 {
  margin: 0;
  font-size: 24px;
  font-weight: 700;
}

.dashboard-header p {
  margin: 6px 0 0;
  color: #606266;
  font-size: 14px;
}

.dashboard-alert {
  margin-bottom: 16px;
}

.metric-grid {
  display: grid;
  grid-template-columns: repeat(4, minmax(0, 1fr));
  gap: 12px;
  margin-bottom: 16px;
}

.metric-card {
  border-radius: 8px;
}

.metric-label {
  color: #606266;
  font-size: 13px;
}

.metric-value {
  margin-top: 10px;
  font-size: 28px;
  line-height: 1;
  font-weight: 700;
}

.metric-hint {
  margin-top: 10px;
  color: #909399;
  font-size: 12px;
}

.tone-blue { color: #1f6feb; }
.tone-orange { color: #c56a00; }
.tone-green { color: #138a42; }
.tone-purple { color: #7b4dd8; }

.dashboard-main {
  display: grid;
  grid-template-columns: minmax(0, 1.2fr) minmax(320px, 0.8fr);
  gap: 16px;
}

.panel {
  min-height: 360px;
  padding: 18px;
  border: 1px solid #ebeef5;
  border-radius: 8px;
  background: #fff;
}

.panel-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 16px;
}

.panel-header h2 {
  margin: 0;
  font-size: 16px;
}

.panel-header span {
  color: #909399;
  font-size: 13px;
}

.status-chart {
  display: flex;
  flex-direction: column;
  gap: 14px;
}

.status-meta {
  display: flex;
  justify-content: space-between;
  margin-bottom: 6px;
  color: #606266;
  font-size: 13px;
}

.status-meta strong {
  color: #303133;
}

.bar-track {
  height: 10px;
  overflow: hidden;
  border-radius: 999px;
  background: #edf0f5;
}

.bar-fill {
  height: 100%;
  border-radius: inherit;
  background: #1f6feb;
}

.gap-list {
  display: flex;
  flex-direction: column;
  gap: 10px;
}

.gap-row {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  padding: 10px 0;
  border-bottom: 1px solid #ebeef5;
}

.gap-query {
  overflow-wrap: anywhere;
  line-height: 1.45;
}

.empty-state {
  padding: 56px 0;
  color: #909399;
  text-align: center;
}

@media (max-width: 900px) {
  .dashboard-page {
    padding: 16px;
  }

  .dashboard-header {
    align-items: flex-start;
    gap: 12px;
  }

  .metric-grid,
  .dashboard-main {
    grid-template-columns: 1fr;
  }
}
</style>
