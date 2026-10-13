export function LoginScreen({
  form,
  connectionState,
  connectionError,
  handleConnect,
  updateField,
}) {
  const useUsername = form.aclMode === 'username'
  return (
    <div className="app app--login">
      <header className="app__header">
        <h1>ChatMS</h1>
        <p className="app__subtitle">MQTT klient</p>
      </header>

      <form className="login-form" onSubmit={handleConnect}>
        <label>
          Identita (MQTT client ID)
          <input
            type="text"
            value={form.identity}
            onChange={updateField('identity')}
            placeholder="např. fiu0013"
            required={!useUsername}
            disabled={useUsername}
            autoComplete="nickname"
          />
        </label>
        {useUsername && (
          <p className="acl-toggle__hint">
            Identita se nepoužívá — v nastavení je zapnuté ACL.
          </p>
        )}

        <label>
          MQTT uživatel
          <input
            type="text"
            value={form.mqttUser}
            onChange={updateField('mqttUser')}
            placeholder="např. adam"
            required
            autoComplete="username"
          />
        </label>

        <label>
          MQTT heslo
          <input
            type="password"
            value={form.mqttPassword}
            onChange={updateField('mqttPassword')}
            required
            autoComplete="current-password"
          />
        </label>

        {connectionError && (
          <p className="app__error" role="alert">
            {connectionError}
          </p>
        )}

        <button
          type="submit"
          className="btn btn--primary"
          disabled={connectionState === 'connecting'}
        >
          {connectionState === 'connecting' ? 'Připojuji…' : 'Připojit'}
        </button>
      </form>
    </div>
  )
}
