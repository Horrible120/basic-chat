<script setup>
import { computed, nextTick, ref } from 'vue'
import { useChat } from './composables/useChat'

const {
  nickname, messages, onlineCount, status, statusLabel, error, userId,
  agent, agentMessages, agentDraft, agentError, taskList, activeTasks,
  roomStreams, agentStreams,
  connect, send, sendAgent, stopTask, disconnect,
} = useChat()

const draft = ref('')
const joined = computed(() => status.value === 'connected' || status.value === 'connecting' || status.value === 'disconnected')

function join() { connect(nickname.value) }
function submit() { if (send(draft.value)) draft.value = ''; nextTick(() => document.querySelector('.composer textarea')?.focus()) }
function onKeydown(event) { if (event.key === 'Enter' && !event.shiftKey && !event.isComposing) { event.preventDefault(); submit() } }
function mentionAgent() {
  const marker = `@${agent.name}`
  if (!draft.value.includes(marker)) draft.value = `${marker} ${draft.value}`
  nextTick(() => document.querySelector('.composer textarea')?.focus())
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
      <div class="eyebrow">OPEN ROOM · 实时聊天</div>
      <h1>小小聊天室</h1>
      <p>输入一个昵称，和正在此刻在线的人聊几句。智能体「{{ agent.name }}」也在房间里，试试 @它。</p>
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
          <div><div class="eyebrow">OPEN ROOM</div><h1>小小聊天室</h1></div>
          <div class="presence"><span :class="['status-dot', status]"></span><strong>{{ onlineCount }}</strong> 人在线</div>
        </header>
        <div class="sub-header">
          <span>{{ statusLabel }}</span>
          <span class="agent-hint">@{{ agent.name }} 可呼叫智能体</span>
          <button v-if="status === 'disconnected'" class="link-button" @click="connect()">重新连接</button>
          <button class="link-button leave" @click="disconnect">离开</button>
        </div>
        <div class="messages" aria-live="polite">
          <div v-if="!messages.length && !roomStreams.length" class="empty-state"><span>✦</span><p>还没有消息，先打个招呼吧。</p></div>
          <article v-for="message in messages" :key="message.id" :class="['message', { mine: message.userId === userId, agent: message.isAgent }]">
            <div class="message-meta"><strong>{{ message.nickname }}</strong><time>{{ timeLabel(message.timestamp) }}</time></div>
            <p>{{ message.content }}</p>
          </article>
          <article v-for="stream in roomStreams" :key="stream.id" class="message agent streaming">
            <div class="message-meta"><strong>{{ agent.name }}</strong><span class="typing">正在输入</span></div>
            <p>{{ stream.content }}<span class="cursor">▌</span></p>
          </article>
        </div>
        <form class="composer" @submit.prevent="submit">
          <button type="button" class="mention-button" title="呼叫智能体" @click="mentionAgent">@</button>
          <textarea v-model="draft" maxlength="2000" rows="2" placeholder="说点什么…（Enter 发送，Shift + Enter 换行）" :disabled="status !== 'connected'" @keydown="onKeydown"></textarea>
          <button type="submit" :disabled="status !== 'connected' || !draft.trim()" aria-label="发送">↑</button>
        </form>
        <p v-if="error" class="error-text composer-error">{{ error }}</p>
      </section>

      <aside class="agent-card">
        <header class="agent-header">
          <div class="agent-avatar">深</div>
          <div class="agent-title">
            <strong>{{ agent.name }}</strong>
            <span>Super-agent · Router + Worker</span>
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
