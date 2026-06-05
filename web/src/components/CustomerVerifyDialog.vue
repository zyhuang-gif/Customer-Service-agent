<script setup>
import { ref, watch } from 'vue'

const props = defineProps({
  modelValue: { type: Boolean, default: false },
  loading: { type: Boolean, default: false },
  error: { type: String, default: '' },
})
const emit = defineEmits(['update:modelValue', 'verify'])

const phone = ref('')
const recentOrderId = ref('')

function reset() {
  phone.value = ''
  recentOrderId.value = ''
}

function close() {
  reset()
  emit('update:modelValue', false)
}

function submit() {
  if (props.loading) return
  const trimmedPhone = phone.value.trim()
  const trimmedOrder = recentOrderId.value.trim()
  if (!trimmedPhone || !trimmedOrder) return
  emit('verify', trimmedPhone, trimmedOrder)
}

watch(() => props.modelValue, (visible) => {
  if (!visible) reset()
})
</script>

<template>
  <el-dialog
    :model-value="modelValue"
    title="验证身份"
    width="420px"
    @update:model-value="emit('update:modelValue', $event)"
    @closed="reset"
  >
    <div class="verify-form">
      <label class="field-label" for="customer-phone">手机号</label>
      <el-input
        id="customer-phone"
        v-model="phone"
        data-test="customer-phone"
        autocomplete="tel"
        placeholder="请输入手机号"
      />

      <label class="field-label" for="recent-order-id">最近订单号</label>
      <el-input
        id="recent-order-id"
        v-model="recentOrderId"
        data-test="recent-order-id"
        autocomplete="off"
        placeholder="请输入最近订单号"
        @keydown.enter.prevent="submit"
      />

      <p v-if="error" class="verify-error">{{ error }}</p>
    </div>

    <template #footer>
      <div class="dialog-actions">
        <el-button data-test="verify-cancel" :disabled="loading" @click="close">取消</el-button>
        <el-button
          data-test="verify-submit"
          type="primary"
          :loading="loading"
          :disabled="!phone.trim() || !recentOrderId.trim()"
          @click="submit"
        >
          验证
        </el-button>
      </div>
    </template>
  </el-dialog>
</template>

<style scoped>
.verify-form { display: grid; gap: 10px; }
.field-label { color: #344054; font-size: 13px; font-weight: 700; }
.verify-error { margin: 2px 0 0; color: #b42318; font-size: 13px; }
.dialog-actions { display: flex; justify-content: flex-end; gap: 8px; }
</style>
