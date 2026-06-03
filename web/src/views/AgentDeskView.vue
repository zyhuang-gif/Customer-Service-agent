<script setup>
import { computed, ref, onMounted, onUnmounted } from 'vue'
import { ElMessage } from 'element-plus'
import { api } from '../api/client'
import { useAuthStore } from '../stores/auth'
import ConversationList from '../components/ConversationList.vue'
import MessageBubble from '../components/MessageBubble.vue'
import PendingActionCard from '../components/PendingActionCard.vue'

const auth = useAuthStore()
const conversations = ref([])
const activeId = ref('')
const messages = ref([])
const pendingActions = ref([])
const agentReply = ref('')
const replying = ref(false)
const orderLookupId = ref('')
const orderDetail = ref(null)
const orderLookupLoading = ref(false)
let refreshTimer = 0
const quickReplies = [
  '您好，我是人工客服，已经接手继续处理。',
  '我先为您核实订单/物流/退款信息，请稍等。',
  '理解您的着急，我会优先帮您跟进。',
  '这个问题需要进一步确认，我会给您明确下一步。',
]
const fieldLabels = {
  id: 'ID',
  customer_id: '客户ID',
  order_id: '订单号',
  status: '状态',
  items: '商品',
  amount: '金额',
  total_amount: '金额',
  address: '地址',
  created_at: '创建时间',
  shipped_at: '发货时间',
  name: '姓名',
  phone: '电话',
  member_level: '等级',
  level: '等级',
  register_date: '注册时间',
  carrier: '承运商',
  tracking_no: '运单号',
  last_update: '更新时间',
  eta: '预计送达',
  traces: '物流轨迹',
  refund: '退款详情',
  channel: '渠道',
  reason: '原因',
  applied_at: '申请时间',
  completed_at: '完成时间',
  category: '类型',
  priority: '优先级',
  assignee: '处理人',
  summary: '摘要',
  history: '处理记录',
  updated_at: '更新时间',
}

const activeConversation = computed(() => conversations.value.find((c) => c.id === activeId.value))
const canAgentReply = computed(() => activeConversation.value?.status === 'human_handling')
const handoffSummaryLines = computed(() => (
  activeConversation.value?.summary ? activeConversation.value.summary.split('\n').filter(Boolean) : []
))

async function loadConversations() {
  conversations.value = await api('/conversations', { token: auth.token })
}

async function loadPending() {
  pendingActions.value = await api('/pending-actions', { token: auth.token })
}

async function refreshDesk() {
  await Promise.all([loadConversations(), loadPending()])
  if (activeId.value) {
    messages.value = await api(`/conversations/${activeId.value}/messages`, { token: auth.token })
  }
}

async function selectConversation(id) {
  activeId.value = id
  agentReply.value = ''
  messages.value = await api(`/conversations/${id}/messages`, { token: auth.token })
}

async function sendAgentReply() {
  const content = agentReply.value.trim()
  if (!activeId.value || !content || !canAgentReply.value || replying.value) return
  replying.value = true
  try {
    const msg = await api(`/conversations/${activeId.value}/messages`, {
      method: 'POST',
      body: { content },
      token: auth.token,
    })
    messages.value.push(msg)
    agentReply.value = ''
    await loadConversations()
  } catch (e) {
    ElMessage.error(e.message || '发送失败')
  } finally {
    replying.value = false
  }
}

function useQuickReply(text) {
  if (!canAgentReply.value) return
  agentReply.value = text
}

function formatValue(value) {
  if (value === null || value === undefined || value === '') return '-'
  if (typeof value === 'object') return JSON.stringify(value)
  return String(value)
}

function firstValue(...values) {
  return values.find((value) => value !== null && value !== undefined && value !== '')
}

function detailEntries(record, exclude = []) {
  if (!record) return []
  const excluded = new Set(exclude)
  return Object.entries(record)
    .filter(([key]) => !excluded.has(key))
    .map(([key, value]) => ({ key, label: fieldLabels[key] || key, value }))
}

