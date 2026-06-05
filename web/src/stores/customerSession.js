import { defineStore } from 'pinia'
import { api } from '../api/client'

const TOKEN_KEY = 'customer_token'
const PHONE_KEY = 'customer_masked_phone'
const EXPIRES_KEY = 'customer_expires_at'

function isFuture(value) {
  const time = Date.parse(value || '')
  return Number.isFinite(time) && time > Date.now()
}

export const useCustomerSessionStore = defineStore('customerSession', {
  state: () => ({
    token: '',
    maskedPhone: '',
    expiresAt: '',
  }),
  getters: {
    isLoggedIn: (state) => !!state.token && isFuture(state.expiresAt),
  },
  actions: {
    restore() {
      this.token = localStorage.getItem(TOKEN_KEY) || ''
      this.maskedPhone = localStorage.getItem(PHONE_KEY) || ''
      this.expiresAt = localStorage.getItem(EXPIRES_KEY) || ''
      if (!this.isLoggedIn) this.logout()
    },
    async verify(phone, recentOrderId) {
      const data = await api('/customer-auth/verify', {
        method: 'POST',
        body: {
          phone: String(phone || '').trim(),
          recent_order_id: String(recentOrderId || '').trim(),
        },
      })
      this.token = data.access_token
      this.maskedPhone = data.masked_phone
      this.expiresAt = data.expires_at
      localStorage.setItem(TOKEN_KEY, this.token)
      localStorage.setItem(PHONE_KEY, this.maskedPhone)
      localStorage.setItem(EXPIRES_KEY, this.expiresAt)
    },
    logout() {
      this.token = ''
      this.maskedPhone = ''
      this.expiresAt = ''
      localStorage.removeItem(TOKEN_KEY)
      localStorage.removeItem(PHONE_KEY)
      localStorage.removeItem(EXPIRES_KEY)
    },
  },
})
