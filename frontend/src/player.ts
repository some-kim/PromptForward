const PLAYER_ID_KEY = 'promptforward.playerId'
const DISPLAY_NAME_KEY = 'promptforward.displayName'

export function getPlayerId(): string {
  const stored = localStorage.getItem(PLAYER_ID_KEY)
  if (stored) return stored

  const playerId = crypto.randomUUID()
  localStorage.setItem(PLAYER_ID_KEY, playerId)
  return playerId
}

export function getDisplayName(): string {
  return localStorage.getItem(DISPLAY_NAME_KEY) ?? ''
}

export function setDisplayName(name: string): void {
  localStorage.setItem(DISPLAY_NAME_KEY, name)
}
