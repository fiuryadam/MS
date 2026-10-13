import { PUBLIC_THREAD } from '../hooks/useChat.js'

function UserListItem({
  userId,
  status,
  unreadCount,
  activeThread,
  setActiveThread,
}) {
  const label =
    unreadCount > 0
      ? `${unreadCount} nepřečtených zpráv`
      : status === 'online'
        ? 'Online'
        : 'Offline'

  return (
    <li>
      <button
        type="button"
        className={
          activeThread === userId
            ? 'user-list__item user-list__item--active'
            : 'user-list__item'
        }
        onClick={() => setActiveThread(userId)}
      >
        <span
          className={`presence presence--${status}`}
          title={status}
          aria-hidden
        />
        <span className="user-list__name">{userId}</span>
        {unreadCount > 0 && (
          <span className="user-list__badge" aria-label={label}>
            {unreadCount > 99 ? '99+' : unreadCount}
          </span>
        )}
      </button>
    </li>
  )
}

function UserSection({ title, users, unreadByUser, activeThread, setActiveThread }) {
  if (users.length === 0) return null

  return (
    <>
      {title && <h3 className="user-list__section">{title}</h3>}
      <ul className="user-list">
        {users.map(([userId, status]) => (
          <UserListItem
            key={userId}
            userId={userId}
            status={status}
            unreadCount={unreadByUser[userId]?.count ?? 0}
            activeThread={activeThread}
            setActiveThread={setActiveThread}
          />
        ))}
      </ul>
    </>
  )
}

export function Sidebar({
  activeThread,
  setActiveThread,
  userListSections,
  unreadByUser,
}) {
  const { unreadUsers, restOnline, restOffline } = userListSections
  const hasAnyUsers =
    unreadUsers.length > 0 || restOnline.length > 0 || restOffline.length > 0

  return (
    <aside className="sidebar">
      <h2>Konverzace</h2>
      <ul className="user-list">
        <li>
          <button
            type="button"
            className={
              activeThread === PUBLIC_THREAD
                ? 'user-list__item user-list__item--active'
                : 'user-list__item'
            }
            onClick={() => setActiveThread(PUBLIC_THREAD)}
          >
            Veřejný chat
          </button>
        </li>
      </ul>

      <h2>Uživatelé</h2>
      {!hasAnyUsers && (
        <p className="user-list__empty">Zatím žádní uživatelé</p>
      )}
      <UserSection
        users={unreadUsers}
        unreadByUser={unreadByUser}
        activeThread={activeThread}
        setActiveThread={setActiveThread}
      />
      <UserSection
        title="Online"
        users={restOnline}
        unreadByUser={unreadByUser}
        activeThread={activeThread}
        setActiveThread={setActiveThread}
      />
      <UserSection
        title="Offline"
        users={restOffline}
        unreadByUser={unreadByUser}
        activeThread={activeThread}
        setActiveThread={setActiveThread}
      />
    </aside>
  )
}
