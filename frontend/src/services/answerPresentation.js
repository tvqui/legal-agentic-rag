// Presentation only: never rewrite legal sentences or detach source markers.
export function answerBlocks(content = '') {
  const blocks = []
  for (const paragraph of content.replace(/\r\n?/g, '\n').split(/\n\s*\n/)) {
    for (const line of paragraph.split('\n')) {
      if (!line.trim()) continue
      const bullet = line.match(/^\s*[-*•]\s+(.+)$/)
      const previous = blocks.at(-1)
      if (bullet) {
        if (previous?.kind === 'list') previous.items.push(bullet[1])
        else blocks.push({ kind: 'list', items: [bullet[1]] })
      } else {
        blocks.push({ kind: 'paragraph', text: line })
      }
    }
  }
  return blocks
}

export function noticeGroups(message) {
  const notices = [...new Set([...(message.limitations || []), ...(message.warnings || [])])]
  const important = []
  const details = []
  for (const text of notices) {
    // Operational codes remain available for debugging, outside the answer.
    // Legal limits and unknown prose are never silently discarded.
    if (/^[A-Z][A-Z_0-9]+(?::|$)/.test(text)) details.push(text)
    else important.push(text)
  }
  return { important, details }
}
