<script setup>
import { computed, onMounted, onUnmounted, ref, watch } from 'vue'
import { chatStream } from '../api/sse'
import { api } from '../api/client'
import MessageBubble from '../components/MessageBubble.vue'

const customerRef = ref(localStorage.getItem('chat_customer_ref') || '13800000001')
const conversationId = ref(localStorage.getItem('chat_conversation_id') || '')
const input = ref('')
const messages = ref(loadCachedMessages())
const sending = ref(false)
let syncTimer = 0
let typeTimer = 0

const quickIntents = [
  { key: 'order', label: '查订单', text: '我想查询订单状态' },
  { key: 'logistics', label: '查物流', text: '我想查询物流进度' },
  { key: 'refund', label: '退款进度', text: '我想查询退款进度' },
  { key: 'return', label: '退货规则', text: '我想了解退货规则' },
  { key: 'handoff', label: '转人工', text: '我要转人工客服' },
]

const lastCustomerMessage = computed(() => {
  return [...messages.value].reverse().find((m) => m.role === 'customer') || null
})

const latestServiceMessage = computed(() => {
  return [...messages.value].reverse().find((m) => ['ai', 'system', 'agent'].includes(m.role)) || null
})

const sessionStatus = computed(() => {
  if (sending.value) return { label: 'AI处理中', tone: 'processing' }
  const content = latestServiceMessage.value?.content || ''
  if (content.includes('人工确认') || content.includes('转人工')) {
    return { label: '需要人工确认', tone: 'attention' }
  }
  if (messages.value.length) return { label: '服务中', tone: 'active' }
  return { label: '服务中', tone: 'idle' }
})

const activeIntent = computed(() => {
  const text = lastCustomerMessage.value?.content || ''
  if (/退款|退钱|到账/.test(text)) return '退款咨询'
  if (/物流|快递|运输|配送/.test(text)) return '物流查询'
  if (/订单|单号/.test(text)) return '订单查询'
  if (/退货|换货/.test(text)) return '退换货咨询'
  if (/投诉|人工|客服/.test(text)) return '人工协助'
  return messages.value.length ? '综合咨询' : '等待用户描述问题'
})

const orderNo = computed(() => {
  const text = lastCustomerMessage.value?.content || ''
  return text.match(/\b\d{8,}\b/)?.[0] || '待识别'
})

const latestTrace = computed(() => {
  return latestServiceMessage.value?.agent_trace || []
})

const contextItems = computed(() => [
  { label: '当前意图', value: activeIntent.value },
  { label: '订单编号', value: orderNo.value },
  { label: '处理状态', value: sessionStatus.value.label },
  { label: '知识依据', value: `${latestServiceMessage.value?.citations?.length || 0} 条` },
])

function loadCachedMessages() {
  try {
    const cached = JSON.parse(localStorage.getItem('chat_messages') || '[]')
    return Array.isArray(cached) ? cached : []
  } catch {
    return []
  }
}

function persistChat() {
  localStorage.setItem('chat_customer_ref', customerRef.value)
  localStorage.setItem('chat_conversation_id', conversationId.value)
  localStorage.setItem('chat_messages', JSON.stringify(messages.value))
}

async function loadServerMessages() {
  const token = localStorage.getItem('cs_token')
  if (!conversationId.value || !token || sending.value || typeTimer) return
  try {
    const rows = await api(`/conversations/${conversationId.value}/messages`, { token })
    messages.value = rows.map((m) => ({
      role: m.role,
      content: m.content,
      citations: (m.meta && m.meta.citations) || [],
      agent_trace: (m.meta && m.meta.agent_trace) || [],
    }))
    persistChat()
  } catch {
    // 客户页以本地缓存为主；后端拉取失败时保留当前可见历史。
  }
}

function clearTypeTimer() {
  if (!typeTimer) return
  window.clearInterval(typeTimer)
  typeTimer = 0
}

function playResponse(index, fullText, meta = {}) {
  clearTypeTimer()
  const text = fullText || ''
  let cursor = Math.min(2, text.length)
  const extra = {
    citations: meta.citations || [],
    agent_trace: meta.agent_trace || [],
  }
  messages.value[index] = { role: 'ai', content: text.slice(0, cursor), ...extra }
  persistChat()
  if (cursor >= text.length) return

  typeTimer = window.setInterval(() => {
    cursor = Math.min(cursor + 2, text.length)
    messages.value[index] = { role: 'ai', content: text.slice(0, cursor), ...extra }
    persistChat()
    if (cursor >= text.length) clearTypeTimer()
  }, 30)
}

