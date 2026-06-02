import { flushPromises, mount } from '@vue/test-utils'
import { createPinia, setActivePinia } from 'pinia'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import router from '../src/router'
import DashboardView from '../src/views/DashboardView.vue'

const summary = {
  conversation_total: 25,
  status_counts: {
    ai_handling: 8,
    awaiting_confirmation: 2,
    human_handling: 5,
    resolved: 7,
    closed: 3,
  },
  pending_actions: 2,
  ai_resolution_rate: 0.4,
  handoff_rate: 0.2,
  knowledge_hit_rate: 0.75,
  knowledge_gaps: [
    { query: '预售商品能否改地址', count: 3 },
    { query: '海外仓退货时效', count: 1 },
  ],
}

describe('DashboardView', () => {
  beforeEach(() => {
    setActivePinia(createPinia())
    localStorage.clear()
    localStorage.setItem('cs_token', 'token-1')
    vi.restoreAllMocks()
  })

  it('请求 dashboard summary 时携带坐席 token', async () => {
    const fetchMock = vi.fn().mockResolvedValue({
      ok: true,
      json: async () => summary,
    })
    vi.stubGlobal('fetch', fetchMock)

    mount(DashboardView)
    await flushPromises()

    expect(fetchMock).toHaveBeenCalledWith(
      'http://localhost:8000/dashboard/summary',
      expect.objectContaining({
        method: 'GET',
        headers: expect.objectContaining({ Authorization: 'Bearer token-1' }),
      }),
    )
  })

  it('渲染核心指标、会话状态图和知识缺口列表', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue({
      ok: true,
      json: async () => summary,
    }))

    const wrapper = mount(DashboardView)
    await flushPromises()

    expect(wrapper.text()).toContain('AI独立解决率')
    expect(wrapper.text()).toContain('40.0%')
    expect(wrapper.text()).toContain('转人工率')
    expect(wrapper.text()).toContain('20.0%')
    expect(wrapper.text()).toContain('工单量')
    expect(wrapper.text()).toContain('25')
    expect(wrapper.text()).toContain('知识命中率')
    expect(wrapper.text()).toContain('75.0%')
    expect(wrapper.text()).toContain('待确认')
    expect(wrapper.text()).toContain('预售商品能否改地址')
    expect(wrapper.text()).toContain('3次')
  })

  it('没有知识缺口时展示空状态', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue({
      ok: true,
      json: async () => ({ ...summary, knowledge_gaps: [] }),
    }))

    const wrapper = mount(DashboardView)
    await flushPromises()

    expect(wrapper.text()).toContain('暂无无答案问题')
  })

  it('注册 dashboard 登录保护路由', () => {
    const route = router.getRoutes().find((item) => item.path === '/dashboard')
    expect(route).toBeTruthy()
    expect(route.meta.requiresAuth).toBe(true)
  })
})
