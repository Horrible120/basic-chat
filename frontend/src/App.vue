<script setup>
import { computed, nextTick, ref } from 'vue'
import { useChat } from './composables/useChat'
import { insertMention, mentionQuery } from './mention'

const {
  nickname, messages, onlineCount, members, status, statusLabel, error, userId,
  agent, agentMessages, agentDraft, agentError, taskList, activeTasks,
  roomStreams, agentStreams,
  connect, send, sendAgent, stopTask, disconnect,
} = useChat()

const draft = ref('')
const composerInput = ref(null)
const mentionOpen = ref(false)
const mentionRange = ref(null)
const mentionOptions = computed(() => {
  const query = (mentionRange.value?.query || '').toLowerCase()
  return [{ userId: 'agent', nickname: agent.name, isAgent: true }, ...members.value.filter(member => member.userId !== userId.value && member.nickname)]
    .filter(member => member.nickname.toLowerCase().includes(query))
})
const joined = computed(() => status.value === 'connected' || status.value === 'connecting' || status.value === 'disconnected')

function join() { connect(nickname.value) }
function submit() { if (send(draft.value)) draft.value = ''; nextTick(() => document.querySelector('.composer textarea')?.focus()) }
function onKeydown(event) { if (event.key === 'Escape' && mentionOpen.value) { mentionOpen.value = false; event.preventDefault(); return } if (event.key === 'Enter' && !event.shiftKey && !event.isComposing) { if (mentionOpen.value && mentionOptions.value.length) { event.preventDefault(); selectMention(mentionOptions.value[0]); return } event.preventDefault(); submit() } }
function updateMentionQuery(event) {
  mentionRange.value = mentionQuery(draft.value, event.target.selectionStart)
  mentionOpen.value = !!mentionRange.value
}
function openMentionMenu() {
  if (status.value !== 'connected') return
  mentionRange.value = null
  mentionOpen.value = !mentionOpen.value
}
function selectMention(member) {
  const textarea = composerInput.value
  const range = mentionRange.value
  const start = range?.start ?? textarea?.selectionStart ?? draft.value.length
  const end = range?.end ?? textarea?.selectionEnd ?? start
  const next = insertMention(draft.value, member.nickname, start, end)
  draft.value = next.text
  mentionOpen.value = false
  mentionRange.value = null
  nextTick(() => { textarea?.focus(); textarea?.setSelectionRange(next.cursor, next.cursor) })
}
function mentionPerson(name) {
  if (status.value !== 'connected' || !name) return
  const textarea = composerInput.value
  const start = textarea?.selectionStart ?? draft.value.length
  const end = textarea?.selectionEnd ?? start
  const next = insertMention(draft.value, name, start, end)
  mentionOpen.value = false
  mentionRange.value = null
  draft.value = next.text
  nextTick(() => { textarea?.focus(); textarea?.setSelectionRange(next.cursor, next.cursor) })
}
function submitAgent() {
  if (sendAgent(agentDraft.value)) agentDraft.value = ''
  nextTick(() => document.querySelector('.agent-composer textarea')?.focus())
}
function onAgentKeydown(event) { if (event.key === 'Enter' && !event.shiftKey && !event.isComposing) { event.preventDefault(); submitAgent() } }
function timeLabel(iso) { return iso ? new Intl.DateTimeFormat('zh-CN', { hour: '2-digit', minute: '2-digit' }).format(new Date(iso)) : '' }
function taskStatusLabel(value) {
  return ({ queued: '排队中', running: '执行中', done: '已完成', failed: '失败', stopped: '已停止' }[value] || value)
}
</script>

