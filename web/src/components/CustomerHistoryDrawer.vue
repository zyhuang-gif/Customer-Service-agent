<script setup>
const props = defineProps({
  modelValue: { type: Boolean, default: false },
  conversations: { type: Array, default: () => [] },
  loading: { type: Boolean, default: false },
  error: { type: String, default: '' },
})
const emit = defineEmits(['update:modelValue', 'select', 'retry'])

const STATUS_TEXT = {
  ai_handling: 'AI处理中',
  awaiting_confirmation: '待确认',
  human_handling: '人工处理中',
  resolved: '已解决',
  closed: '已关闭',
}

function formatTime(value) {
  if (!value) return ''
  const date = new Date(value)
  if (Number.isNaN(date.getTime())) return ''
  return new Intl.DateTimeFormat('zh-CN', {
    month: '2-digit',
    day: '2-digit',
    hour: '2-digit',
    minute: '2-digit',
  }).format(date)
}

function statusText(status) {
  return STATUS_TEXT[status] || status || '处理中'
}
</script>

<template>
  <el-drawer
    :model-value="modelValue"
    title="历史咨询"
    size="360px"
    @update:model-value="emit('update:modelValue', $event)"
  >
    <div class="history-content">
      <div v-if="loading" class="history-state">加载中...</div>

      <div v-else-if="error" class="history-state error">
        <p>{{ error }}</p>
        <el-button data-test="history-retry" type="primary" @click="emit('retry')">重试</el-button>
      </div>

      <div v-else-if="!props.conversations.length" class="history-state">暂无历史咨询</div>

      <template v-else>
        <button
          v-for="conversation in props.conversations"
          :key="conversation.id"
          class="history-item"
          :data-test="`history-${conversation.id}`"
          type="button"
          @click="emit('select', conversation.id)"
        >
          <span class="history-main">
            <strong>{{ conversation.summary || '新咨询' }}</strong>
            <small>{{ formatTime(conversation.last_message_at || conversation.created_at) }}</small>
          </span>
          <el-tag size="small">{{ statusText(conversation.status) }}</el-tag>
        </button>
      </template>
    </div>
  </el-drawer>
</template>

<style scoped>
.history-content { display: grid; gap: 10px; }
.history-state { padding: 28px 8px; color: #667085; text-align: center; font-size: 14px; }
.history-state.error { color: #b42318; }
.history-state.error p { margin: 0 0 12px; }
.history-item { display: flex; align-items: center; justify-content: space-between; gap: 12px; width: 100%; border: 1px solid #e4e9f2; border-radius: 8px; padding: 12px; background: #fff; color: #25324b; cursor: pointer; text-align: left; }
.history-item:hover { border-color: #1f6feb; background: #f5f9ff; }
.history-main { display: grid; gap: 4px; min-width: 0; }
.history-main strong { overflow: hidden; text-overflow: ellipsis; white-space: nowrap; font-size: 14px; }
.history-main small { color: #667085; font-size: 12px; }
</style>
