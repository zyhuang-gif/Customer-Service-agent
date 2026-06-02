import { flushPromises, mount } from '@vue/test-utils'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import ChatView from '../src/views/ChatView.vue'

describe('ChatView', () => {
  beforeEach(() => {
    vi.useFakeTimers()
    localStorage.clear()
    vi.restoreAllMocks()
  })

  afterEach(() => {
    vi.useRealTimers()
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

  it('发送后立即显示处理中反馈', async () => {
    let resolveFetch
    vi.stubGlobal('fetch', vi.fn(() => new Promise((resolve) => {
      resolveFetch = resolve
    })))
    const wrapper = mount(ChatView)
    await flushPromises()

    wrapper.vm.input = '订单 20260531002 物流到哪了？'
    const sendPromise = wrapper.vm.send()
    await flushPromises()

    expect(wrapper.text()).toContain('正在处理，请稍候')

    resolveFetch({
      body: {
        getReader: () => ({
          read: vi.fn()
            .mockResolvedValueOnce({
              done: false,
              value: new TextEncoder().encode('data: {"type":"start","conversation_id":"conv-1"}\n\n'),
            })
            .mockResolvedValueOnce({
              done: false,
              value: new TextEncoder().encode('data: {"type":"response","content":"物流运输中。"}\n\n'),
            })
            .mockResolvedValueOnce({ done: true }),
        }),
      },
    })
    await sendPromise
    await flushPromises()

    expect(wrapper.text()).toContain('物流运输中。')
    expect(wrapper.text()).not.toContain('正在处理，请稍候')
  })

  it('定时同步后端新增消息', async () => {
    localStorage.setItem('cs_token', 'token-1')
    localStorage.setItem('chat_conversation_id', 'conv-1')
    localStorage.setItem('chat_messages', JSON.stringify([
      { role: 'customer', content: '我要退款' },
      { role: 'system', content: '该操作涉及资金/履约，已提交人工确认。' },
    ]))
    let calls = 0
    vi.stubGlobal('fetch', vi.fn(async () => {
      calls += 1
      return {
        ok: true,
        json: async () => (calls === 1
          ? [
              { role: 'customer', content: '我要退款', meta: {} },
              { role: 'ai', content: '该操作涉及资金/履约，已提交人工确认。', meta: {} },
            ]
          : [
              { role: 'customer', content: '我要退款', meta: {} },
              { role: 'ai', content: '该操作涉及资金/履约，已提交人工确认。', meta: {} },
              { role: 'ai', content: '退款申请已确认执行。', meta: {} },
            ]),
      }
    }))

    const wrapper = mount(ChatView)
    await flushPromises()
    expect(wrapper.text()).not.toContain('退款申请已确认执行。')

    await vi.advanceTimersByTimeAsync(3000)
    await flushPromises()

    expect(wrapper.text()).toContain('退款申请已确认执行。')
  })
})
