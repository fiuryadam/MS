import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import {
  MAX_ATTEMPTS_BEFORE_ALL_OFFLINE,
} from '../config/offlineAgent.js'
import {
  loadBrokerSettings,
  saveBrokerSettings,
} from '../brokerSettings.js'
import { getDefaultBroker } from '../config/defaultBroker.js'
import { MqttChatService } from '../mqtt/MqttChatService.js'
import {
  clearSession,
  loadSession,
  resolveChatIdentity,
  saveSession,
} from '../session.js'

export const PUBLIC_THREAD = '__public__'

function threadKeyForMessage(msg) {
  if (msg.channel === 'public') return PUBLIC_THREAD
  return msg.peerId
}

function messageDedupKey(msg) {
  return `${msg.channel}|${msg.senderId}|${msg.timestamp ?? ''}|${msg.text}`
}

function buildConnectPayload(config) {
  const mqttUser = (config.mqttUser ?? '').trim()
  const loginIdentity = (config.identity ?? '').trim()
  const aclMode = config.aclMode === 'username' ? 'username' : 'clientId'
  const useSSL =
    typeof config.useSSL === 'boolean' ? config.useSSL : true

  return {
    host: config.host.trim(),
    port: config.port.trim(),
    path: (config.path ?? '').trim() || '/mqtt',
    mqttUser,
    mqttPassword: config.mqttPassword,
    identity: resolveChatIdentity({ ...config, mqttUser, identity: loginIdentity, aclMode }),
    aclMode,
    loginIdentity,
    useSSL,
  }
}

function appendLocalMessage(setMessages, msg) {
  setMessages((prev) => {
    const key = messageDedupKey(msg)
    if (prev.some((m) => messageDedupKey(m) === key)) return prev
    return [...prev, msg]
  })
}

