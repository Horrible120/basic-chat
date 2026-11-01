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
      <div class="welcome-mark" aria-hidden="true">✳</div>
      <div class="eyebrow">A LITTLE SPACE FOR EVERYONE</div>
      <h1>相遇，从聊天开始<span>。</span></h1>
      <p>给自己起个名字，和朋友们聊聊此刻的想法。<br>也可以在对话中 @机器人，一起探索更多灵感。</p>
      <form class="join-form" @submit.prevent="join">
        <label for="nickname">你的昵称</label>
        <input id="nickname" v-model="nickname" maxlength="20" autofocus placeholder="例如：小雨" />
        <button type="submit">进入聊天室 <span>→</span></button>
      </form>
      <p v-if="error" class="error-text">{{ error }}</p>
    </section>

    <section v-else class="chat-card">
      <header class="chat-header">
        <div class="room-heading"><div class="room-icon" aria-hidden="true">✳</div><div><h1>小小聊天室</h1><div class="room-caption">一个分享想法的小空间</div></div></div>
        <div class="presence"><span :class="['status-dot', status]"></span><strong>{{ onlineCount }}</strong> 人在线</div>
      </header>
      <div class="sub-header"><span>{{ statusLabel }} · @机器人 可体验本机模拟回复</span><button v-if="status === 'disconnected'" class="link-button" @click="connect()">重新连接</button><button class="link-button leave" @click="disconnect">离开</button></div>
      <div class="messages" aria-live="polite">
        <div v-if="!messages.length" class="empty-state"><span>✦</span><p>还没有消息，先打个招呼吧。</p></div>
        <article v-for="message in messages" :key="message.id" :class="['message', { mine: message.userId === userId, bot: message.userId === 'local-demo-bot' }]">
          <div class="message-meta"><strong>{{ message.nickname }}</strong><span v-if="message.userId === 'local-demo-bot'" class="bot-badge">AI · 演示</span><time>{{ timeLabel(message.timestamp) }}</time></div>
          <details v-if="message.tool" class="bot-tool"><summary>{{ message.tool.name }} · {{ message.tool.status }}（模拟）</summary><p>{{ message.tool.result || "正在执行…" }}</p></details><p>{{ message.content }}</p>
        </article>
      </div>
      <div class="composer-area"><div class="composer-tip"><span>✧</span> 小提示：输入 <strong>@机器人</strong> 体验模拟回复</div><form class="composer" @submit.prevent="submit">
        <textarea v-model="draft" maxlength="2000" rows="2" placeholder="说点什么…输入 @机器人 加问题可体验模拟回复" :disabled="status !== 'connected'" @keydown="onKeydown"></textarea>
        <button type="submit" :disabled="status !== 'connected' || !draft.trim()" aria-label="发送">↑</button>
      </form><div class="composer-footer">Enter 发送 <span>·</span> Shift + Enter 换行</div></div>
      <p v-if="error" class="error-text composer-error">{{ error }}</p>
    </section>
  </main>
</template>
