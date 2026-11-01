export function botPrompt(message) {
  const mention = /@(?:机器人|AI)(?![\w\u4e00-\u9fff])/i
  if (!mention.test(message)) return null
  return message.replace(mention, '').replace(/ {2,}/g, ' ').trim()
}

const sleep = ms => new Promise(resolve => setTimeout(resolve, ms))
// Replace this event stream with the backend adapter after the API is agreed.
export async function* mockChat(message, { signal, delay = 35 } = {}) {
  if (signal?.aborted) return
  const wantsTool = /搜索|查询|天气|工具|search|weather/i.test(message)
  if (wantsTool) {
    yield { type: 'tool_start', id: 'mock-search', name: '模拟搜索' }
    await sleep(delay * 15)
    if (signal?.aborted) return
    yield { type: 'tool_result', id: 'mock-search', success: true, result: '这是一条模拟工具结果，尚未连接真实搜索服务。' }
  }
  const answer = wantsTool ? '我已经演示了一次工具调用。目前展示的是模拟结果，等接入后端后，就可以在这里呈现真实工具的执行状态和结果。' : '你好！我是你的 AI 助手。\n\n目前这里使用的是模拟回复，聊天界面已经为后续连接大模型做好准备。你可以试着输入「搜索 Vue」，看看工具调用的展示效果。'
  for (const content of answer.match(/.{1,3}|\n/g) || []) {
    if (signal?.aborted) return
    yield { type: 'text', content }
    await sleep(delay)
  }
}


