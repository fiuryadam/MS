import { Client, Message } from 'paho-mqtt'
import {
  MAX_ATTEMPTS_BEFORE_ALL_OFFLINE,
  PRESENCE_SNAPSHOT_MS,
  RECONNECT_INTERVAL_MS,
} from '../config/offlineAgent.js'
import { formatMessage, formatMessageWithTimestamp, parseMessage } from './messageFormat.js'
import { createQueueItem, OutboundQueue } from './outboundQueue.js'
import {
  parseIncomingTopic,
  privatePublishTopic,
  privateSubscribeFilter,
  publicPublishTopic,
  publicSubscribeFilter,
  statusSubscribeFilter,
  statusTopic,
} from './topics.js'

const CHAT_QOS = 1

export class MqttChatService {
  constructor() {
    this.client = null
    this.identity = null
    this.connected = false
    this.intentionalDisconnect = false
    this.connectConfig = null
    this.reconnectAttempt = 0
    this.reconnectTimer = null
    this.snapshotTimer = null
    this.allOfflineMode = false
    this.livePresence = {}
    this.lastKnownRoster = {}
    this.outboundQueue = new OutboundQueue()
    this._listeners = {
      message: new Set(),
      presence: new Set(),
      connection: new Set(),
      queue: new Set(),
      roster: new Set(),
    }
  }

  subscribe(event, listener) {
    if (!this._listeners[event]) {
      throw new Error(`Neznámá událost: ${event}`)
    }
    this._listeners[event].add(listener)
    return () => {
      this._listeners[event].delete(listener)
    }
  }

  _emit(event, payload) {
    for (const listener of this._listeners[event]) {
      listener(payload)
    }
  }

  _emitQueueSize() {
    this._emit('queue', { size: this.outboundQueue.size })
  }

  _copyPresence(source) {
    return { ...source }
  }

  _snapshotRoster() {
    this.lastKnownRoster = this._copyPresence(this.livePresence)
    this._emit('roster', {
      presence: this._copyPresence(this.lastKnownRoster),
      frozen: true,
    })
  }

  _startSnapshotTimer() {
    this._stopSnapshotTimer()
    this.snapshotTimer = setInterval(() => {
      if (this.connected) {
        this._snapshotRoster()
      }
    }, PRESENCE_SNAPSHOT_MS)
  }

  _stopSnapshotTimer() {
    if (this.snapshotTimer) {
      clearInterval(this.snapshotTimer)
      this.snapshotTimer = null
    }
  }

  _clearReconnectTimer() {
    if (this.reconnectTimer) {
      clearTimeout(this.reconnectTimer)
      this.reconnectTimer = null
    }
  }

  _stopReconnectLoop() {
    this._clearReconnectTimer()
    this.reconnectAttempt = 0
    this.allOfflineMode = false
  }

  connect(config) {
    const {
      host,
      port,
      path = '/mqtt',
      mqttUser,
      mqttPassword,
      identity,
      useSSL = true,
    } = config

    if (!identity?.trim()) {
      throw new Error('Identita je povinná.')
    }

    this._stopReconnectLoop()
    this.outboundQueue.clear()
    this._emitQueueSize()
    this.livePresence = {}
    this.lastKnownRoster = {}
    this.allOfflineMode = false

    if (this.client) {
      this.disconnect({ announceOffline: false, emitEvent: false })
    }

    this.connectConfig = {
      host,
      port,
      path,
      mqttUser,
      mqttPassword,
      identity: identity.trim(),
      useSSL: Boolean(useSSL),
    }
    this.identity = this.connectConfig.identity
    this.intentionalDisconnect = false

    this._establishClient({ isReconnect: false })
  }

