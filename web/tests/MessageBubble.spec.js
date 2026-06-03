import { mount } from '@vue/test-utils'
import { describe, it, expect } from 'vitest'
import MessageBubble from '../src/components/MessageBubble.vue'

describe('MessageBubble', () => {
  it('渲染客户消息内容', () => {
    const w = mount(MessageBubble, { props: { role: 'customer', content: '我的订单到哪了' } })
    expect(w.text()).toContain('我的订单到哪了')
  })

  it('AI 消息带引用出处时展示来源', () => {
    const w = mount(MessageBubble, {
      props: {
        role: 'ai',
        content: '物流停滞可申请催办',
        citations: [{ title: '物流催办政策', source: 'aftersale_policy.md' }],
      },
    })
    expect(w.text()).toContain('物流催办政策')
    expect(w.text()).toContain('aftersale_policy.md')
  })

  it('不同角色应用不同样式类', () => {
    const w = mount(MessageBubble, { props: { role: 'customer', content: 'x' } })
    expect(w.find('.bubble-customer').exists()).toBe(true)
  })

  it('客户侧处理进度不暴露内部 Agent 名称', () => {
    const w = mount(MessageBubble, {
      props: {
        role: 'ai',
        content: '退款通常需要 1-5 个工作日到账。',
        agentTrace: [
          { agent: 'CoordinatorAgent', summary: '识别为退款咨询' },
          { agent: 'KnowledgeAgent', summary: '查询退款到账规则' },
        ],
      },
    })

    expect(w.text()).toContain('处理进度')
    expect(w.text()).toContain('识别为退款咨询')
    expect(w.text()).toContain('查询退款到账规则')
    expect(w.text()).not.toContain('CoordinatorAgent')
    expect(w.text()).not.toContain('KnowledgeAgent')
  })
})
