import test from 'node:test'
import assert from 'node:assert/strict'
import { botPrompt, mockChat } from '../src/chatService.js'

test('recognizes a robot mention and extracts the question', () => {
  assert.equal(botPrompt('@机器人 帮我搜索 Vue'), '帮我搜索 Vue')
  assert.equal(botPrompt('你好 @AI 介绍一下'), '你好 介绍一下')
  assert.equal(botPrompt('机器人你好'), null)
  assert.equal(botPrompt('@AI助手 你好'), null)
  assert.equal(botPrompt('@机器人'), '')
})

test('mock tool request emits tool events followed by an answer', async () => {
  const events = []
  for await (const event of mockChat('搜索 Vue', { delay: 0 })) events.push(event)
  assert.deepEqual(events.filter(e => e.type.startsWith('tool')).map(e => e.type), ['tool_start', 'tool_result'])
  assert.ok(events.some(e => e.type === 'text' && e.content))
})
