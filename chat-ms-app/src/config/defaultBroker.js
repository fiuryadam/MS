export function getDefaultBroker() {
  return {
    host: import.meta.env.VITE_MQTT_HOST ?? 'localhost',
    port: import.meta.env.VITE_MQTT_PORT ?? '9999',
    path: import.meta.env.VITE_MQTT_PATH ?? '/mqtt',
    mqttUser: import.meta.env.VITE_MQTT_USER ?? '',
    mqttPassword: import.meta.env.VITE_MQTT_PASSWORD ?? '',
  }
}
