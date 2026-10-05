const BROKER_KEY = 'chatms.broker'

export function loadBrokerSettings() {
  try {
    const raw = localStorage.getItem(BROKER_KEY)
    if (!raw) return null
    const parsed = JSON.parse(raw)
    if (!parsed || typeof parsed !== 'object') return null
    return {
      host: typeof parsed.host === 'string' ? parsed.host : undefined,
      port: typeof parsed.port === 'string' ? parsed.port : undefined,
      path: typeof parsed.path === 'string' ? parsed.path : undefined,
      aclMode: parsed.aclMode === 'username' ? 'username' : 'clientId',
    }
  } catch {
    return null
  }
}

export function saveBrokerSettings({ host, port, path, aclMode }) {
  localStorage.setItem(
    BROKER_KEY,
    JSON.stringify({
      host,
      port,
      path,
      aclMode: aclMode === 'username' ? 'username' : 'clientId',
    }),
  )
}
