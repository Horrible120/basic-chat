import { computed, nextTick, reactive, ref } from 'vue'

export function useChat() {
  const nickname = ref('')
  const messages = ref([])
  const onlineCount = ref(0)
  const members = ref([])
  const status = ref('idle')
  const error = ref('')
  const socket = ref(null)
  const userId = ref('')

  const agent = reactive({ name: '小深', online: false, demo: false, allowWrite: true, maxWorkers: 3 })
  const agentMessages = ref([])
  const agentDraft = ref('')
  const agentError = ref('')
  const tasks = reactive({})
  const streaming = reactive({})

  const statusLabel = computed(() => ({
    idle: '尚未加入', connecting: '连接中…', connected: '在线', disconnected: '已断开',
  }[status.value] || status.value))

  const taskList = computed(() => Object.values(tasks).sort((a, b) => (b.createdAt || '').localeCompare(a.createdAt || '')))
  const activeTasks = computed(() => taskList.value.filter((task) => task.status === 'queued' || task.status === 'running'))
  const roomStreams = computed(() => Object.entries(streaming)
    .filter(([, item]) => item.channel === 'room' && !item.taskId)
    .map(([id, item]) => ({ id, content: item.content })))
  const agentStreams = computed(() => Object.entries(streaming)
    .filter(([, item]) => item.channel === 'dm' && !item.taskId)
    .map(([id, item]) => ({ id, content: item.content })))

  function scrollTo(selector) {
    nextTick(() => {
      const element = document.querySelector(selector)
      if (element) element.scrollTop = element.scrollHeight
    })
  }

  function resetAgentState() {
    for (const key of Object.keys(tasks)) delete tasks[key]
    for (const key of Object.keys(streaming)) delete streaming[key]
    agentMessages.value = []
    agentError.value = ''
  }

  function pushAgentMessage(message) {
    if (message.id && agentMessages.value.some((item) => item.id === message.id)) return
    agentMessages.value.push(message)
    scrollTo('.agent-messages')
  }

  function handlePacket(packet) {
    if (packet.type === 'ready') {
      userId.value = packet.userId
      onlineCount.value = packet.onlineCount
      members.value = Array.isArray(packet.members) ? packet.members : []
      if (packet.agent) Object.assign(agent, packet.agent)
    } else if (packet.type === 'presence') {
      onlineCount.value = packet.onlineCount
      members.value = Array.isArray(packet.members) ? packet.members : []
    } else if (packet.type === 'chat') {
      messages.value.push(packet)
      scrollTo('.messages')
    } else if (packet.type === 'agent.history') {
      agentMessages.value = (packet.messages || []).map((item) => ({
        id: item.id, role: item.role, content: item.content, timestamp: item.timestamp,
      }))
      scrollTo('.agent-messages')
    } else if (packet.type === 'agent.message') {
      pushAgentMessage({
        id: packet.messageId || packet.id,
        role: packet.role || 'user',
        content: packet.content,
        timestamp: packet.timestamp,
      })
    } else if (packet.type === 'agent.delta') {
      const entry = streaming[packet.messageId] || (streaming[packet.messageId] = {
        content: '', channel: packet.channel, taskId: packet.taskId || null,
      })
      entry.content += packet.content
      if (packet.taskId && tasks[packet.taskId]) tasks[packet.taskId].output = entry.content
      if (!packet.taskId) scrollTo(packet.channel === 'room' ? '.messages' : '.agent-messages')
    } else if (packet.type === 'agent.done') {
      if (packet.channel === 'room') {
        messages.value.push({
          id: packet.messageId || packet.id,
          messageId: packet.messageId || packet.id,
          userId: packet.userId || 'agent',
          nickname: packet.nickname || agent.name,
          content: packet.content,
          timestamp: packet.timestamp,
          isAgent: true,
        })
        scrollTo('.messages')
      } else {
        pushAgentMessage({
          id: packet.messageId || packet.id,
          role: 'agent',
          content: packet.content,
          timestamp: packet.timestamp,
          taskId: packet.taskId || null,
        })
      }
      if (packet.messageId) delete streaming[packet.messageId]
      if (packet.taskId && tasks[packet.taskId]) tasks[packet.taskId].output = packet.content
    } else if (packet.type === 'agent.state') {
      const task = tasks[packet.taskId] || (tasks[packet.taskId] = { taskId: packet.taskId, traces: [] })
      Object.assign(task, packet)
      if (!task.traces) task.traces = []
    } else if (packet.type === 'agent.trace') {
      const task = tasks[packet.taskId]
      if (task) {
        task.traces = [...(task.traces || []), { step: packet.step, detail: packet.detail, timestamp: packet.timestamp }].slice(-30)
      }
    } else if (packet.type === 'agent.error') {
      agentError.value = packet.message || '智能体处理失败'
    } else if (packet.type === 'error') {
      error.value = packet.message || '消息发送失败'
    }
  }

  function connect(name = nickname.value) {
    const cleanName = name.trim()
    error.value = ''
    if (!cleanName) { error.value = '请输入昵称'; return false }
    nickname.value = cleanName
    status.value = 'connecting'
    resetAgentState()
    const scheme = window.location.protocol === 'https:' ? 'wss' : 'ws'
    const ws = new WebSocket(`${scheme}://${window.location.host}/ws?nickname=${encodeURIComponent(cleanName)}`)
    socket.value = ws
    ws.addEventListener('open', () => { status.value = 'connected' })
    ws.addEventListener('message', (event) => {
      try { handlePacket(JSON.parse(event.data)) } catch { /* 忽略无法解析的包 */ }
    })
    ws.addEventListener('close', () => { status.value = 'disconnected'; socket.value = null; members.value = [] })
    ws.addEventListener('error', () => { error.value = '连接失败，请检查后端服务'; status.value = 'disconnected' })
    return true
  }

  function send(content) {
    const text = content.trim()
    if (!text || !socket.value || socket.value.readyState !== WebSocket.OPEN) return false
    socket.value.send(JSON.stringify({ type: 'chat', content: text }))
    return true
  }

  function sendAgent(content) {
    const text = content.trim()
    if (!text) return false
    if (!socket.value || socket.value.readyState !== WebSocket.OPEN) {
      agentError.value = '连接已断开，请先重新连接'
      return false
    }
    agentError.value = ''
    socket.value.send(JSON.stringify({ type: 'agent.dm', content: text }))
    return true
  }

  function stopTask(taskId) {
    if (!socket.value || socket.value.readyState !== WebSocket.OPEN) return false
    socket.value.send(JSON.stringify({ type: 'agent.stop', taskId }))
    return true
  }

  function disconnect() { socket.value?.close(); socket.value = null; status.value = 'disconnected' }

  return {
    nickname, messages, onlineCount, members, status, statusLabel, error, userId,
    agent, agentMessages, agentDraft, agentError, tasks, taskList, activeTasks,
    roomStreams, agentStreams,
    connect, send, sendAgent, stopTask, disconnect,
  }
}
