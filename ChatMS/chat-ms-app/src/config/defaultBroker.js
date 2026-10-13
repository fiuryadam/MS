function parseUseSslEnv() {
  const raw = import.meta.env.VITE_MQTT_USE_SSL
  if (raw === undefined || raw === '') return true
  const normalized = String(raw).trim().toLowerCase()
  if (normalized === 'true' || normalized === '1' || normalized === 'yes') return true
  if (normalized === 'false' || normalized === '0' || normalized === 'no') return false
  return true
}

export function getDefaultBroker() {
  return {
    host: import.meta.env.VITE_MQTT_HOST ?? 'localhost',
    port: import.meta.env.VITE_MQTT_PORT ?? '9999',
    path: import.meta.env.VITE_MQTT_PATH ?? '/mqtt',
    mqttUser: import.meta.env.VITE_MQTT_USER ?? '',
    mqttPassword: import.meta.env.VITE_MQTT_PASSWORD ?? '',
    useSSL: parseUseSslEnv(),
  }
}
