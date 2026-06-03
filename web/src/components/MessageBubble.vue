<script setup>
defineProps({
  role: { type: String, required: true },
  content: { type: String, default: '' },
  citations: { type: Array, default: () => [] },
})
</script>

<template>
  <div class="bubble-row" :class="`row-${role}`">
    <div class="bubble" :class="`bubble-${role}`">
      <div class="bubble-content">{{ content }}</div>
      <div v-if="citations.length" class="citations">
        <span class="citation-label">引用：</span>
        <el-tag v-for="(c, i) in citations" :key="i" size="small" type="info" class="citation-tag">
          {{ c.title }}<span v-if="c.source"> · {{ c.source }}</span>
        </el-tag>
      </div>
    </div>
  </div>
</template>

<style scoped>
.bubble-row { display: flex; margin: 8px 0; }
.row-customer { justify-content: flex-end; }
.row-ai, .row-agent, .row-system { justify-content: flex-start; }
.bubble { max-width: 70%; padding: 10px 14px; border-radius: 10px; line-height: 1.5; }
.bubble-customer { background: #409eff; color: #fff; }
.bubble-ai { background: #f4f4f5; color: #303133; }
.bubble-agent { background: #e1f3d8; color: #303133; }
.bubble-system { background: #fdf6ec; color: #909399; font-size: 13px; }
.citations { margin-top: 6px; }
.citation-label { font-size: 12px; color: #909399; }
.citation-tag { margin-right: 4px; }
</style>
