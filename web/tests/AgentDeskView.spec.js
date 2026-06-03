import { flushPromises, mount } from '@vue/test-utils'
import { createPinia, setActivePinia } from 'pinia'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import AgentDeskView from '../src/views/AgentDeskView.vue'

const conversationsFirst = []
const conversationsSecond = [
  { id: 'conv-1', customer_ref: '13800000001', status: 'awaiting_confirmation' },
]
const humanConversation = [
  {
    id: 'conv-human',
    customer_ref: '13800000002',
    status: 'human_handling',
    summary: '客户问题：我要转人工\n客户情绪：angry / high\n建议人工处理：先安抚客户',
  },
]
const pendingFirst = []
const pendingSecond = [
  {
    id: 1,
    conversation_id: 'conv-1',
    tool_name: 'apply_refund',
    params: { order_id: '20260531002', amount: 499 },
  },
]

describe('AgentDeskView', () => {
  beforeEach(() => {
    vi.useFakeTimers()
    setActivePinia(createPinia())
    localStorage.clear()
    localStorage.setItem('cs_token', 'token-1')
  })

  afterEach(() => {
    vi.useRealTimers()
    vi.restoreAllMocks()
  })

  it('定时刷新会话列表和待确认动作', async () => {
    let conversationsCalls = 0
    let pendingCalls = 0
    vi.stubGlobal('fetch', vi.fn(async (url) => {
      if (String(url).endsWith('/conversations')) {
        conversationsCalls += 1
        return {
          ok: true,
          json: async () => (conversationsCalls === 1 ? conversationsFirst : conversationsSecond),
        }
      }
      if (String(url).endsWith('/pending-actions')) {
        pendingCalls += 1
        return {
          ok: true,
          json: async () => (pendingCalls === 1 ? pendingFirst : pendingSecond),
        }
      }
      return { ok: true, json: async () => [] }
    }))

    const wrapper = mount(AgentDeskView)
    await flushPromises()
    expect(wrapper.text()).toContain('暂无会话')
    expect(wrapper.text()).toContain('暂无待确认动作')

    await vi.advanceTimersByTimeAsync(3000)
    await flushPromises()

    expect(wrapper.text()).toContain('13800000001')
    expect(wrapper.text()).toContain('发起退款')
    expect(fetch).toHaveBeenCalledWith(
      'http://localhost:8000/conversations',
      expect.objectContaining({
        headers: expect.objectContaining({ Authorization: 'Bearer token-1' }),
      }),
    )
  })

  it('人工处理会话允许坐席发送回复', async () => {
    vi.stubGlobal('fetch', vi.fn(async (url, options = {}) => {
      if (String(url).endsWith('/conversations')) {
        return { ok: true, json: async () => humanConversation }
      }
      if (String(url).endsWith('/pending-actions')) {
        return { ok: true, json: async () => [] }
      }
      if (String(url).endsWith('/conversations/conv-human/messages') && options.method === 'POST') {
        return {
          ok: true,
          json: async () => ({
            id: 2,
            role: 'agent',
            content: '您好，我来继续处理。',
            meta: { agent_id: 1 },
          }),
        }
      }
      if (String(url).endsWith('/conversations/conv-human/messages')) {
        return {
          ok: true,
          json: async () => [
            { id: 1, role: 'customer', content: '我要转人工', meta: {} },
          ],
        }
      }
      return { ok: true, json: async () => [] }
    }))

    const wrapper = mount(AgentDeskView)
    await flushPromises()
    await wrapper.find('.conv-item').trigger('click')
    await flushPromises()

    wrapper.vm.agentReply = '您好，我来继续处理。'
    await wrapper.vm.sendAgentReply()
    await flushPromises()

    expect(fetch).toHaveBeenCalledWith(
      'http://localhost:8000/conversations/conv-human/messages',
      expect.objectContaining({
        method: 'POST',
        body: JSON.stringify({ content: '您好，我来继续处理。' }),
        headers: expect.objectContaining({ Authorization: 'Bearer token-1' }),
      }),
    )
    expect(wrapper.text()).toContain('您好，我来继续处理。')
  })

  it('转人工摘要只展示在坐席侧接管信息中', async () => {
    vi.stubGlobal('fetch', vi.fn(async (url) => {
      if (String(url).endsWith('/conversations')) {
        return { ok: true, json: async () => humanConversation }
      }
      if (String(url).endsWith('/pending-actions')) {
        return { ok: true, json: async () => [] }
      }
      if (String(url).endsWith('/conversations/conv-human/messages')) {
        return {
          ok: true,
          json: async () => [
            { id: 1, role: 'customer', content: '我要转人工', meta: { sentiment: 'angry', risk: 'high' } },
          ],
        }
      }
      return { ok: true, json: async () => [] }
    }))

    const wrapper = mount(AgentDeskView)
    await flushPromises()
    await wrapper.find('.conv-item').trigger('click')
    await flushPromises()

    expect(wrapper.find('.handoff-panel').text()).toContain('客户问题：我要转人工')
    expect(wrapper.find('.handoff-panel').text()).toContain('客户情绪：angry / high')
    expect(wrapper.find('.msg-area').text()).not.toContain('客户情绪：angry / high')
    expect(wrapper.find('.msg-area').text()).not.toContain('建议人工处理：先安抚客户')
  })

  it('坐席侧展示 AI 消息的 Agent Trace', async () => {
    vi.stubGlobal('fetch', vi.fn(async (url) => {
      if (String(url).endsWith('/conversations')) {
        return { ok: true, json: async () => conversationsSecond }
      }
      if (String(url).endsWith('/pending-actions')) {
        return { ok: true, json: async () => [] }
      }
      if (String(url).endsWith('/conversations/conv-1/messages')) {
        return {
          ok: true,
          json: async () => [
            { id: 1, role: 'customer', content: '退款多久到账？', meta: {} },
            {
              id: 2,
              role: 'ai',
              content: '退款通常需要 1-5 个工作日到账。',
              meta: {
                agent_trace: [
                  { agent: 'CoordinatorAgent', summary: '识别为退款咨询' },
                  { agent: 'KnowledgeAgent', summary: '检索退款政策' },
                ],
              },
            },
          ],
        }
      }
      return { ok: true, json: async () => [] }
    }))

    const wrapper = mount(AgentDeskView)
    await flushPromises()
    await wrapper.find('.conv-item').trigger('click')
    await flushPromises()

    expect(wrapper.find('.agent-trace').text()).toContain('CoordinatorAgent')
    expect(wrapper.find('.agent-trace').text()).toContain('检索退款政策')
  })

  it('人工处理会话展示常用语且点击只填入回复草稿', async () => {
    vi.stubGlobal('fetch', vi.fn(async (url) => {
      if (String(url).endsWith('/conversations')) {
        return { ok: true, json: async () => humanConversation }
      }
      if (String(url).endsWith('/pending-actions')) {
        return { ok: true, json: async () => [] }
      }
      if (String(url).endsWith('/conversations/conv-human/messages')) {
        return {
          ok: true,
          json: async () => [
            { id: 1, role: 'customer', content: '我要转人工', meta: {} },
          ],
        }
      }
      return { ok: true, json: async () => [] }
    }))

    const wrapper = mount(AgentDeskView)
    await flushPromises()
    await wrapper.find('.conv-item').trigger('click')
    await flushPromises()

    const quickReply = wrapper.find('.quick-replies button')
    expect(wrapper.find('.quick-replies').text()).toContain('我先为您核实订单/物流/退款信息，请稍等。')

    await quickReply.trigger('click')

    expect(wrapper.vm.agentReply).toBe(quickReply.text())
    expect(fetch).not.toHaveBeenCalledWith(
      'http://localhost:8000/conversations/conv-human/messages',
      expect.objectContaining({ method: 'POST' }),
    )
  })

  it('坐席可按订单号查询并查看订单完整信息', async () => {
    vi.stubGlobal('fetch', vi.fn(async (url) => {
      if (String(url).endsWith('/conversations')) {
        return { ok: true, json: async () => humanConversation }
      }
      if (String(url).endsWith('/pending-actions')) {
        return { ok: true, json: async () => [] }
      }
      if (String(url).endsWith('/conversations/conv-human/messages')) {
        return {
          ok: true,
          json: async () => [
            { id: 1, role: 'customer', content: '请帮我看下 20260531002', meta: {} },
          ],
        }
      }
      if (String(url).endsWith('/agent-desk/orders/20260531002')) {
        return {
          ok: true,
          json: async () => ({
            order: {
              id: '20260531002',
              status: '已发货',
              amount: 499,
              address: '上海市浦东新区',
              items: [{ name: '保温杯', qty: 1 }],
            },
            customer: { name: '张三', phone: '13800000001', member_level: 'VIP' },
            logistics: { carrier: '顺丰', tracking_no: 'SF123', status: '运输中' },
            refund: { status: '无', refund: null },
            tickets: [{ id: 't1', status: 'open', summary: '催物流' }],
          }),
        }
      }
      return { ok: true, json: async () => [] }
    }))

    const wrapper = mount(AgentDeskView)
    await flushPromises()
    await wrapper.find('.conv-item').trigger('click')
    await flushPromises()

    wrapper.vm.orderLookupId = '20260531002'
    await wrapper.vm.lookupOrder()
    await flushPromises()

    expect(fetch).toHaveBeenCalledWith(
      'http://localhost:8000/agent-desk/orders/20260531002',
      expect.objectContaining({
        headers: expect.objectContaining({ Authorization: 'Bearer token-1' }),
      }),
    )
    expect(wrapper.find('.order-lookup').text()).toContain('20260531002')
    expect(wrapper.find('.order-lookup').text()).toContain('张三')
    expect(wrapper.find('.order-lookup').text()).toContain('顺丰')
    expect(wrapper.find('.order-lookup').text()).toContain('SF123')
    expect(wrapper.find('.order-lookup').text()).toContain('催物流')
  })
})