  _establishClient({ isReconnect }) {
    const { host, port, path, mqttUser, mqttPassword } = this.connectConfig

    this.client = new Client(host, Number(port), path, this.identity)

    this.client.onConnectionLost = (response) => {
      this.connected = false
      this._stopSnapshotTimer()
      if (this.intentionalDisconnect) return
      this._beginReconnect(response.errorMessage)
    }

    this.client.onMessageArrived = (message) => {
      this._handleIncoming(message.destinationName, message.payloadString)
    }

    const will = new Message('offline')
    will.destinationName = statusTopic(this.identity)
    will.qos = CHAT_QOS
    will.retained = true

    this.client.connect({
      useSSL: Boolean(this.connectConfig.useSSL),
      userName: mqttUser,
      password: mqttPassword,
      keepAliveInterval: 30,
      cleanSession: false,
      willMessage: will,
      onSuccess: () => {
        this.connected = true
        this._stopReconnectLoop()
        this.allOfflineMode = false
        this._subscribeAll()
        this._publishStatus('online')
        this._startSnapshotTimer()
        this._snapshotRoster()
        this._flushOutboundQueue()
        this._emit('connection', {
          status: 'connected',
          isReconnect,
        })
      },
      onFailure: (err) => {
        this.connected = false
        const message = err.errorMessage ?? 'Připojení selhalo'
        if (isReconnect) {
          this._scheduleReconnectAttempt(message)
        } else {
          this._emit('connection', {
            status: 'failed',
            error: message,
          })
        }
      },
    })
  }

  _beginReconnect(errorMessage) {
    this._snapshotRoster()
    this.reconnectAttempt = 0
    this.allOfflineMode = false
    this._scheduleReconnectAttempt(errorMessage)
  }

  _scheduleReconnectAttempt(lastError) {
    this._clearReconnectTimer()
    if (this.intentionalDisconnect || !this.connectConfig) return

    this.reconnectAttempt += 1
    const attempt = this.reconnectAttempt

    this._emit('connection', {
      status: 'reconnecting',
      attempt,
      maxAttempts: MAX_ATTEMPTS_BEFORE_ALL_OFFLINE,
      error: lastError,
    })

    if (
      attempt >= MAX_ATTEMPTS_BEFORE_ALL_OFFLINE &&
      !this.allOfflineMode
    ) {
      this.allOfflineMode = true
      const offlinePresence = {}
      for (const userId of Object.keys(this.lastKnownRoster)) {
        if (userId !== this.identity) {
          offlinePresence[userId] = 'offline'
        }
      }
      this._emit('roster', {
        presence: offlinePresence,
        allOffline: true,
      })
      this._emit('connection', { status: 'offline' })
    }

    this.reconnectTimer = setTimeout(() => {
      if (this.intentionalDisconnect || !this.connectConfig) return
      try {
        if (this.client) {
          try {
            this.client.disconnect()
          } catch {}
          this.client = null
        }
        this._establishClient({ isReconnect: true })
      } catch (err) {
        this._scheduleReconnectAttempt(err.message ?? 'Reconnect selhal')
      }
    }, RECONNECT_INTERVAL_MS)
  }

  disconnect({ announceOffline = true, emitEvent = true } = {}) {
    this.intentionalDisconnect = true
    this._stopReconnectLoop()
    this._stopSnapshotTimer()
    this.outboundQueue.clear()
    this._emitQueueSize()
    this.connectConfig = null
    this.livePresence = {}
    this.lastKnownRoster = {}

    if (!this.client) {
      if (emitEvent) {
        this._emit('connection', { status: 'disconnected' })
      }
      return
    }

    if (announceOffline && this.connected) {
      this._publishStatus('offline')
    }
    try {
      this.client.disconnect()
    } catch {}
    this.connected = false
    if (emitEvent) {
      this._emit('connection', { status: 'disconnected' })
    }
    this.client = null
  }

  unload() {
    if (!this.client || !this.connected) return
    this.intentionalDisconnect = true
    this._stopReconnectLoop()
    this._publishStatus('offline')
  }

