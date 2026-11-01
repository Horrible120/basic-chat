import { computed, nextTick, ref } from 'vue'

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
      else if (packet.type === 'chat') { messages.value.push(packet); nextTick(() => document.querySelector('.messages')?.scrollTo({ top: 999999, behavior: 'smooth' })) }
      else if (packet.type === 'error') error.value = packet.message || '消息发送失败'
    })
    ws.addEventListener('close', () => { status.value = 'disconnected'; socket.value = null })
    ws.addEventListener('error', () => { error.value = '连接失败，请检查后端服务'; status.value = 'disconnected' })
    return true
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
