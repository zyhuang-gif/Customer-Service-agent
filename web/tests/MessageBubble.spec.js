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
  })

  it('不同角色应用不同样式类', () => {
    const w = mount(MessageBubble, { props: { role: 'customer', content: 'x' } })
    expect(w.find('.bubble-customer').exists()).toBe(true)
  })
})
