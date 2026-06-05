import { apiUrl } from './client'

export async function chatStream({ conversationId, customerRef, message, token }, onEvent) {
  const headers = { 'Content-Type': 'application/json' }
  if (token) headers.Authorization = `Bearer ${token}`
  const resp = await fetch(apiUrl('/chat'), {
    method: 'POST',
    headers,
    body: JSON.stringify({
      conversation_id: conversationId || null,
      customer_ref: customerRef,
      message,
    }),
  })
  if (!resp.ok) {
    const detail = await resp.json().catch(() => ({}))
    throw new Error(detail.detail || `请求失败 ${resp.status}`)
  }
  const reader = resp.body.getReader()
  const decoder = new TextDecoder()
  let buf = ''
  while (true) {
    const { done, value } = await reader.read()
    if (done) break
    buf += decoder.decode(value, { stream: true })
    const parts = buf.split('\n\n')
    buf = parts.pop()
    for (const part of parts) {
      const line = part.trim()
      if (line.startsWith('data:')) {
        const json = line.slice(5).trim()
        try {
          onEvent(JSON.parse(json))
        } catch {
          /* 忽略解析失败的分片 */
        }
      }
    }
  }
}
