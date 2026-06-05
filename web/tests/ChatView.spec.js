import { createPinia, setActivePinia } from 'pinia'
import { flushPromises, mount } from '@vue/test-utils'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import ChatView from '../src/views/ChatView.vue'

function mountChat() {
  const pinia = createPinia()
  setActivePinia(pinia)
  return mount(ChatView, {
    global: {
      plugins: [pinia],
      stubs: {
        CustomerVerifyDialog: {
          props: ['modelValue'],
          emits: ['update:modelValue', 'verify'],
          template: '<div v-if="modelValue" data-test="verify-dialog">验证身份</div>',
        },
        CustomerHistoryDrawer: {
          props: ['modelValue', 'conversations', 'loading', 'error'],
          emits: ['update:modelValue', 'select', 'retry'],
          template: '<div v-if="modelValue" data-test="history-drawer"><button v-for="c in conversations" :key="c.id" :data-test="`history-${c.id}`" @click="$emit(`select`, c.id)">{{ c.summary }}</button></div>',
        },
      },
    },
  })
}

function streamResponse(events = []) {
  const chunks = events.map((event) => new TextEncoder().encode(`data: ${JSON.stringify(event)}\n\n`))
  let index = 0
  return {
    ok: true,
    body: {
      getReader: () => ({
        read: vi.fn(async () => {
          if (index >= chunks.length) return { done: true }
          const value = chunks[index]
          index += 1
          return { done: false, value }
        }),
      }),
    },
  }
}

describe('ChatView', () => {
  beforeEach(() => {
    vi.useFakeTimers()
    vi.setSystemTime(new Date('2026-06-04T10:00:00Z'))
    localStorage.clear()
    vi.restoreAllMocks()
  })

  afterEach(() => {
    vi.useRealTimers()
  })

  it('无客户令牌时进入全新咨询页并移除内部面板', async () => {
    localStorage.setItem('chat_customer_ref', '13800000001')
    localStorage.setItem('chat_conversation_id', 'conv-1')
    localStorage.setItem('chat_messages', JSON.stringify([{ role: 'customer', content: '旧消息' }]))

    const wrapper = mountChat()
    await flushPromises()

    expect(wrapper.text()).toContain('您好，请问有什么可以帮您？')
    expect(wrapper.text()).toContain('查订单')
    expect(wrapper.text()).not.toContain('旧消息')
    expect(wrapper.text()).not.toContain('服务上下文')
    expect(wrapper.find('[data-test="customer-ref-input"]').exists()).toBe(false)
    expect(localStorage.getItem('chat_messages')).toBeNull()
  })

  it('最近会话在两小时内时自动续聊', async () => {
    localStorage.setItem('customer_token', 'token-1')
    localStorage.setItem('customer_masked_phone', '138****0001')
    localStorage.setItem('customer_expires_at', '2099-06-11T00:00:00Z')
    vi.stubGlobal('fetch', vi.fn()
      .mockResolvedValueOnce({
        ok: true,
        json: async () => ({ should_resume: true, conversation: { id: 'c1' } }),
      })
      .mockResolvedValueOnce({
        ok: true,
        json: async () => [{ role: 'customer', content: '继续查物流', meta: {} }],
      }))

    const wrapper = mountChat()
    await flushPromises()

    expect(wrapper.text()).toContain('继续查物流')
    expect(wrapper.text()).toContain('138****0001')
    expect(fetch).toHaveBeenCalledWith('http://localhost:8000/customer/conversations/recent', expect.objectContaining({
      headers: expect.objectContaining({ Authorization: 'Bearer token-1' }),
    }))
  })

  it('最近会话超过两小时时展示全新咨询页', async () => {
    localStorage.setItem('customer_token', 'token-1')
    localStorage.setItem('customer_masked_phone', '138****0001')
    localStorage.setItem('customer_expires_at', '2099-06-11T00:00:00Z')
    vi.stubGlobal('fetch', vi.fn(async () => ({
      ok: true,
      json: async () => ({ should_resume: false, conversation: { id: 'old' } }),
    })))

    const wrapper = mountChat()
    await flushPromises()

    expect(wrapper.text()).toContain('您好，请问有什么可以帮您？')
    expect(fetch).toHaveBeenCalledOnce()
  })

  it('点击新咨询后清空当前视图但保留账户', async () => {
    localStorage.setItem('customer_token', 'token-1')
    localStorage.setItem('customer_masked_phone', '138****0001')
    localStorage.setItem('customer_expires_at', '2099-06-11T00:00:00Z')
    vi.stubGlobal('fetch', vi.fn()
      .mockResolvedValueOnce({
        ok: true,
        json: async () => ({ should_resume: true, conversation: { id: 'c1' } }),
      })
      .mockResolvedValueOnce({
        ok: true,
        json: async () => [{ role: 'customer', content: '旧消息', meta: {} }],
      }))
    const wrapper = mountChat()
    await flushPromises()

    await wrapper.find('[data-test="new-consultation"]').trigger('click')

    expect(wrapper.text()).not.toContain('旧消息')
    expect(wrapper.text()).toContain('138****0001')
    expect(wrapper.text()).toContain('您好，请问有什么可以帮您？')
  })

  it('未登录打开历史时要求验证身份', async () => {
    const wrapper = mountChat()
    await flushPromises()

    await wrapper.find('[data-test="history-open"]').trigger('click')

    expect(wrapper.find('[data-test="verify-dialog"]').exists()).toBe(true)
  })

  it('发送后处理身份验证要求事件', async () => {
    vi.stubGlobal('fetch', vi.fn(async () => streamResponse([
      { type: 'identity_required', content: '请先完成客户身份验证。' },
      { type: 'done' },
    ])))
    const wrapper = mountChat()
    await flushPromises()

    wrapper.vm.input = '查询订单 20260531002'
    await wrapper.vm.send()
    await flushPromises()

    expect(wrapper.text()).toContain('请先完成客户身份验证。')
    expect(wrapper.find('[data-test="verify-dialog"]').exists()).toBe(true)
  })
})
