export function SettingsScreen({
  form,
  connectionState,
  updateField,
  setAclMode,
}) {
  const useUsername = form.aclMode === 'username'
  const connected = connectionState === 'connected'

  return (
    <div className="app app--settings">
      <header className="app__header">
        <h1>Nastavení</h1>
        <p className="app__subtitle">Broker a ACL</p>
      </header>

      <div className="login-form">
        <h2 className="settings__heading">ACL</h2>
        <label className="acl-toggle">
          <input
            type="checkbox"
            checked={useUsername}
            onChange={(e) =>
              setAclMode(e.target.checked ? 'username' : 'clientId')
            }
          />
          Použít MQTT uživatele
        </label>
        <h2 className="settings__heading">Broker</h2>
        <label>
          Host
          <input
            type="text"
            value={form.host}
            onChange={updateField('host')}
            required
          />
        </label>
        <label>
          Port (WebSocket)
          <input
            type="text"
            value={form.port}
            onChange={updateField('port')}
            required
          />
        </label>
        <label>
          Cesta WS
          <input
            type="text"
            value={form.path}
            onChange={updateField('path')}
          />
        </label>

        {connected && (
          <p className="settings__note">
            Změny se projeví až po odpojení a novém připojení.
          </p>
        )}
      </div>
    </div>
  )
}
