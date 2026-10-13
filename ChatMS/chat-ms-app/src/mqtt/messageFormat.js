export function formatMessage(text) {
  const timestamp = Math.floor(Date.now() / 1000)
  return formatMessageWithTimestamp(text, timestamp)
}

export function formatMessageWithTimestamp(text, timestamp) {
  return `${timestamp}\n${text}`
}

const TIMESTAMP_PREFIX = /^(\d{9,12})(?:\r?\n|[ \t]+)([\s\S]*)$/

export function parseMessage(payload) {
  const raw = typeof payload === 'string' ? payload : ''
  const match = raw.match(TIMESTAMP_PREFIX)
  if (!match) {
    return { timestamp: null, text: raw }
  }
  return {
    timestamp: Number(match[1]),
    text: match[2],
  }
}

export function formatTimestamp(seconds) {
  if (seconds == null) return ''
  const date = new Date(seconds * 1000)
  return date.toLocaleString()
}
