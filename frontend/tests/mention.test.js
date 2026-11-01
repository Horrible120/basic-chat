import test from 'node:test'
import assert from 'node:assert/strict'
import { insertMention } from '../src/mention.js'

test('在光标位置插入昵称并保留前后文字', () => {
  assert.deepEqual(insertMention('你好，继续聊', '小雨', 3, 3), { text: '你好，@小雨 继续聊', cursor: 7 })
})

test('替换选中文本并分隔前面的文字', () => {
  assert.deepEqual(insertMention('请问某人今天', '小明', 2, 4), { text: '请问 @小明 今天', cursor: 7 })
})

test('识别光标前的 @ 搜索词并保留其位置', async () => {
  const { mentionQuery } = await import('../src/mention.js')
  assert.deepEqual(mentionQuery('你好 @小雨', 6), { start: 3, end: 6, query: '小雨' })
  assert.equal(mentionQuery('这是邮箱 a@b.com', 11), null)
  assert.equal(mentionQuery('你好 @小雨 ', 7), null)
})
