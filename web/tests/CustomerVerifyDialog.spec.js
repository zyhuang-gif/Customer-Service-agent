import { mount } from '@vue/test-utils'
import { describe, expect, it } from 'vitest'
import CustomerVerifyDialog from '../src/components/CustomerVerifyDialog.vue'

describe('CustomerVerifyDialog', () => {
  it('提交手机号和最近订单号', async () => {
    const wrapper = mount(CustomerVerifyDialog, {
      props: { modelValue: true },
      global: {
        stubs: {
          ElDialog: { template: '<div><slot /><slot name="footer" /></div>' },
          ElButton: { template: '<button :disabled="disabled"><slot /></button>', props: ['disabled'] },
          ElInput: {
            props: ['modelValue'],
            emits: ['update:modelValue'],
            template: '<input :value="modelValue" @input="$emit(`update:modelValue`, $event.target.value)" />',
          },
        },
      },
    })

    await wrapper.find('[data-test="customer-phone"]').setValue(' 13800000001 ')
    await wrapper.find('[data-test="recent-order-id"]').setValue(' 20260531002 ')
    await wrapper.find('[data-test="verify-submit"]').trigger('click')

    expect(wrapper.emitted('verify')[0]).toEqual(['13800000001', '20260531002'])
  })

  it('关闭时清空表单并同步可见状态', async () => {
    const wrapper = mount(CustomerVerifyDialog, {
      props: { modelValue: true },
      global: {
        stubs: {
          ElDialog: { template: '<div><slot /><slot name="footer" /></div>' },
          ElButton: { template: '<button><slot /></button>' },
          ElInput: {
            props: ['modelValue'],
            emits: ['update:modelValue'],
            template: '<input :value="modelValue" @input="$emit(`update:modelValue`, $event.target.value)" />',
          },
        },
      },
    })

    await wrapper.find('[data-test="customer-phone"]').setValue('13800000001')
    await wrapper.find('[data-test="verify-cancel"]').trigger('click')

    expect(wrapper.emitted('update:modelValue')[0]).toEqual([false])
    expect(wrapper.vm.phone).toBe('')
  })
})
