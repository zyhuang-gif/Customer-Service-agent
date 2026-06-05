<script setup>
import { computed, onMounted, onUnmounted, ref } from 'vue'
import { api } from '../api/client'
import { chatStream } from '../api/sse'
import CustomerHistoryDrawer from '../components/CustomerHistoryDrawer.vue'
import CustomerVerifyDialog from '../components/CustomerVerifyDialog.vue'
import MessageBubble from '../components/MessageBubble.vue'
import { useCustomerSessionStore } from '../stores/customerSession'

const customerSession = useCustomerSessionStore()

const conversationId = ref('')
const input = ref('')
const messages = ref([])
const sending = ref(false)
const historyOpen = ref(false)
const historyLoading = ref(false)
const historyError = ref('')
const conversations = ref([])
const verifyOpen = ref(false)
const verifyLoading = ref(false)
const verifyError = ref('')
let typeTimer = 0

const quickIntents = [
  { key: 'order', label: '查订单', text: '我想查询订单状态' },
  { key: 'logistics', label: '查物流', text: '我想查询物流进度' },
  { key: 'refund', label: '退款进度', text: '我想查询退款进度' },
  { key: 'return', label: '退货规则', text: '我想了解退货规则' },
  { key: 'handoff', label: '转人工', text: '我要转人工客服' },
]

const latestServiceMessage = computed(() => {
  return [...messages.value].reverse().find((m) => ['ai', 'system', 'agent'].includes(m.role)) || null
})

const sessionStatus = computed(() => {
  if (sending.value) return { label: '处理中', tone: 'processing' }
  const content = latestServiceMessage.value?.content || ''
  if (content.includes('人工确认') || content.includes('转人工')) return { label: '待人工', tone: 'attention' }
  if (messages.value.length) return { label: '咨询中', tone: 'active' }
  return { label: '新咨询', tone: 'idle' }
})

function clearLegacyCache() {
  localStorage.removeItem('chat_customer_ref')
  localStorage.removeItem('chat_conversation_id')
  localStorage.removeItem('chat_messages')
}

function normalizeRows(rows) {
  return rows.map((message) => ({
    role: message.role,
    content: message.content,
    citations: message.meta?.citations || [],
    agent_trace: message.meta?.agent_trace || [],
  }))
}

function clearTypeTimer() {
  if (!typeTimer) return
  window.clearInterval(typeTimer)
  typeTimer = 0
}

function startNewConsultation() {
  clearTypeTimer()
  conversationId.value = ''
  messages.value = []
  input.value = ''
}

async function openConversation(id) {
  if (!customerSession.isLoggedIn) {
    verifyOpen.value = true
    return
  }
  const rows = await api(`/customer/conversations/${id}/messages`, { token: customerSession.token })
  conversationId.value = id
  messages.value = normalizeRows(rows)
  historyOpen.value = false
}

async function initializeRecentConversation() {
  startNewConsultation()
  if (!customerSession.isLoggedIn) return
  try {
    const recent = await api('/customer/conversations/recent', { token: customerSession.token })
    if (recent.should_resume && recent.conversation?.id) {
      await openConversation(recent.conversation.id)
    }
  } catch (error) {
    customerSession.logout()
  }
}

async function loadHistory() {
  if (!customerSession.isLoggedIn) {
    verifyOpen.value = true
    return
  }
  historyOpen.value = true
  historyLoading.value = true
  historyError.value = ''
  try {
    conversations.value = await api('/customer/conversations', { token: customerSession.token })
  } catch (error) {
    historyError.value = error.message || '历史咨询加载失败'
    if (historyError.value.includes('登录')) customerSession.logout()
  } finally {
    historyLoading.value = false
  }
}

async function verifyCustomer(phone, recentOrderId) {
  verifyLoading.value = true
  verifyError.value = ''
  try {
    await customerSession.verify(phone, recentOrderId)
    verifyOpen.value = false
    await initializeRecentConversation()
  } catch (error) {
    verifyError.value = error.message || '验证失败'
  } finally {
    verifyLoading.value = false
  }
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
  if (cursor >= text.length) return

  typeTimer = window.setInterval(() => {
    cursor = Math.min(cursor + 2, text.length)
    messages.value[index] = { role: 'ai', content: text.slice(0, cursor), ...extra }
    if (cursor >= text.length) clearTypeTimer()
  }, 30)
}

