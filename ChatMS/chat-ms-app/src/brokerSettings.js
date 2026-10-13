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
      useSSL: typeof parsed.useSSL === 'boolean' ? parsed.useSSL : undefined,
    }
  } catch {
    return null
  }
}

export function saveBrokerSettings({ host, port, path, aclMode, useSSL }) {
  const payload = {
    host,
    port,
    path,
    aclMode: aclMode === 'username' ? 'username' : 'clientId',
  }
  if (typeof useSSL === 'boolean') {
    payload.useSSL = useSSL
  }
  localStorage.setItem(BROKER_KEY, JSON.stringify(payload))
}
