<script setup>
import { computed, nextTick, ref } from 'vue'
import { useChat } from './composables/useChat'

const { nickname, messages, onlineCount, status, statusLabel, error, userId, connect, send, disconnect } = useChat()
const draft = ref('')
const joined = computed(() => status.value === 'connected' || status.value === 'connecting' || status.value === 'disconnected')

function join() { connect(nickname.value) }
function submit() { if (send(draft.value)) draft.value = ''; nextTick(() => document.querySelector('.composer textarea')?.focus()) }
function onKeydown(event) { if (event.key === 'Enter' && !event.shiftKey && !event.isComposing) { event.preventDefault(); submit() } }
function timeLabel(iso) { return new Intl.DateTimeFormat('zh-CN', { hour: '2-digit', minute: '2-digit' }).format(new Date(iso)) }
</script>

<template>
  <main class="page-shell">
    <section v-if="!joined || status === 'idle'" class="welcome-card">
      <div class="eyebrow">OPEN ROOM · 实时聊天</div>
      <h1>小小聊天室</h1>
      <p>输入一个昵称，和正在此刻在线的人聊几句。</p>
      <form class="join-form" @submit.prevent="join">
        <label for="nickname">你的昵称</label>
        <input id="nickname" v-model="nickname" maxlength="20" autofocus placeholder="例如：小雨" />
        <button type="submit">进入聊天室 <span>→</span></button>
      </form>
      <p v-if="error" class="error-text">{{ error }}</p>
    </section>

    <section v-else class="chat-card">
      <header class="chat-header">
        <div><div class="eyebrow">OPEN ROOM</div><h1>小小聊天室</h1></div>
        <div class="presence"><span :class="['status-dot', status]"></span><strong>{{ onlineCount }}</strong> 人在线</div>
      </header>
      <div class="sub-header"><span>{{ statusLabel }}</span><button v-if="status === 'disconnected'" class="link-button" @click="connect()">重新连接</button><button class="link-button leave" @click="disconnect">离开</button></div>
      <div class="messages" aria-live="polite">
        <div v-if="!messages.length" class="empty-state"><span>✦</span><p>还没有消息，先打个招呼吧。</p></div>
        <article v-for="message in messages" :key="message.id" :class="['message', { mine: message.userId === userId }]">
          <div class="message-meta"><strong>{{ message.nickname }}</strong><time>{{ timeLabel(message.timestamp) }}</time></div>
          <p>{{ message.content }}</p>
        </article>
      </div>
      <form class="composer" @submit.prevent="submit">
        <textarea v-model="draft" maxlength="2000" rows="2" placeholder="说点什么…（Enter 发送，Shift + Enter 换行）" :disabled="status !== 'connected'" @keydown="onKeydown"></textarea>
        <button type="submit" :disabled="status !== 'connected' || !draft.trim()" aria-label="发送">↑</button>
      </form>
      <p v-if="error" class="error-text composer-error">{{ error }}</p>
    </section>
  </main>
</template>
