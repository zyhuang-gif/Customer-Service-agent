import { flushPromises, mount } from '@vue/test-utils'
import { createPinia, setActivePinia } from 'pinia'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import AgentDeskView from '../src/views/AgentDeskView.vue'

const conversationsFirst = []
const conversationsSecond = [
  { id: 'conv-1', customer_ref: '13800000001', status: 'awaiting_confirmation' },
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
})
