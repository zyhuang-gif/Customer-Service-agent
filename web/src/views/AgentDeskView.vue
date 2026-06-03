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
let refreshTimer = 0

const activeConversation = computed(() => conversations.value.find((c) => c.id === activeId.value))
const canAgentReply = computed(() => activeConversation.value?.status === 'human_handling')

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
.empty { color: #909399; text-align: center; margin-top: 40px; }
</style>
