const PREFIX = '/mschat'

export function publicPublishTopic(senderId) {
  return `${PREFIX}/all/${senderId}`
}

export function publicSubscribeFilter() {
  return `${PREFIX}/all/#`
}

export function privatePublishTopic(recipientId, senderId) {
  return `${PREFIX}/user/${recipientId}/${senderId}`
}

export function privateSubscribeFilter(identity) {
  return `${PREFIX}/user/${identity}/#`
}

export function statusTopic(userId) {
  return `${PREFIX}/status/${userId}`
}

export function statusSubscribeFilter() {
  return `${PREFIX}/status/#`
}

export function parseIncomingTopic(topic) {
  const parts = topic.split('/').filter(Boolean)
  if (parts[0] !== 'mschat') return null

  if (parts[1] === 'all' && parts.length >= 3) {
    return { kind: 'public', senderId: parts[2] }
  }

  if (parts[1] === 'user' && parts.length >= 4) {
    return {
      kind: 'private',
      recipientId: parts[2],
      senderId: parts[3],
    }
  }

  if (parts[1] === 'status' && parts.length >= 3) {
    return { kind: 'status', userId: parts[2] }
  }

  return null
}
