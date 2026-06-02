<script setup>
import { ref, onMounted } from 'vue'
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

async function loadConversations() {
  conversations.value = await api('/conversations', { token: auth.token })
}

async function loadPending() {
  pendingActions.value = await api('/pending-actions', { token: auth.token })
}

async function selectConversation(id) {
  activeId.value = id
  messages.value = await api(`/conversations/${id}/messages`, { token: auth.token })
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
  loadConversations()
  loadPending()
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
.empty { color: #909399; text-align: center; margin-top: 40px; }
</style>
