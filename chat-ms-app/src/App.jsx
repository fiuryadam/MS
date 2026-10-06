import { useState } from 'react'
import './App.css'
import { ChatScreen } from './components/ChatScreen.jsx'
import { LoginScreen } from './components/LoginScreen.jsx'
import { SettingsScreen } from './components/SettingsScreen.jsx'
import { useChat } from './hooks/useChat.js'

function App() {
  const chat = useChat()
  const [tab, setTab] = useState('chat')

  return (
    <>
      <nav className="app-tabs" aria-label="Hlavní navigace">
        <button
          type="button"
          className={tab === 'chat' ? 'app-tabs__tab is-active' : 'app-tabs__tab'}
          onClick={() => setTab('chat')}
        >
          Chat
        </button>
        <button
          type="button"
          className={
            tab === 'settings' ? 'app-tabs__tab is-active' : 'app-tabs__tab'
          }
          onClick={() => setTab('settings')}
        >
          Nastavení
        </button>
      </nav>

      {tab === 'settings' ? (
        <SettingsScreen
          form={chat.form}
          connectionState={chat.connectionState}
          updateField={chat.updateField}
          setAclMode={chat.setAclMode}
          setUseSsl={chat.setUseSsl}
        />
      ) : chat.chatOpen ? (
        <ChatScreen {...chat} />
      ) : (
        <LoginScreen
          form={chat.form}
          connectionState={chat.connectionState}
          connectionError={chat.connectionError}
          handleConnect={chat.handleConnect}
          updateField={chat.updateField}
        />
      )}
    </>
  )
}

export default App
