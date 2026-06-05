import { createPinia, setActivePinia } from 'pinia'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { chatStream } from '../src/api/sse'
import { useCustomerSessionStore } from '../src/stores/customerSession'

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

describe('customerSession store', () => {
  beforeEach(() => {
    setActivePinia(createPinia())
    localStorage.clear()
    vi.restoreAllMocks()
  })

  it('清理已过期客户令牌', () => {
    localStorage.setItem('customer_token', 'expired')
    localStorage.setItem('customer_masked_phone', '138****0001')
    localStorage.setItem('customer_expires_at', '2026-01-01T00:00:00Z')

    const store = useCustomerSessionStore()
    store.restore()

    expect(store.token).toBe('')
    expect(localStorage.getItem('customer_token')).toBeNull()
  })

  it('验证成功后保存客户会话信息', async () => {
    vi.stubGlobal('fetch', vi.fn(async () => ({
      ok: true,
      json: async () => ({
        access_token: 'token-1',
        masked_phone: '138****0001',
        expires_at: '2099-06-11T00:00:00Z',
      }),
    })))
    const store = useCustomerSessionStore()

    await store.verify(' 13800000001 ', ' 20260531002 ')

    expect(fetch).toHaveBeenCalledWith('http://localhost:8000/customer-auth/verify', expect.objectContaining({
      method: 'POST',
      body: JSON.stringify({ phone: '13800000001', recent_order_id: '20260531002' }),
    }))
    expect(store.isLoggedIn).toBe(true)
    expect(localStorage.getItem('customer_masked_phone')).toBe('138****0001')
  })

  it('退出时清除客户会话信息', () => {
    localStorage.setItem('customer_token', 'token-1')
    localStorage.setItem('customer_masked_phone', '138****0001')
    localStorage.setItem('customer_expires_at', '2099-06-11T00:00:00Z')
    const store = useCustomerSessionStore()
    store.restore()

    store.logout()

    expect(store.isLoggedIn).toBe(false)
    expect(localStorage.getItem('customer_expires_at')).toBeNull()
  })
})

describe('chatStream', () => {
  beforeEach(() => {
    vi.restoreAllMocks()
  })

  it('有客户令牌时发送 Authorization 头', async () => {
    vi.stubGlobal('fetch', vi.fn(async () => streamResponse([{ type: 'done' }])))
    const events = []

    await chatStream({
      conversationId: 'conv-1',
      customerRef: 'ignored',
      message: '你好',
      token: 'token-1',
    }, (event) => events.push(event))

    expect(fetch).toHaveBeenCalledWith('http://localhost:8000/chat', expect.objectContaining({
      headers: {
        'Content-Type': 'application/json',
        Authorization: 'Bearer token-1',
      },
    }))
    expect(events).toEqual([{ type: 'done' }])
  })

  it('HTTP 错误时抛出可读错误', async () => {
    vi.stubGlobal('fetch', vi.fn(async () => ({
      ok: false,
      status: 401,
      json: async () => ({ detail: '客户登录已失效' }),
    })))

    await expect(chatStream({
      conversationId: '',
      customerRef: 'anonymous-web',
      message: '你好',
      token: 'bad-token',
    }, () => {})).rejects.toThrow('客户登录已失效')
  })
})
