<script setup>
defineProps({
  role: { type: String, required: true },
  content: { type: String, default: '' },
  citations: { type: Array, default: () => [] },
  agentTrace: { type: Array, default: () => [] },
})
</script>

<template>
  <div class="bubble-row" :class="`row-${role}`">
    <div class="bubble" :class="`bubble-${role}`">
      <div class="bubble-content">{{ content }}</div>

      <div v-if="citations.length" class="evidence-block">
        <div class="meta-title">依据 {{ citations.length }} 条</div>
        <div class="citation-list">
          <span v-for="(c, i) in citations" :key="i" class="citation-item">
            {{ c.title }}<span v-if="c.source"> · {{ c.source }}</span>
          </span>
        </div>
      </div>

      <div v-if="agentTrace.length" class="trace-block">
        <div class="meta-title">AI 协同过程</div>
        <div class="trace-list">
          <div v-for="(step, i) in agentTrace" :key="i" class="trace-step">
            <span class="trace-dot">{{ i + 1 }}</span>
            <span class="trace-agent">{{ step.agent || 'Agent' }}</span>
            <span class="trace-summary">{{ step.summary || step.action || '完成处理步骤' }}</span>
          </div>
        </div>
      </div>
    </div>
  </div>
</template>

<style scoped>
.bubble-row { display: flex; margin: 10px 0; }
.row-customer { justify-content: flex-end; }
.row-ai, .row-agent, .row-system { justify-content: flex-start; }
.bubble { max-width: min(74%, 620px); padding: 11px 14px; border-radius: 8px; line-height: 1.55; box-shadow: 0 1px 2px rgba(15, 23, 42, 0.05); }
.bubble-customer { background: #1f6feb; color: #fff; }
.bubble-ai { background: #fff; color: #25324b; border: 1px solid #e5eaf3; }
.bubble-agent { background: #edf7ed; color: #25324b; border: 1px solid #d8ead9; }
.bubble-system { background: #fff8eb; color: #7a5a16; border: 1px solid #f3dfb5; font-size: 13px; }
.bubble-content { white-space: pre-wrap; word-break: break-word; }
.evidence-block, .trace-block { margin-top: 10px; padding-top: 9px; border-top: 1px solid rgba(148, 163, 184, 0.24); }
.meta-title { margin-bottom: 6px; color: #667085; font-size: 12px; font-weight: 600; }
.citation-list { display: flex; flex-wrap: wrap; gap: 6px; }
.citation-item { border: 1px solid #d7deea; border-radius: 999px; padding: 2px 8px; background: #f8fafc; color: #475467; font-size: 12px; }
.trace-list { display: grid; gap: 6px; }
.trace-step { display: grid; grid-template-columns: 20px auto 1fr; align-items: center; gap: 7px; color: #475467; font-size: 12px; }
.trace-dot { width: 18px; height: 18px; border-radius: 50%; background: #e8f1ff; color: #1f6feb; display: inline-flex; align-items: center; justify-content: center; font-size: 11px; font-weight: 700; }
.trace-agent { color: #344054; font-weight: 600; }
.trace-summary { min-width: 0; word-break: break-word; }

@media (max-width: 720px) {
  .bubble { max-width: 88%; }
  .trace-step { grid-template-columns: 20px 1fr; }
  .trace-summary { grid-column: 2; }
}
</style>
