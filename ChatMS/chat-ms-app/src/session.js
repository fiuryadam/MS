const SESSION_KEY = 'chatms.session'

export function resolveChatIdentity(config) {
  const mqttUser = (config.mqttUser ?? '').trim()
  const identity = (config.identity ?? '').trim()
  if (config.aclMode === 'username') return mqttUser
  return identity
}

export function loadSession() {
  try {
    const raw = sessionStorage.getItem(SESSION_KEY)
    if (!raw) return null
    const parsed = JSON.parse(raw)
    if (!resolveChatIdentity(parsed)) return null
    return parsed
  } catch {
    return null
  }
}

export function saveSession(config) {
  sessionStorage.setItem(SESSION_KEY, JSON.stringify(config))
}

export function clearSession() {
  sessionStorage.removeItem(SESSION_KEY)
}
