<script setup>
defineProps({
  conversations: { type: Array, default: () => [] },
  activeId: { type: String, default: '' },
})
defineEmits(['select'])

const STATUS_TAG = {
  ai_handling: { text: 'AI处理中', type: 'primary' },
  awaiting_confirmation: { text: '待确认', type: 'danger' },
  human_handling: { text: '人工处理', type: 'warning' },
  resolved: { text: '已解决', type: 'success' },
  closed: { text: '已关闭', type: 'info' },
}
</script>

<template>
  <div class="conv-list">
    <div
      v-for="c in conversations"
      :key="c.id"
      class="conv-item"
      :class="{ active: c.id === activeId }"
      @click="$emit('select', c.id)"
    >
      <div class="conv-top">
        <span class="conv-ref">{{ c.customer_ref }}</span>
        <el-tag :type="(STATUS_TAG[c.status] || {}).type || 'info'" size="small">
          {{ (STATUS_TAG[c.status] || {}).text || c.status }}
        </el-tag>
      </div>
      <div class="conv-id">{{ c.id }}</div>
    </div>
    <div v-if="!conversations.length" class="empty">暂无会话</div>
  </div>
</template>

<style scoped>
.conv-list { height: 100%; overflow-y: auto; }
.conv-item { padding: 10px 12px; border-bottom: 1px solid #ebeef5; cursor: pointer; }
.conv-item:hover { background: #f5f7fa; }
.conv-item.active { background: #ecf5ff; }
.conv-top { display: flex; justify-content: space-between; align-items: center; }
.conv-ref { font-weight: 600; }
.conv-id { font-size: 12px; color: #909399; margin-top: 2px; }
.empty { color: #909399; text-align: center; padding: 20px; }
</style>
