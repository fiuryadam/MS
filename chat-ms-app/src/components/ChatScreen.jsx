import { Sidebar } from './Sidebar.jsx'
import { MessageThread } from './MessageThread.jsx'

function connectionBanner({
  connectionState,
  reconnectAttempt,
  maxReconnectAttempts,
  queueSize,
}) {
  if (connectionState === 'connected') {
    if (queueSize > 0) {
      return (
        <p className="app__status app__status--queue" role="status">
          Ve frontě: {queueSize}{' '}
          {queueSize === 1 ? 'zpráva' : queueSize < 5 ? 'zprávy' : 'zpráv'} k
          odeslání…
        </p>
      )
    }
    return null
  }

  if (connectionState === 'reconnecting') {
    return (
      <p className="app__status app__status--reconnecting" role="status">
        Obnovuji spojení ({reconnectAttempt}/{maxReconnectAttempts})… Zprávy se
        ukládají do fronty
        {queueSize > 0 ? ` (${queueSize})` : ''}.
      </p>
    )
  }

  if (connectionState === 'offline') {
    return (
      <p className="app__status app__status--offline" role="status">
        Offline režim – spojení se nepodařilo obnovit, všichni uživatelé jsou
        offline. Zprávy se ukládají do fronty
        {queueSize > 0 ? ` (${queueSize})` : ''}.
      </p>
    )
  }

  return null
}

export function ChatScreen({
  identity,
  connectionState,
  connectionError,
  reconnectAttempt,
  maxReconnectAttempts,
  queueSize,
  activeThread,
  setActiveThread,
  userListSections,
  unreadByUser,
  visibleMessages,
  messageListRef,
  draft,
  setDraft,
  handleDisconnect,
  handleSend,
}) {
  const banner = connectionBanner({
    connectionState,
    reconnectAttempt,
    maxReconnectAttempts,
    queueSize,
  })

  return (
    <div className="app app--chat">
      <header className="app__header app__header--row">
        <div>
          <h1>ChatMS</h1>
          <p className="app__subtitle">
            Přihlášen jako <strong>{identity}</strong>
            {connectionState === 'connected' && (
              <span className="app__connection-dot app__connection-dot--online" />
            )}
            {connectionState === 'reconnecting' && (
              <span className="app__connection-dot app__connection-dot--reconnecting" />
            )}
            {connectionState === 'offline' && (
              <span className="app__connection-dot app__connection-dot--offline" />
            )}
          </p>
        </div>
        <button type="button" className="btn" onClick={handleDisconnect}>
          Odpojit
        </button>
      </header>

      {banner}

      {connectionError && connectionState !== 'connected' && (
        <p className="app__error app__error--banner" role="alert">
          {connectionError}
        </p>
      )}

      <div className="chat-layout">
        <Sidebar
          activeThread={activeThread}
          setActiveThread={setActiveThread}
          userListSections={userListSections}
          unreadByUser={unreadByUser}
        />
        <MessageThread
          activeThread={activeThread}
          identity={identity}
          visibleMessages={visibleMessages}
          messageListRef={messageListRef}
          draft={draft}
          setDraft={setDraft}
          handleSend={handleSend}
        />
      </div>
    </div>
  )
}
