import { useEffect, useRef, useState } from 'react'
import './App.css'
import { ApiError, api, type Attempt, type Challenge, type Game } from './api'
import { GameMode } from './components/GameMode'
import { LearningMode } from './components/LearningMode'
import { getDisplayName, getPlayerId, setDisplayName } from './player'

type View =
  | { name: 'challenges' }
  | { name: 'learning'; challenge: Challenge; attempt: Attempt }
  | { name: 'game'; game: Game }

function gameIdFromHash(): string | null {
  const match = location.hash.match(/^#\/game\/(\w+)$/)
  return match ? match[1] : null
}

export default function App() {
  const playerId = getPlayerId()
  const [name, setName] = useState(getDisplayName())
  const [challenges, setChallenges] = useState<Challenge[]>([])
  const [view, setView] = useState<View>({ name: 'challenges' })
  const [error, setError] = useState<string | null>(null)
  const [busy, setBusy] = useState(false)
  const [invitedGameId, setInvitedGameId] = useState(gameIdFromHash)
  const joining = useRef<string | null>(null)

  useEffect(() => {
    const onHashChange = () => setInvitedGameId(gameIdFromHash())
    addEventListener('hashchange', onHashChange)
    return () => removeEventListener('hashchange', onHashChange)
  }, [])

  useEffect(() => {
    api.listChallenges().then(setChallenges).catch((caught) => setError(String(caught)))
  }, [])

  useEffect(() => {
    // A ref, not state: StrictMode runs this effect twice and two joins race into a false 409.
    if (!invitedGameId || view.name === 'game' || joining.current === invitedGameId) return
    joining.current = invitedGameId

    api
      .joinGame(invitedGameId, playerId, name || 'Player')
      .then((game) => {
        setError(null)
        setView({ name: 'game', game })
      })
      .catch((caught) => {
        joining.current = null
        setError(caught instanceof ApiError ? caught.message : String(caught))
      })
  }, [invitedGameId, name, playerId, view.name])

  async function startLearning(challenge: Challenge) {
    setBusy(true)
    setError(null)
    try {
      const attempt = await api.createLearningAttempt(challenge.id, playerId, name || 'Player')
      setView({ name: 'learning', challenge, attempt })
    } catch (caught) {
      setError(caught instanceof ApiError ? caught.message : String(caught))
    } finally {
      setBusy(false)
    }
  }

  async function startGame(challenge?: Challenge) {
    setBusy(true)
    setError(null)
    try {
      const game = await api.createGame(playerId, name || 'Player', challenge?.id)
      location.hash = `#/game/${game.id}`
      setView({ name: 'game', game })
    } catch (caught) {
      setError(caught instanceof ApiError ? caught.message : String(caught))
    } finally {
      setBusy(false)
    }
  }

  function exit() {
    joining.current = null
    location.hash = ''
    setView({ name: 'challenges' })
  }

  return (
    <main>
      <header className="app-header">
        <h1>PromptForward</h1>
        <p>Write better prompts with fewer wasted generations.</p>
        <label>
          Display name
          <input
            value={name}
            placeholder="Player"
            onChange={(event) => {
              setName(event.target.value)
              setDisplayName(event.target.value)
            }}
          />
        </label>
      </header>

      {view.name === 'challenges' && (
        <section>
          <div className="mode-header">
            <h2>Challenges</h2>
            <button onClick={() => startGame()} disabled={busy || challenges.length === 0}>
              Start a random game
            </button>
          </div>
          {challenges.length === 0 && <p>No challenges yet. Run the seed script to add target images.</p>}
          <ul className="challenge-grid">
            {challenges.map((challenge) => (
              <li key={challenge.id}>
                <img src={challenge.imageUrl} alt="Challenge target" />
                <div className="actions">
                  <button onClick={() => startLearning(challenge)} disabled={busy}>
                    Learn
                  </button>
                  <button onClick={() => startGame(challenge)} disabled={busy}>
                    Challenge a friend
                  </button>
                </div>
              </li>
            ))}
          </ul>
        </section>
      )}

      {view.name === 'learning' && (
        <LearningMode challenge={view.challenge} attempt={view.attempt} onExit={exit} />
      )}

      {view.name === 'game' && <GameMode game={view.game} playerId={playerId} onExit={exit} />}

      {error && <p className="error">{error}</p>}
    </main>
  )
}