async function send() {
  const text = input.value.trim()
  if (!text || sending.value) return
  messages.value.push({ role: 'customer', content: text })
  const pendingIndex = messages.value.length
  messages.value.push({ role: 'system', content: '正在处理，请稍候...' })
  persistChat()
  input.value = ''
  sending.value = true
  let aiIndex = pendingIndex
  try {
    await chatStream(
      { conversationId: conversationId.value, customerRef: customerRef.value, message: text },
      (ev) => {
        if (ev.type === 'start') {
          conversationId.value = ev.conversation_id
          persistChat()
        } else if (ev.type === 'response') {
          playResponse(aiIndex, ev.content, {
            citations: ev.citations || [],
            agent_trace: ev.agent_trace || [],
          })
        } else if (ev.type === 'awaiting_confirmation') {
          clearTypeTimer()
          messages.value[pendingIndex] = {
            role: 'system',
            content: ev.content || '该操作已提交人工确认，请稍候。',
            citations: ev.citations || [],
            agent_trace: ev.agent_trace || [],
          }
          persistChat()
        }
      },
    )
  } catch (e) {
    clearTypeTimer()
    messages.value.push({ role: 'system', content: '网络错误，请重试。' })
    persistChat()
  } finally {
    sending.value = false
  }
}

async function useQuickIntent(intent) {
  if (sending.value) return
  input.value = intent.text
  await send()
}

watch(customerRef, persistChat)

onMounted(() => {
  loadServerMessages()
  syncTimer = window.setInterval(loadServerMessages, 3000)
})

onUnmounted(() => {
  if (syncTimer) window.clearInterval(syncTimer)
  clearTypeTimer()
})
</script>

<template>
  <div class="chat-page">
    <div class="chat-header">
      <div>
        <div class="service-title">智能售后客服</div>
        <div class="service-subtitle">订单、物流、退款与人工协同</div>
      </div>
      <div class="header-actions">
        <span class="status-pill" :class="`status-${sessionStatus.tone}`">{{ sessionStatus.label }}</span>
        <el-input v-model="customerRef" size="small" class="customer-input" placeholder="手机号/标识" />
      </div>
    </div>

    <div class="chat-shell">
      <main class="chat-main">
        <div class="quick-intents" aria-label="常用客服入口">
          <button
            v-for="intent in quickIntents"
            :key="intent.key"
            class="quick-intent"
            :data-test="`quick-intent-${intent.key}`"
            type="button"
            :disabled="sending"
            @click="useQuickIntent(intent)"
          >
            {{ intent.label }}
          </button>
        </div>

        <div class="chat-body">
          <div v-if="!messages.length" class="empty">
            <div class="empty-title">您好，请问有什么可以帮您？</div>
            <div class="empty-copy">可以直接描述订单、物流、退款或售后问题。</div>
          </div>
          <MessageBubble
            v-for="(m, i) in messages"
            :key="i"
            :role="m.role"
            :content="m.content"
            :citations="m.citations || []"
            :agent-trace="m.agent_trace || []"
          />
        </div>

        <div class="chat-input">
          <el-input
            v-model="input"
            type="textarea"
            :rows="2"
            placeholder="输入您的问题"
            @keydown.enter.prevent="send"
          />
          <el-button type="primary" :loading="sending" @click="send">发送</el-button>
        </div>
      </main>

      <aside class="service-panel">
        <section class="panel-section">
          <div class="panel-title">服务上下文</div>
          <div class="context-list">
            <div v-for="item in contextItems" :key="item.label" class="context-item">
              <span>{{ item.label }}</span>
              <strong>{{ item.value }}</strong>
            </div>
          </div>
        </section>

        <section class="panel-section status-card">
          <div class="panel-title">当前进度</div>
          <div class="progress-line">
            <span class="progress-dot done"></span>
            <span>识别问题</span>
          </div>
          <div class="progress-line">
            <span class="progress-dot" :class="{ done: messages.length }"></span>
            <span>检索依据</span>
          </div>
          <div class="progress-line">
            <span class="progress-dot" :class="{ done: latestServiceMessage }"></span>
            <span>生成答复</span>
          </div>
        </section>

        <section class="panel-section" :class="{ muted: !latestTrace.length }">
          <div class="panel-title">AI 协同过程</div>
          <div v-if="latestTrace.length" class="side-trace">
            <div v-for="(step, i) in latestTrace" :key="i" class="side-trace-step">
              <span>{{ i + 1 }}</span>
              <div>
                <strong>{{ step.agent || 'Agent' }}</strong>
                <p>{{ step.summary || step.action || '完成处理步骤' }}</p>
              </div>
            </div>
          </div>
          <div v-else class="panel-empty">等待用户描述问题</div>
        </section>
      </aside>
    </div>
  </div>
</template>

