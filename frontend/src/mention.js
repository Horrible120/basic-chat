export function insertMention(text, name, start, end) {
  const before = text.slice(0, start)
  const after = text.slice(end)
  const prefix = before && !/[\s，。！？、,.!?;；：:]$/.test(before) ? ' ' : ''
  const insertion = `${prefix}@${name} `
  return { text: before + insertion + after, cursor: before.length + insertion.length }
}


export function mentionQuery(text, cursor) {
  const before = text.slice(0, cursor)
  const match = /(?:^|[\s，。！？、,.!?;；：:])@([^\s@]*)$/.exec(before)
  if (!match) return null
  return { start: cursor - match[1].length - 1, end: cursor, query: match[1] }
}