function replacePending(index, role, content, meta = {}) {
  clearTypeTimer()
  messages.value[index] = {
    role,
    content,
    citations: meta.citations || [],
    agent_trace: meta.agent_trace || [],
  }
}

async function send() {
  const text = input.value.trim()
  if (!text || sending.value) return
  messages.value.push({ role: 'customer', content: text })
  const pendingIndex = messages.value.length
  messages.value.push({ role: 'system', content: '正在处理，请稍候...' })
  input.value = ''
  sending.value = true
  try {
    await chatStream(
      {
        conversationId: conversationId.value,
        customerRef: 'anonymous-web',
        message: text,
        token: customerSession.isLoggedIn ? customerSession.token : '',
      },
      (event) => {
        if (event.type === 'start') {
          conversationId.value = event.conversation_id
        } else if (event.type === 'response') {
          playResponse(pendingIndex, event.content, event)
        } else if (event.type === 'awaiting_confirmation') {
          replacePending(pendingIndex, 'system', event.content || '该操作已提交人工确认，请稍候。', event)
        } else if (event.type === 'identity_required') {
          replacePending(pendingIndex, 'system', event.content || '请先完成客户身份验证。')
          verifyOpen.value = true
        } else if (event.type === 'access_denied') {
          replacePending(pendingIndex, 'system', event.content || '无法访问该咨询内容。')
        } else if (event.type === 'service_unavailable') {
          replacePending(pendingIndex, 'system', event.content || '服务暂时不可用，请稍后再试。')
        }
      },
    )
  } catch (error) {
    replacePending(pendingIndex, 'system', error.message || '网络错误，请重试。')
    if ((error.message || '').includes('登录')) {
      customerSession.logout()
      verifyOpen.value = true
    }
  } finally {
    sending.value = false
  }
}

async function useQuickIntent(intent) {
  if (sending.value) return
  input.value = intent.text
  await send()
}

function logout() {
  customerSession.logout()
  startNewConsultation()
}

onMounted(async () => {
  clearLegacyCache()
  customerSession.restore()
  await initializeRecentConversation()
})

onUnmounted(() => {
  clearTypeTimer()
})
</script>

<template>
  <div class="chat-page">
    <header class="chat-header">
      <div>
        <div class="service-title">智能售后客服</div>
        <div class="service-subtitle">订单、物流、退款与人工协同</div>
      </div>
      <div class="header-actions">
        <span class="status-pill" :class="`status-${sessionStatus.tone}`">{{ sessionStatus.label }}</span>
        <button class="text-action" type="button" data-test="new-consultation" @click="startNewConsultation">新咨询</button>
        <button class="text-action" type="button" data-test="history-open" @click="loadHistory">历史咨询</button>
        <button
          v-if="customerSession.isLoggedIn"
          class="account-button"
          type="button"
          data-test="account-label"
          @click="logout"
        >
          {{ customerSession.maskedPhone }}
        </button>
        <button v-else class="account-button" type="button" data-test="verify-open" @click="verifyOpen = true">
          验证身份
        </button>
      </div>
    </header>

    <main class="chat-shell">
      <section class="chat-main">
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
            v-for="(message, index) in messages"
            :key="index"
            :role="message.role"
            :content="message.content"
            :citations="message.citations || []"
            :agent-trace="message.agent_trace || []"
          />
        </div>

        <form class="chat-input" @submit.prevent="send">
          <textarea
            v-model="input"
            class="message-input"
            rows="2"
            placeholder="输入您的问题"
            @keydown.enter.prevent="send"
          ></textarea>
          <button class="send-button" type="submit" :disabled="sending || !input.trim()">
            {{ sending ? '发送中' : '发送' }}
          </button>
        </form>
      </section>
    </main>

    <CustomerVerifyDialog
      v-model="verifyOpen"
      :loading="verifyLoading"
      :error="verifyError"
      @verify="verifyCustomer"
    />
    <CustomerHistoryDrawer
      v-model="historyOpen"
      :conversations="conversations"
      :loading="historyLoading"
      :error="historyError"
      @select="openConversation"
      @retry="loadHistory"
    />
  </div>