<style scoped>
.chat-page { min-height: 100dvh; background: #f5f7fb; color: #25324b; }
.chat-header { display: flex; justify-content: space-between; align-items: center; gap: 16px; padding: 14px 24px; border-bottom: 1px solid #e4e9f2; background: #fff; }
.service-title { font-weight: 700; font-size: 17px; }
.service-subtitle { margin-top: 2px; color: #667085; font-size: 12px; }
.header-actions { display: flex; align-items: center; gap: 10px; }
.customer-input { width: 168px; }
.status-pill { display: inline-flex; align-items: center; min-height: 26px; border-radius: 999px; padding: 2px 10px; font-size: 12px; font-weight: 700; border: 1px solid transparent; }
.status-active, .status-idle { background: #e8f1ff; color: #1f6feb; border-color: #c9ddff; }
.status-processing { background: #fff7e6; color: #a15c00; border-color: #f7d99a; }
.status-attention { background: #fff1f0; color: #b42318; border-color: #f3b8b2; }
.chat-shell { display: grid; grid-template-columns: minmax(0, 1fr) 320px; gap: 16px; max-width: 1180px; height: calc(100dvh - 62px); margin: 0 auto; padding: 16px; }
.chat-main, .service-panel { min-height: 0; }
.chat-main { display: grid; grid-template-rows: auto minmax(0, 1fr) auto; border: 1px solid #e4e9f2; border-radius: 8px; background: #fff; overflow: hidden; }
.quick-intents { display: flex; gap: 8px; overflow-x: auto; padding: 12px 14px; border-bottom: 1px solid #edf1f7; background: #fbfcfe; }
.quick-intent { flex: 0 0 auto; border: 1px solid #d7deea; border-radius: 999px; padding: 6px 12px; background: #fff; color: #344054; cursor: pointer; font-size: 13px; }
.quick-intent:hover:not(:disabled) { border-color: #1f6feb; color: #1f6feb; background: #f5f9ff; }
.quick-intent:disabled { cursor: not-allowed; opacity: 0.55; }
.chat-body { min-height: 0; overflow-y: auto; padding: 16px 18px; background: linear-gradient(#fff, #f8fafc); }
.empty { display: grid; place-items: center; align-content: center; min-height: 260px; color: #667085; text-align: center; }
.empty-title { color: #25324b; font-weight: 700; font-size: 18px; }
.empty-copy { margin-top: 8px; font-size: 13px; }
.chat-input { display: flex; gap: 10px; align-items: flex-end; padding: 12px 14px; border-top: 1px solid #e4e9f2; background: #fff; }
.service-panel { display: grid; align-content: start; gap: 12px; overflow-y: auto; }
.panel-section { border: 1px solid #e4e9f2; border-radius: 8px; padding: 14px; background: #fff; }
.panel-section.muted { color: #667085; }
.panel-title { margin-bottom: 12px; color: #25324b; font-weight: 700; font-size: 14px; }
.context-list { display: grid; gap: 10px; }
.context-item { display: flex; justify-content: space-between; gap: 12px; color: #667085; font-size: 13px; }
.context-item strong { color: #25324b; text-align: right; font-weight: 700; }
.status-card { background: #fbfcfe; }
.progress-line { display: flex; align-items: center; gap: 8px; min-height: 28px; color: #475467; font-size: 13px; }
.progress-dot { width: 9px; height: 9px; border-radius: 50%; background: #d0d5dd; }
.progress-dot.done { background: #1f6feb; box-shadow: 0 0 0 4px #e8f1ff; }
.side-trace { display: grid; gap: 10px; }
.side-trace-step { display: grid; grid-template-columns: 22px 1fr; gap: 8px; align-items: start; }
.side-trace-step > span { width: 22px; height: 22px; display: inline-flex; align-items: center; justify-content: center; border-radius: 50%; background: #e8f1ff; color: #1f6feb; font-size: 12px; font-weight: 700; }
.side-trace-step strong { display: block; color: #344054; font-size: 13px; }
.side-trace-step p { margin: 2px 0 0; color: #667085; font-size: 12px; line-height: 1.45; }
.panel-empty { color: #667085; font-size: 13px; }

@media (max-width: 900px) {
  .chat-header { align-items: flex-start; padding: 12px 14px; }
  .header-actions { align-items: flex-end; flex-direction: column; gap: 8px; }
  .customer-input { width: 150px; }
  .chat-shell { grid-template-columns: 1fr; height: auto; min-height: calc(100dvh - 62px); padding: 10px; }
  .chat-main { min-height: calc(100dvh - 82px); }
  .service-panel { grid-row: 1; grid-template-columns: 1fr; }
  .panel-section:not(:first-child) { display: none; }
}
</style>
