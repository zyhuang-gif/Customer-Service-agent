import { defineStore } from 'pinia'
import { api } from '../api/client'

export const useAuthStore = defineStore('auth', {
  state: () => ({
    token: localStorage.getItem('cs_token') || '',
    role: localStorage.getItem('cs_role') || '',
    displayName: localStorage.getItem('cs_name') || '',
  }),
  getters: {
    isLoggedIn: (s) => !!s.token,
  },
  actions: {
    async login(username, password) {
      const data = await api('/auth/login', { method: 'POST', body: { username, password } })
      this.token = data.access_token
      this.role = data.role
      this.displayName = data.display_name
      localStorage.setItem('cs_token', this.token)
      localStorage.setItem('cs_role', this.role)
      localStorage.setItem('cs_name', this.displayName)
    },
    logout() {
      this.token = ''
      this.role = ''
      this.displayName = ''
      localStorage.removeItem('cs_token')
      localStorage.removeItem('cs_role')
      localStorage.removeItem('cs_name')
    },
  },
})