</template>

<style scoped>
.chat-page { min-height: 100dvh; background: #f5f7fb; color: #25324b; }
.chat-header { display: flex; justify-content: space-between; align-items: center; gap: 16px; padding: 14px 24px; border-bottom: 1px solid #e4e9f2; background: #fff; }
.service-title { font-weight: 700; font-size: 17px; }
.service-subtitle { margin-top: 2px; color: #667085; font-size: 12px; }
.header-actions { display: flex; align-items: center; gap: 8px; flex-wrap: wrap; justify-content: flex-end; }
.status-pill { display: inline-flex; align-items: center; min-height: 26px; border-radius: 999px; padding: 2px 10px; font-size: 12px; font-weight: 700; border: 1px solid transparent; }
.status-active, .status-idle { background: #e8f1ff; color: #1f6feb; border-color: #c9ddff; }
.status-processing { background: #fff7e6; color: #a15c00; border-color: #f7d99a; }
.status-attention { background: #fff1f0; color: #b42318; border-color: #f3b8b2; }
.text-action, .account-button { border: 1px solid #d7deea; border-radius: 8px; padding: 6px 10px; background: #fff; color: #344054; cursor: pointer; font-size: 13px; }
.text-action:hover, .account-button:hover { border-color: #1f6feb; color: #1f6feb; background: #f5f9ff; }
.account-button { font-weight: 700; }
.chat-shell { max-width: 920px; height: calc(100dvh - 62px); margin: 0 auto; padding: 16px; }
.chat-main { display: grid; grid-template-rows: auto minmax(0, 1fr) auto; height: 100%; border: 1px solid #e4e9f2; border-radius: 8px; background: #fff; overflow: hidden; }
.quick-intents { display: flex; gap: 8px; overflow-x: auto; padding: 12px 14px; border-bottom: 1px solid #edf1f7; background: #fbfcfe; }
.quick-intent { flex: 0 0 auto; border: 1px solid #d7deea; border-radius: 999px; padding: 6px 12px; background: #fff; color: #344054; cursor: pointer; font-size: 13px; }
.quick-intent:hover:not(:disabled) { border-color: #1f6feb; color: #1f6feb; background: #f5f9ff; }
.quick-intent:disabled { cursor: not-allowed; opacity: 0.55; }
.chat-body { min-height: 0; overflow-y: auto; padding: 18px; background: linear-gradient(#fff, #f8fafc); }
.empty { display: grid; place-items: center; align-content: center; min-height: 280px; color: #667085; text-align: center; }
.empty-title { color: #25324b; font-weight: 700; font-size: 20px; }
.empty-copy { margin-top: 8px; font-size: 13px; }
.chat-input { display: grid; grid-template-columns: minmax(0, 1fr) auto; gap: 10px; align-items: end; padding: 12px 14px; border-top: 1px solid #e4e9f2; background: #fff; }
.message-input { width: 100%; resize: none; border: 1px solid #d7deea; border-radius: 8px; padding: 9px 10px; color: #25324b; font: inherit; line-height: 1.5; }
.message-input:focus { outline: none; border-color: #1f6feb; box-shadow: 0 0 0 3px #e8f1ff; }
.send-button { min-width: 76px; border: 1px solid #1f6feb; border-radius: 8px; padding: 9px 14px; background: #1f6feb; color: #fff; cursor: pointer; font-weight: 700; }
.send-button:disabled { cursor: not-allowed; opacity: 0.6; }

@media (max-width: 760px) {
  .chat-header { align-items: flex-start; padding: 12px 14px; }
  .chat-shell { height: calc(100dvh - 92px); padding: 10px; }
  .chat-input { grid-template-columns: 1fr; }
  .send-button { width: 100%; }
}
</style>