  sendPublic(text) {
    const trimmed = text?.trim()
    if (!trimmed) return

    if (this._shouldQueue()) {
      const timestamp = Math.floor(Date.now() / 1000)
      const item = createQueueItem({
        channel: 'public',
        text: trimmed,
        timestamp,
      })
      this.outboundQueue.enqueue(item)
      this._emitQueueSize()
      this._emit('queue', { item, enqueued: true })
      return
    }

    this._publishPublic(trimmed)
  }

  sendPrivate(recipientId, text) {
    const recipient = recipientId?.trim()
    if (!recipient) {
      throw new Error('Příjemce je povinný.')
    }
    const trimmed = text?.trim()
    if (!trimmed) return

    if (this._shouldQueue()) {
      const timestamp = Math.floor(Date.now() / 1000)
      const item = createQueueItem({
        channel: 'private',
        recipientId: recipient,
        text: trimmed,
        timestamp,
      })
      this.outboundQueue.enqueue(item)
      this._emitQueueSize()
      this._emit('queue', { item, enqueued: true })
      return
    }

    this._publishPrivate(recipient, trimmed)
  }

  _shouldQueue() {
    return !this.connected
  }

  _publishPublic(text, timestamp = Math.floor(Date.now() / 1000)) {
    this._publishRaw(
      publicPublishTopic(this.identity),
      formatMessageWithTimestamp(text, timestamp),
    )
  }

  _publishPrivate(recipientId, text, timestamp = Math.floor(Date.now() / 1000)) {
    this._publishRaw(
      privatePublishTopic(recipientId, this.identity),
      formatMessageWithTimestamp(text, timestamp),
    )
  }

  _flushOutboundQueue() {
    if (!this.connected) return

    for (const item of this.outboundQueue.peekAll()) {
      if (item.channel === 'public') {
        this._publishPublic(item.text, item.timestamp)
      } else if (item.channel === 'private') {
        this._publishPrivate(item.recipientId, item.text, item.timestamp)
      }
      this.outboundQueue.removeById(item.id)
    }

    this._emitQueueSize()
  }

  _subscribeAll() {
    const filters = [
      publicSubscribeFilter(),
      privateSubscribeFilter(this.identity),
      statusSubscribeFilter(),
    ]
    for (const filter of filters) {
      this.client.subscribe(filter, { qos: CHAT_QOS })
    }
  }

  _publishRaw(destinationName, payload) {
    if (!this.client || !this.connected) {
      throw new Error('Nejste připojeni k brokeru.')
    }
    const msg = new Message(payload)
    msg.destinationName = destinationName
    msg.qos = CHAT_QOS
    this.client.send(msg)
  }

  _publish(destinationName, text) {
    this._publishRaw(destinationName, formatMessage(text))
  }

  _publishStatus(value) {
    if (!this.client) return
    const msg = new Message(value)
    msg.destinationName = statusTopic(this.identity)
    msg.qos = CHAT_QOS
    msg.retained = true
    this.client.send(msg)
  }

  _handleIncoming(topic, payloadString) {
    const parsedTopic = parseIncomingTopic(topic)
    if (!parsedTopic) return

    if (parsedTopic.kind === 'status') {
      const status = payloadString.trim().toLowerCase()
      if (status === 'online' || status === 'offline') {
        if (this.connected) {
          this.livePresence[parsedTopic.userId] = status
          this.lastKnownRoster[parsedTopic.userId] = status
        }
        this._emit('presence', { userId: parsedTopic.userId, status })
      }
      return
    }

    const { timestamp, text } = parseMessage(payloadString)
    const base = {
      id: `${topic}-${timestamp ?? Date.now()}-${Math.random().toString(36).slice(2)}`,
      timestamp,
      text,
      senderId: parsedTopic.senderId,
    }

    if (parsedTopic.kind === 'public') {
      this._emit('message', { ...base, channel: 'public' })
      return
    }

    if (parsedTopic.kind === 'private') {
      this._emit('message', {
        ...base,
        channel: 'private',
        peerId: parsedTopic.senderId,
      })
    }
  }
}
