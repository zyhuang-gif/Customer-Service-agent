import { flushPromises, mount } from '@vue/test-utils'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import ChatView from '../src/views/ChatView.vue'

describe('ChatView', () => {
  beforeEach(() => {
    localStorage.clear()
    vi.restoreAllMocks()
  })

  it('刷新后从本地缓存恢复当前会话和消息', async () => {
    localStorage.setItem('chat_customer_ref', '13800000001')
    localStorage.setItem('chat_conversation_id', 'conv-1')
    localStorage.setItem('chat_messages', JSON.stringify([
      { role: 'customer', content: '订单 20260531002 物流到哪了？' },
      { role: 'ai', content: '您的订单正在运输中。' },
    ]))

    const wrapper = mount(ChatView)
    await flushPromises()

    expect(wrapper.text()).toContain('订单 20260531002 物流到哪了？')
    expect(wrapper.text()).toContain('您的订单正在运输中。')
  })
})
