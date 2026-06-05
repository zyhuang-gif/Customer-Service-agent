import { mount } from '@vue/test-utils'
import { describe, expect, it } from 'vitest'
import CustomerHistoryDrawer from '../src/components/CustomerHistoryDrawer.vue'

function mountDrawer(props = {}) {
  return mount(CustomerHistoryDrawer, {
    props: {
      modelValue: true,
      conversations: [],
      ...props,
    },
    global: {
      stubs: {
        ElDrawer: { template: '<div><slot /></div>' },
        ElButton: { template: '<button><slot /></button>' },
        ElTag: { template: '<span><slot /></span>' },
      },
    },
  })
}

describe('CustomerHistoryDrawer', () => {
  it('选择历史咨询', async () => {
    const wrapper = mountDrawer({
      conversations: [{
        id: 'c1',
        summary: '物流查询',
        status: 'ai_handling',
        last_message_at: '2026-06-04T10:00:00Z',
      }],
    })

    await wrapper.find('[data-test="history-c1"]').trigger('click')

    expect(wrapper.text()).toContain('物流查询')
    expect(wrapper.text()).toContain('AI处理中')
    expect(wrapper.emitted('select')[0]).toEqual(['c1'])
  })

  it('展示空状态和重试状态', async () => {
    const empty = mountDrawer()
    expect(empty.text()).toContain('暂无历史咨询')

    const failed = mountDrawer({ error: '加载失败' })
    expect(failed.text()).toContain('加载失败')
    await failed.find('[data-test="history-retry"]').trigger('click')
    expect(failed.emitted('retry')).toBeTruthy()
  })
})
