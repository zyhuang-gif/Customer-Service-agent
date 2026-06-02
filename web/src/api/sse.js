import { apiUrl } from './client'

export async function chatStream({ conversationId, customerRef, message }, onEvent) {
  const resp = await fetch(apiUrl('/chat'), {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      conversation_id: conversationId || null,
      customer_ref: customerRef,
      message,
    }),
  })
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
