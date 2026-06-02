import { mount } from '@vue/test-utils'
import { describe, it, expect } from 'vitest'
import PendingActionCard from '../src/components/PendingActionCard.vue'

const action = {
  id: 1,
  conversation_id: 'c1',
  tool_name: 'apply_refund',
  params: { order_id: 'O1', amount: 499, reason: '物流停滞' },
  created_at: '2026-06-02T00:00:00',
}

describe('PendingActionCard', () => {
  it('展示工具名与关键参数', () => {
    const w = mount(PendingActionCard, { props: { action } })
    expect(w.text()).toContain('apply_refund')
    expect(w.text()).toContain('O1')
    expect(w.text()).toContain('499')
  })

  it('点确认触发 review 事件且 approved=true', async () => {
    const w = mount(PendingActionCard, { props: { action } })
    await w.find('.btn-approve').trigger('click')
    expect(w.emitted('review')).toBeTruthy()
    expect(w.emitted('review')[0]).toEqual([{ id: 1, approved: true }])
  })

  it('点驳回触发 review 事件且 approved=false', async () => {
    const w = mount(PendingActionCard, { props: { action } })
    await w.find('.btn-reject').trigger('click')
    expect(w.emitted('review')[0]).toEqual([{ id: 1, approved: false }])
  })
})