async function lookupOrder() {
  const id = orderLookupId.value.trim()
  if (!id || orderLookupLoading.value) return
  orderLookupLoading.value = true
  orderDetail.value = null
  try {
    orderDetail.value = await api(`/agent-desk/orders/${encodeURIComponent(id)}`, { token: auth.token })
  } catch (e) {
    ElMessage.error(e.message || '订单查询失败')
  } finally {
    orderLookupLoading.value = false
  }
}

async function onReview({ id, approved }) {
  try {
    await api(`/pending-actions/${id}/review`, {
      method: 'POST', body: { approved }, token: auth.token,
    })
    ElMessage.success(approved ? '已确认执行' : '已驳回')
    await loadPending()
    if (activeId.value) await selectConversation(activeId.value)
  } catch (e) {
    ElMessage.error(e.message || '操作失败')
  }
}

onMounted(() => {
  refreshDesk()
  refreshTimer = window.setInterval(refreshDesk, 3000)
})

onUnmounted(() => {
  if (refreshTimer) window.clearInterval(refreshTimer)
})
</script>

<template>
  <div class="desk">
    <div class="col col-left">
      <div class="col-title">会话列表</div>
      <ConversationList :conversations="conversations" :active-id="activeId" @select="selectConversation" />
    </div>
    <div class="col col-mid">
      <div class="col-title">对话内容</div>
      <div class="msg-area">
        <MessageBubble v-for="m in messages" :key="m.id" :role="m.role" :content="m.content"
                       :citations="(m.meta && m.meta.citations) || []" />
        <div v-if="!messages.length" class="empty">选择左侧会话查看对话</div>
      </div>
      <div class="agent-reply">
        <el-input
          v-model="agentReply"
          type="textarea"
          :rows="2"
          placeholder="输入人工回复"
          :disabled="!canAgentReply"
          @keydown.enter.prevent="sendAgentReply"
        />
        <el-button type="primary" :loading="replying" :disabled="!canAgentReply || !agentReply.trim()" @click="sendAgentReply">
          发送
        </el-button>
      </div>
    </div>
    <div class="col col-right">
      <div v-if="handoffSummaryLines.length" class="handoff-panel">
        <div class="panel-title">接管信息</div>
        <div v-for="line in handoffSummaryLines" :key="line" class="summary-line">{{ line }}</div>
      </div>
      <div v-if="canAgentReply" class="quick-replies">
        <div class="panel-title">常用语</div>
        <button v-for="text in quickReplies" :key="text" type="button" class="quick-reply" @click="useQuickReply(text)">
          {{ text }}
        </button>
      </div>
      <div class="order-lookup">
        <div class="panel-title">订单查询</div>
        <div class="order-search">
          <el-input
            v-model="orderLookupId"
            placeholder="输入订单号"
            clearable
            @keydown.enter.prevent="lookupOrder"
          />
          <el-button type="primary" :loading="orderLookupLoading" :disabled="!orderLookupId.trim()" @click="lookupOrder">
            查询
          </el-button>
        </div>
        <div v-if="orderDetail" class="order-detail">
          <div class="detail-section">
            <div class="detail-title">订单</div>
            <div v-for="entry in detailEntries(orderDetail.order, ['items'])" :key="entry.key" class="kv">
              <span>{{ entry.label }}</span><strong>{{ formatValue(entry.value) }}</strong>
            </div>
          </div>
          <div class="detail-section" v-if="orderDetail.order.items?.length">
            <div class="detail-title">商品</div>
            <div v-for="item in orderDetail.order.items" :key="item.sku || item.name" class="list-row">
              <span>{{ formatValue(item.name || item.sku) }}</span>
              <strong>x{{ formatValue(firstValue(item.qty, item.quantity)) }}</strong>
            </div>
          </div>
          <div class="detail-section" v-if="orderDetail.customer">
            <div class="detail-title">客户</div>
            <div v-for="entry in detailEntries(orderDetail.customer)" :key="entry.key" class="kv">
              <span>{{ entry.label }}</span><strong>{{ formatValue(entry.value) }}</strong>
            </div>
          </div>
          <div class="detail-section" v-if="orderDetail.logistics">
            <div class="detail-title">物流</div>
            <div v-for="entry in detailEntries(orderDetail.logistics)" :key="entry.key" class="kv">
              <span>{{ entry.label }}</span><strong>{{ formatValue(entry.value) }}</strong>
            </div>
          </div>
          <div class="detail-section" v-if="orderDetail.refund">
            <div class="detail-title">退款</div>
            <div v-for="entry in detailEntries(orderDetail.refund)" :key="entry.key" class="kv">
              <span>{{ entry.label }}</span><strong>{{ formatValue(entry.value) }}</strong>
            </div>
          </div>
          <div class="detail-section">
            <div class="detail-title">关联工单</div>
            <div v-if="!orderDetail.tickets?.length" class="muted">暂无关联工单</div>
            <div v-for="ticket in orderDetail.tickets" :key="ticket.id" class="ticket-row">
              <div v-for="entry in detailEntries(ticket)" :key="entry.key" class="kv">
                <span>{{ entry.label }}</span><strong>{{ formatValue(entry.value) }}</strong>
              </div>
            </div>
          </div>
        </div>
      </div>
      <div class="col-title">
        待确认动作
        <el-badge :value="pendingActions.length" :hidden="!pendingActions.length" />
      </div>
      <div class="pending-area">
        <PendingActionCard v-for="a in pendingActions" :key="a.id" :action="a" @review="onReview" />
        <div v-if="!pendingActions.length" class="empty">暂无待确认动作</div>
      </div>
    </div>
  </div>