<template>
  <main class="page-shell">
    <section v-if="!joined || status === 'idle'" class="welcome-card">
      <div class="welcome-mark" aria-hidden="true">✳</div>
      <div class="eyebrow">A LITTLE SPACE FOR EVERYONE</div>
      <h1>相遇，从聊天开始<span>。</span></h1>
      <p>给自己起个名字，和朋友们聊聊此刻的想法。<br>智能体「{{ agent.name }}」也在房间里，试试 @它。</p>
      <form class="join-form" @submit.prevent="join">
        <label for="nickname">你的昵称</label>
        <input id="nickname" v-model="nickname" maxlength="20" autofocus placeholder="例如：小雨" />
        <button type="submit">进入聊天室 <span>→</span></button>
      </form>
      <p v-if="error" class="error-text">{{ error }}</p>
    </section>

    <div v-else class="workspace">
      <section class="chat-card">
        <header class="chat-header">
          <div class="room-heading"><div class="room-icon" aria-hidden="true">✳</div><div><h1>小小聊天室</h1><div class="room-caption">一个分享想法的小空间</div></div></div>
          <div class="presence"><span :class="['status-dot', status]"></span><strong>{{ onlineCount }}</strong> 人在线</div>
        </header>
        <div class="sub-header">
          <span>{{ statusLabel }}</span>
          <span class="agent-hint">输入 @ 或点击按钮选择在线成员</span>
          <button v-if="status === 'disconnected'" class="link-button" @click="connect()">重新连接</button>
          <button class="link-button leave" @click="disconnect">离开</button>
        </div>
        <div class="messages" aria-live="polite">
          <div v-if="!messages.length && !roomStreams.length" class="empty-state"><span>✦</span><p>还没有消息，先打个招呼吧。</p></div>
          <article v-for="message in messages" :key="message.id" :class="['message', { mine: message.userId === userId, agent: message.isAgent }]">
            <div class="message-meta"><button v-if="message.userId !== userId && !message.isAgent" type="button" class="mention-name" :disabled="status !== 'connected'" :aria-label="`提及 ${message.nickname}`" :title="`@${message.nickname}`" @click="mentionPerson(message.nickname)">{{ message.nickname }}</button><strong v-else>{{ message.nickname }}</strong><time>{{ timeLabel(message.timestamp) }}</time></div>
            <p>{{ message.content }}</p>
          </article>
          <article v-for="stream in roomStreams" :key="stream.id" class="message agent streaming">
            <div class="message-meta"><strong>{{ agent.name }}</strong><span class="typing">正在输入</span></div>
            <p>{{ stream.content }}<span class="cursor">▌</span></p>
          </article>
        </div>
        <form class="composer" @submit.prevent="submit">
          <div v-if="mentionOpen" class="mention-menu" role="group" aria-label="选择要提及的成员">
            <div class="mention-menu-title">提及成员</div>
            <button v-for="member in mentionOptions" :key="member.userId" type="button" class="mention-option" @mousedown.prevent @click="selectMention(member)">
              <span class="mention-avatar">{{ member.nickname.slice(0, 1) }}</span><span>{{ member.nickname }}</span><small>{{ member.isAgent ? '智能体' : '在线 · ' + member.userId.slice(0, 4) }}</small>
            </button>
            <div v-if="!mentionOptions.length" class="mention-empty">没有匹配的成员</div>
          </div>
          <button type="button" class="mention-button" title="提及成员" aria-label="提及成员" :aria-expanded="mentionOpen" @click="openMentionMenu">@</button>
          <textarea ref="composerInput" v-model="draft" maxlength="2000" rows="2" placeholder="说点什么…（Enter 发送，Shift + Enter 换行）" :disabled="status !== 'connected'" @keydown="onKeydown" @input="updateMentionQuery" @click="updateMentionQuery"></textarea>
          <button type="submit" :disabled="status !== 'connected' || !draft.trim()" aria-label="发送">↑</button>
        </form>
        <p v-if="error" class="error-text composer-error">{{ error }}</p>
      </section>

      <aside class="agent-card">
        <header class="agent-header">
          <div class="agent-avatar">深</div>
          <div class="agent-title">
            <strong>{{ agent.name }}</strong>
            <span>Super-agent · Router + {{ agent.backend === 'dsh' ? 'Harness' : 'Worker' }}</span>
          </div>
          <span :class="['status-dot', agent.online ? 'connected' : '']"></span>
        </header>

        <p v-if="agent.demo" class="agent-banner">演示模式：在项目根目录 .env 填入 LLM_API_KEY 后重启，即可启用真实模型。</p>
        <p v-else-if="activeTasks.length" class="agent-banner busy">{{ activeTasks.length }} 个任务正在后台执行，互不阻塞。</p>

        <section v-if="taskList.length" class="task-board">
          <article v-for="task in taskList" :key="task.taskId" :class="['task-card', task.status]">
            <div class="task-row">
              <span class="task-title">{{ task.title }}</span>
              <span class="task-status">{{ taskStatusLabel(task.status) }}</span>
              <button v-if="task.status === 'queued' || task.status === 'running'" class="task-stop" @click="stopTask(task.taskId)">停止</button>
            </div>
            <p v-if="task.output" class="task-output">{{ task.output }}</p>
            <details v-if="task.traces && task.traces.length" class="task-traces">
              <summary>{{ task.traces.length }} 步执行记录</summary>
              <ul>
                <li v-for="(trace, index) in task.traces" :key="index">
                  <code>{{ trace.step }}</code><span>{{ trace.detail }}</span>
                </li>
              </ul>
            </details>
          </article>
        </section>

        <div class="agent-messages" aria-live="polite">
          <div v-if="!agentMessages.length && !agentStreams.length" class="agent-empty">
            <span>✦</span>
            <p>把任务交给 {{ agent.name }}，Router 会分派给后台 Worker 并在这里汇报进度。</p>
          </div>
          <article v-for="message in agentMessages" :key="message.id" :class="['agent-message', message.role]">
            <div class="agent-message-meta">
              <strong>{{ message.role === 'agent' ? agent.name : '你' }}</strong>
              <time>{{ timeLabel(message.timestamp) }}</time>
            </div>
            <p>{{ message.content }}</p>
          </article>
          <article v-for="stream in agentStreams" :key="stream.id" class="agent-message agent streaming">
            <div class="agent-message-meta"><strong>{{ agent.name }}</strong><span class="typing">思考中</span></div>
            <p>{{ stream.content }}<span class="cursor">▌</span></p>
          </article>
        </div>

        <form class="agent-composer" @submit.prevent="submitAgent">
          <textarea v-model="agentDraft" maxlength="2000" rows="2" :disabled="status !== 'connected'" placeholder="私聊智能体，或让它改代码…" @keydown="onAgentKeydown"></textarea>
          <button type="submit" :disabled="status !== 'connected' || !agentDraft.trim()" aria-label="发送给智能体">↑</button>
        </form>
        <p v-if="agentError" class="error-text agent-error">{{ agentError }}</p>
      </aside>
    </div>
  </main>
</template>
