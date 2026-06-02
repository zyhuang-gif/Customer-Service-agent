<script setup>
import { ref } from 'vue'
import { chatStream } from '../api/sse'
import MessageBubble from '../components/MessageBubble.vue'

const customerRef = ref('13800000001')
const conversationId = ref('')
const input = ref('')
const messages = ref([])
const sending = ref(false)

async function send() {
  const text = input.value.trim()
  if (!text || sending.value) return
  messages.value.push({ role: 'customer', content: text })
  input.value = ''
  sending.value = true
  let aiContent = ''
  let aiIndex = -1
  try {
    await chatStream(
      { conversationId: conversationId.value, customerRef: customerRef.value, message: text },
      (ev) => {
        if (ev.type === 'start') {
          conversationId.value = ev.conversation_id
        } else if (ev.type === 'response') {
          aiContent = ev.content
          if (aiIndex === -1) {
            messages.value.push({ role: 'ai', content: aiContent })
            aiIndex = messages.value.length - 1
          } else {
            messages.value[aiIndex].content = aiContent
          }
        } else if (ev.type === 'awaiting_confirmation') {
          messages.value.push({ role: 'system', content: ev.content || '该操作已提交人工确认，请稍候。' })
        }
      },
    )
  } catch (e) {
    messages.value.push({ role: 'system', content: '网络错误，请重试。' })
  } finally {
    sending.value = false
  }
}
</script>

<template>
  <div class="chat-page">
    <div class="chat-header">
      <span>智能售后客服</span>
      <el-input v-model="customerRef" size="small" style="width: 160px" placeholder="手机号/标识" />
    </div>
    <div class="chat-body">
      <MessageBubble
        v-for="(m, i) in messages"
        :key="i"
        :role="m.role"
        :content="m.content"
        :citations="m.citations || []"
      />
      <div v-if="!messages.length" class="empty">您好，请问有什么可以帮您？</div>
    </div>
    <div class="chat-input">
      <el-input
        v-model="input"
        type="textarea"
        :rows="2"
        placeholder="输入您的问题，回车发送"
        @keydown.enter.prevent="send"
      />
      <el-button type="primary" :loading="sending" @click="send">发送</el-button>
    </div>
  </div>
</template>

<style scoped>
.chat-page { display: flex; flex-direction: column; height: 100vh; max-width: 720px; margin: 0 auto; }
.chat-header { display: flex; justify-content: space-between; align-items: center; padding: 12px 16px; border-bottom: 1px solid #ebeef5; font-weight: 600; }
.chat-body { flex: 1; overflow-y: auto; padding: 16px; }
.empty { color: #909399; text-align: center; margin-top: 40px; }
.chat-input { display: flex; gap: 8px; padding: 12px 16px; border-top: 1px solid #ebeef5; }
</style>
