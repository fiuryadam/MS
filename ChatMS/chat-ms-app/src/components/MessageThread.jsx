import { formatTimestamp } from '../mqtt/messageFormat.js'
import { PUBLIC_THREAD } from '../hooks/useChat.js'

export function MessageThread({
  activeThread,
  identity,
  visibleMessages,
  messageListRef,
  draft,
  setDraft,
  handleSend,
}) {
  const threadTitle =
    activeThread === PUBLIC_THREAD
      ? 'Veřejný chat'
      : `${activeThread}`

  return (
    <main className="thread">
      <h2 className="thread__title">{threadTitle}</h2>
      <ul className="message-list" ref={messageListRef}>
        {visibleMessages.length === 0 && (
          <li className="message-list__empty">Žádné zprávy</li>
        )}
        {visibleMessages.map((msg) => (
          <li
            key={msg.id}
            className={
              msg.senderId === identity ? 'message message--own' : 'message'
            }
          >
            <div className="message__meta">
              <span className="message__sender">{msg.senderId}</span>
              <time dateTime={msg.timestamp?.toString()}>
                {formatTimestamp(msg.timestamp)}
              </time>
            </div>
            <p className="message__text">{msg.text}</p>
          </li>
        ))}
      </ul>

      <form className="composer" onSubmit={handleSend}>
        <input
          type="text"
          value={draft}
          onChange={(e) => setDraft(e.target.value)}
          placeholder="Napište zprávu…"
          autoComplete="off"
        />
        <button type="submit" className="btn btn--primary">
          Odeslat
        </button>
      </form>
    </main>
  )
}
