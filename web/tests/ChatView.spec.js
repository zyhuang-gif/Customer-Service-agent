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

  it('空会话展示真实客服入口和服务上下文', async () => {
    const wrapper = mount(ChatView)
    await flushPromises()

    expect(wrapper.text()).toContain('服务中')
    expect(wrapper.text()).toContain('查订单')
    expect(wrapper.text()).toContain('查物流')
    expect(wrapper.text()).toContain('退款进度')
    expect(wrapper.text()).toContain('服务上下文')
    expect(wrapper.text()).toContain('等待用户描述问题')
  })

  it('点击快捷入口会填充输入框并发送问题', async () => {
    vi.stubGlobal('fetch', vi.fn(async () => ({
      body: {
        getReader: () => ({
          read: vi.fn().mockResolvedValueOnce({ done: true }),
        }),
      },
    })))
    const wrapper = mount(ChatView)
    await flushPromises()

    await wrapper.find('[data-test="quick-intent-logistics"]').trigger('click')
    await flushPromises()

    expect(wrapper.text()).toContain('我想查询物流进度')
    expect(fetch).toHaveBeenCalledOnce()
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

    expect(wrapper.text()).toContain('物流')
    expect(wrapper.text()).not.toContain('物流运输中。')

    await vi.advanceTimersByTimeAsync(200)
    await flushPromises()

    expect(wrapper.text()).toContain('物流运输中。')
    expect(wrapper.text()).not.toContain('正在处理，请稍候')
  })

  it('保存 SSE 返回的引用并展示脱敏后的处理进度', async () => {
    let resolveFetch
    vi.stubGlobal('fetch', vi.fn(() => new Promise((resolve) => {
      resolveFetch = resolve
    })))
    const wrapper = mount(ChatView)
    await flushPromises()

    wrapper.vm.input = '退款多久到账？'
    const sendPromise = wrapper.vm.send()
    await flushPromises()

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
              value: new TextEncoder().encode('data: {"type":"response","content":"退款通常需要 1-5 个工作日到账。","citations":[{"title":"退款到账时间","source":"refund_policy.md"}],"agent_trace":[{"agent":"CoordinatorAgent","summary":"识别为退款咨询"}]}\n\n'),
            })
            .mockResolvedValueOnce({ done: true }),
        }),
      },
    })
    await sendPromise
    await vi.advanceTimersByTimeAsync(400)
    await flushPromises()

    const cached = JSON.parse(localStorage.getItem('chat_messages'))
    const ai = cached.find((m) => m.role === 'ai')
    expect(ai.citations[0].title).toBe('退款到账时间')
    expect(ai.agent_trace[0].agent).toBe('CoordinatorAgent')
    expect(wrapper.text()).toContain('退款到账时间')
    expect(wrapper.text()).toContain('识别为退款咨询')
    expect(wrapper.text()).toContain('处理进度')
    expect(wrapper.text()).not.toContain('AI 协同过程')
    expect(wrapper.text()).not.toContain('CoordinatorAgent')
  })

  it('高风险确认提示直接完整显示', async () => {
    let resolveFetch
    vi.stubGlobal('fetch', vi.fn(() => new Promise((resolve) => {
      resolveFetch = resolve
    })))
    const wrapper = mount(ChatView)
    await flushPromises()

    wrapper.vm.input = '我要退款'
    const sendPromise = wrapper.vm.send()
    await flushPromises()

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
              value: new TextEncoder().encode('data: {"type":"awaiting_confirmation","content":"该操作涉及资金/履约，已提交人工确认。"}\n\n'),
            })
            .mockResolvedValueOnce({ done: true }),
        }),
      },
    })
    await sendPromise
    await flushPromises()

    expect(wrapper.text()).toContain('该操作涉及资金/履约，已提交人工确认。')
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