export function useChat() {
  const service = useMemo(() => new MqttChatService(), [])

  const [form, setForm] = useState(() => {
    const session = loadSession()
    const defaults = getDefaultBroker()
    const broker = loadBrokerSettings()
    const useSSL =
      broker?.useSSL ??
      (typeof session?.useSSL === 'boolean' ? session.useSSL : defaults.useSSL)
    return {
      identity: session?.loginIdentity ?? session?.identity ?? '',
      host: broker?.host ?? session?.host ?? defaults.host,
      port: broker?.port ?? session?.port ?? defaults.port,
      path: broker?.path ?? session?.path ?? defaults.path,
      mqttUser: session?.mqttUser ?? defaults.mqttUser,
      mqttPassword: session?.mqttPassword ?? defaults.mqttPassword,
      aclMode:
        broker?.aclMode ??
        (session?.aclMode === 'username' ? 'username' : 'clientId'),
      useSSL,
    }
  })
  const [connectionState, setConnectionState] = useState(() =>
    resolveChatIdentity(form) ? 'connecting' : 'idle',
  )
  const [connectionError, setConnectionError] = useState('')
  const [reconnectAttempt, setReconnectAttempt] = useState(0)
  const [queueSize, setQueueSize] = useState(0)
  const [identity, setIdentity] = useState(() => {
    const session = loadSession()
    return session ? resolveChatIdentity(session) : ''
  })
  const [presence, setPresence] = useState({})
  const [unreadByUser, setUnreadByUser] = useState({})
  const [messages, setMessages] = useState([])
  const [activeThread, setActiveThreadState] = useState(PUBLIC_THREAD)
  const [draft, setDraft] = useState('')
  const messageListRef = useRef(null)
  const connectConfigRef = useRef(null)
  const activeThreadRef = useRef(PUBLIC_THREAD)
  const identityRef = useRef('')
  const connectionStateRef = useRef('idle')
  const presenceLiveRef = useRef(true)

  useEffect(() => {
    activeThreadRef.current = activeThread
  }, [activeThread])

  useEffect(() => {
    identityRef.current = identity
  }, [identity])

  useEffect(() => {
    connectionStateRef.current = connectionState
  }, [connectionState])

  useEffect(() => {
    const unsubConnection = service.subscribe('connection', (event) => {
      if (event.status === 'connected') {
        setConnectionState('connected')
        setConnectionError('')
        setReconnectAttempt(0)
        presenceLiveRef.current = true
        if (connectConfigRef.current) {
          saveSession(connectConfigRef.current)
        }
      } else if (event.status === 'failed') {
        setConnectionState('failed')
        setConnectionError(event.error ?? 'Připojení selhalo')
      } else if (event.status === 'disconnected') {
        setConnectionState('idle')
        setConnectionError('')
        setReconnectAttempt(0)
        setQueueSize(0)
        presenceLiveRef.current = true
        setIdentity('')
        setPresence({})
        setUnreadByUser({})
        setMessages([])
        setActiveThreadState(PUBLIC_THREAD)
      } else if (event.status === 'reconnecting') {
        setConnectionState('reconnecting')
        setReconnectAttempt(event.attempt ?? 0)
        presenceLiveRef.current = false
        setConnectionError(
          event.error ?? 'Spojení bylo přerušeno, obnovuji…',
        )
      } else if (event.status === 'offline') {
        setConnectionState('offline')
        presenceLiveRef.current = false
      }
    })

    const unsubRoster = service.subscribe('roster', ({ presence: roster, allOffline }) => {
      if (allOffline) {
        setPresence((prev) => {
          const next = { ...prev, ...roster }
          for (const userId of Object.keys(next)) {
            if (userId !== identityRef.current) {
              next[userId] = 'offline'
            }
          }
          return next
        })
        return
      }

      setPresence((prev) => ({ ...prev, ...roster }))
    })

    const unsubPresence = service.subscribe('presence', ({ userId, status }) => {
      if (!presenceLiveRef.current) return
      setPresence((prev) => ({ ...prev, [userId]: status }))
    })

    const unsubQueue = service.subscribe('queue', (event) => {
      if (typeof event.size === 'number') {
        setQueueSize(event.size)
      }
    })

    const unsubMessage = service.subscribe('message', (msg) => {
      setMessages((prev) => {
        const key = messageDedupKey(msg)
        if (prev.some((m) => messageDedupKey(m) === key)) return prev
        return [...prev, msg]
      })

      if (msg.channel !== 'private') return
      const peerId = msg.peerId
      if (!peerId || peerId === identityRef.current) return
      if (peerId === activeThreadRef.current) return

      const lastAt = msg.timestamp ?? Math.floor(Date.now() / 1000)
      setUnreadByUser((prev) => {
        const existing = prev[peerId]
        return {
          ...prev,
          [peerId]: {
            count: (existing?.count ?? 0) + 1,
            lastAt,
          },
        }
      })
      setPresence((prev) =>
        prev[peerId] ? prev : { ...prev, [peerId]: 'offline' },
      )
    })

    return () => {
      unsubConnection()
      unsubRoster()
      unsubPresence()
      unsubQueue()
      unsubMessage()
    }
  }, [service])

  const visibleMessages = useMemo(() => {
    return messages.filter((msg) => threadKeyForMessage(msg) === activeThread)
  }, [messages, activeThread])

  useEffect(() => {
    const el = messageListRef.current
    if (!el) return
    el.scrollTop = el.scrollHeight
  }, [visibleMessages, activeThread])

  const setActiveThread = useCallback((thread) => {
    setActiveThreadState(thread)
    if (thread !== PUBLIC_THREAD) {
      setUnreadByUser((prev) => {
        if (!prev[thread]) return prev
        const next = { ...prev }
        delete next[thread]
        return next
      })
    }
  }, [])

  const userListSections = useMemo(() => {
    const others = Object.entries(presence).filter(
      ([userId]) => userId !== identity,
    )
    const byName = ([a], [b]) => a.localeCompare(b)

    const unreadUsers = others
      .filter(([userId]) => unreadByUser[userId]?.count)
      .sort(
        (a, b) =>
          (unreadByUser[b[0]]?.lastAt ?? 0) - (unreadByUser[a[0]]?.lastAt ?? 0),
      )

    const restOnline = others
      .filter(([userId, status]) => !unreadByUser[userId] && status === 'online')
      .sort(byName)

    const restOffline = others
      .filter(([userId, status]) => !unreadByUser[userId] && status !== 'online')
      .sort(byName)

    return { unreadUsers, restOnline, restOffline }
  }, [presence, identity, unreadByUser])

  const persistBrokerFromForm = useCallback((next) => {
    saveBrokerSettings({
      host: next.host,
      port: next.port,
      path: next.path,
      aclMode: next.aclMode,
      useSSL: next.useSSL,
    })
  }, [])

  const connectWithPayload = useCallback(
    (payload) => {
      connectConfigRef.current = payload
      try {
        service.connect(payload)
      } catch (err) {
        setConnectionState('failed')
        setConnectionError(err.message ?? 'Chyba připojení')
      }
    },
    [service],
  )

  const startConnect = useCallback(
    (config) => {
      const payload = buildConnectPayload(config)
      persistBrokerFromForm(config)
      setConnectionError('')
      setConnectionState('connecting')
      setIdentity(payload.identity)
      connectWithPayload(payload)
    },
    [connectWithPayload, persistBrokerFromForm],
  )

  useEffect(() => {
    const session = loadSession()
    if (!session) return
    connectConfigRef.current = buildConnectPayload(session)
    service.connect(connectConfigRef.current)
  }, [service])

  useEffect(() => {
    const onPageHide = (event) => {
      if (event.persisted) return
      service.unload()
    }
    window.addEventListener('pagehide', onPageHide)
    return () => window.removeEventListener('pagehide', onPageHide)
  }, [service])

  const handleConnect = useCallback(
    (e) => {
      e.preventDefault()
      startConnect(form)
    },
    [form, startConnect],
  )

  const handleDisconnect = useCallback(() => {
    clearSession()
    connectConfigRef.current = null
    service.disconnect()
  }, [service])

  const handleSend = useCallback(
    (e) => {
      e.preventDefault()
      const text = draft.trim()
      if (!text) return
      const timestamp = Math.floor(Date.now() / 1000)
      const state = connectionStateRef.current
      const isLive = state === 'connected'

      try {
        if (activeThread === PUBLIC_THREAD) {
          service.sendPublic(text)
          if (!isLive) {
            appendLocalMessage(setMessages, {
              id: `local-${timestamp}-${Math.random().toString(36).slice(2)}`,
              channel: 'public',
              senderId: identity,
              timestamp,
              text,
            })
          }
        } else {
          service.sendPrivate(activeThread, text)
          appendLocalMessage(setMessages, {
            id: `local-${timestamp}-${Math.random().toString(36).slice(2)}`,
            channel: 'private',
            senderId: identity,
            peerId: activeThread,
            timestamp,
            text,
          })
        }
        setDraft('')
      } catch (err) {
        setConnectionError(err.message ?? 'Odeslání selhalo')
      }
    },
    [activeThread, draft, identity, service],
  )

  const updateField = useCallback(
    (field) => (e) => {
      const value = e.target.value
      setForm((prev) => {
        const next = { ...prev, [field]: value }
        if (
          field === 'host' ||
          field === 'port' ||
          field === 'path' ||
          field === 'useSSL'
        ) {
          persistBrokerFromForm(next)
        }
        return next
      })
    },
    [persistBrokerFromForm],
  )

  const setAclMode = useCallback(
    (aclMode) => {
      setForm((prev) => {
        const next = { ...prev, aclMode }
        persistBrokerFromForm(next)
        return next
      })
    },
    [persistBrokerFromForm],
  )

  const setUseSsl = useCallback(
    (useSSL) => {
      setForm((prev) => {
        const next = { ...prev, useSSL: Boolean(useSSL) }
        persistBrokerFromForm(next)
        return next
      })
    },
    [persistBrokerFromForm],
  )

  const chatOpen =
    connectionState === 'connected' ||
    connectionState === 'reconnecting' ||
    connectionState === 'offline'

  return {
    form,
    connectionState,
    connectionError,
    reconnectAttempt,
    maxReconnectAttempts: MAX_ATTEMPTS_BEFORE_ALL_OFFLINE,
    queueSize,
    chatOpen,
    identity,
    activeThread,
    setActiveThread,
    draft,
    setDraft,
    messageListRef,
    userListSections,
    unreadByUser,
    visibleMessages,
    handleConnect,
    handleDisconnect,
    handleSend,
    updateField,
    setAclMode,
    setUseSsl,
  }
}
