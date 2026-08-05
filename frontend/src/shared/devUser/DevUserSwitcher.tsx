import { useDevUser } from './DevUserContext'

const ROLE_LABELS: Record<string, string> = {
  admin: 'Administrador',
  audiologist: 'Audioprotesista',
  viewer: 'Solo lectura',
}

export function DevUserSwitcher() {
  const { devUsers, currentUser, selectedUserId, status, errorMessage, selectUser } = useDevUser()

  if (status === 'loading') {
    return <p role="status">Cargando usuarios de desarrollo…</p>
  }

  if (status === 'error') {
    return <p role="alert">No se pudo cargar la lista de usuarios de desarrollo: {errorMessage}</p>
  }

  if (devUsers.length === 0) {
    return (
      <p role="alert">
        No hay usuarios de desarrollo. Ejecuta el seed:{' '}
        <code>docker compose run --rm backend python -m app.seed</code>
      </p>
    )
  }

  return (
    <div className="dev-user-switcher">
      <label htmlFor="dev-user-select">Usuario ficticio activo</label>
      <select
        id="dev-user-select"
        value={selectedUserId ?? ''}
        onChange={(event) => selectUser(event.target.value)}
      >
        {devUsers.map((user) => (
          <option key={user.id} value={user.id}>
            {user.display_name} ({ROLE_LABELS[user.role] ?? user.role})
          </option>
        ))}
      </select>
      {currentUser && (
        <p data-testid="current-user-summary">
          Actuando como <strong>{currentUser.display_name}</strong> —{' '}
          {ROLE_LABELS[currentUser.role] ?? currentUser.role} ({currentUser.email})
        </p>
      )}
    </div>
  )
}
