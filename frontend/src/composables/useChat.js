import { computed, nextTick, ref } from 'vue'
import { botPrompt, mockChat } from '../chatService'

export function useChat() {
  const nickname = ref('')
  const messages = ref([])
  const onlineCount = ref(0)
  const status = ref('idle')
  const error = ref('')
  const socket = ref(null)
  const userId = ref('')

  const statusLabel = computed(() => ({
    idle: '尚未加入', connecting: '连接中…', connected: '在线', disconnected: '已断开',
  }[status.value] || status.value))

  function connect(name = nickname.value) {
    const cleanName = name.trim()
    error.value = ''
    if (!cleanName) { error.value = '请输入昵称'; return false }
    nickname.value = cleanName
    status.value = 'connecting'
    const scheme = window.location.protocol === 'https:' ? 'wss' : 'ws'
    const ws = new WebSocket(`${scheme}://${window.location.host}/ws?nickname=${encodeURIComponent(cleanName)}`)
    socket.value = ws
    ws.addEventListener('open', () => { status.value = 'connected' })
    ws.addEventListener('message', (event) => {
      let packet
      try { packet = JSON.parse(event.data) } catch { return }
      if (packet.type === 'ready') { userId.value = packet.userId; onlineCount.value = packet.onlineCount }
      else if (packet.type === 'presence') onlineCount.value = packet.onlineCount
      else if (packet.type === 'chat') { messages.value.push(packet); scrollToLatest(); if (packet.userId === userId.value) { const prompt = botPrompt(packet.content); if (prompt !== null) respondLocally(prompt) } }
      else if (packet.type === 'error') error.value = packet.message || '消息发送失败'
    })
    ws.addEventListener('close', () => { status.value = 'disconnected'; socket.value = null })
    ws.addEventListener('error', () => { error.value = '连接失败，请检查后端服务'; status.value = 'disconnected' })
    return true
  }

  function scrollToLatest() {
    nextTick(() => document.querySelector('.messages')?.scrollTo({ top: 999999, behavior: 'smooth' }))
  }

  // Demonstration only: real shared bot messages must come from the backend.
  async function respondLocally(prompt) {
    messages.value.push({ id: crypto.randomUUID(), userId: 'local-demo-bot', nickname: '机器人（本机演示）', timestamp: new Date().toISOString(), content: '', tool: null })
    const reply = messages.value[messages.value.length - 1]
    if (!prompt) { reply.content = '请在 @机器人 后输入你的问题。'; scrollToLatest(); return }
    try {
      for await (const event of mockChat(prompt)) {
        if (event.type === 'text') reply.content += event.content
        else if (event.type === 'tool_start') reply.tool = { name: event.name, status: '执行中', result: '' }
        else if (event.type === 'tool_result' && reply.tool) { reply.tool.status = event.success ? '已完成' : '失败'; reply.tool.result = event.result || event.error || '' }
        scrollToLatest()
      }
    } catch { reply.content += '模拟回复失败，请重试。' }
  }

  function send(content) {
    const text = content.trim()
    if (!text || !socket.value || socket.value.readyState !== WebSocket.OPEN) return false
    socket.value.send(JSON.stringify({ type: 'chat', content: text }))
    return true
  }

  function disconnect() { socket.value?.close(); socket.value = null; status.value = 'disconnected' }
  return { nickname, messages, onlineCount, status, statusLabel, error, userId, connect, send, disconnect }
}
