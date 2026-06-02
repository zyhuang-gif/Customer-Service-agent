<script setup>
defineProps({
  action: { type: Object, required: true },
})
const emit = defineEmits(['review'])

const RISK_LABEL = {
  apply_refund: '发起退款',
  change_address: '修改收货地址',
  issue_coupon: '发放优惠券',
}
</script>

<template>
  <el-card class="pending-card" shadow="hover">
    <div class="pending-title">
      <el-tag type="danger" size="small">待确认</el-tag>
      <span class="tool">{{ RISK_LABEL[action.tool_name] || action.tool_name }}（{{ action.tool_name }}）</span>
    </div>
    <div class="params">
      <div v-for="(v, k) in action.params" :key="k" class="param-row">
        <span class="param-key">{{ k }}：</span><span class="param-val">{{ v }}</span>
      </div>
    </div>
    <div class="actions">
      <el-button class="btn-approve" type="success" size="small" @click="emit('review', { id: action.id, approved: true })">
        确认执行
      </el-button>
      <el-button class="btn-reject" type="info" size="small" @click="emit('review', { id: action.id, approved: false })">
        驳回
      </el-button>
    </div>
  </el-card>
</template>

<style scoped>
.pending-card { margin-bottom: 12px; border-left: 3px solid #f56c6c; }
.pending-title { display: flex; align-items: center; gap: 8px; margin-bottom: 8px; }
.tool { font-weight: 600; }
.params { background: #fafafa; padding: 8px; border-radius: 4px; font-size: 13px; }
.param-key { color: #909399; }
.actions { margin-top: 10px; display: flex; gap: 8px; }
</style>