</template>

<style scoped>
.desk { display: flex; height: 100vh; }
.col { display: flex; flex-direction: column; border-right: 1px solid #ebeef5; }
.col-left { width: 280px; }
.col-mid { flex: 1; }
.col-right { width: 360px; border-right: none; }
.col-title { padding: 12px 16px; font-weight: 600; border-bottom: 1px solid #ebeef5; }
.msg-area, .pending-area { flex: 1; overflow-y: auto; padding: 16px; }
.agent-reply { display: flex; gap: 8px; padding: 12px 16px; border-top: 1px solid #ebeef5; }
.agent-reply .el-button { width: 72px; }
.handoff-panel { padding: 12px 16px; border-bottom: 1px solid #ebeef5; background: #f5f7fa; }
.panel-title { font-weight: 600; margin-bottom: 8px; }
.summary-line { font-size: 13px; color: #606266; line-height: 1.5; margin-top: 4px; white-space: pre-wrap; }
.quick-replies { padding: 12px 16px; border-bottom: 1px solid #ebeef5; }
.quick-reply { display: block; width: 100%; text-align: left; border: 1px solid #dcdfe6; background: #fff; color: #303133; border-radius: 6px; padding: 8px 10px; margin-top: 8px; cursor: pointer; line-height: 1.4; }
.quick-reply:hover { border-color: #409eff; color: #409eff; background: #ecf5ff; }
.order-lookup { padding: 12px 16px; border-bottom: 1px solid #ebeef5; }
.order-search { display: flex; gap: 8px; }
.order-search .el-button { width: 64px; }
.order-detail { margin-top: 12px; max-height: 360px; overflow-y: auto; border: 1px solid #ebeef5; border-radius: 6px; background: #fff; }
.detail-section { padding: 10px 12px; border-bottom: 1px solid #f2f3f5; }
.detail-section:last-child { border-bottom: none; }
.detail-title { font-size: 13px; font-weight: 600; color: #303133; margin-bottom: 6px; }
.kv, .list-row, .ticket-row { display: flex; justify-content: space-between; gap: 12px; font-size: 12px; line-height: 1.6; }
.kv span, .ticket-row span { color: #909399; white-space: nowrap; }
.kv strong, .list-row strong, .ticket-row strong { color: #303133; font-weight: 500; text-align: right; overflow-wrap: anywhere; }
.list-row span { color: #606266; overflow-wrap: anywhere; }
.ticket-row { padding: 6px 0; border-top: 1px solid #f2f3f5; }
.ticket-row:first-of-type { border-top: none; }
.muted { color: #909399; font-size: 12px; }
.empty { color: #909399; text-align: center; margin-top: 40px; }
</style>
