import { useEffect, useState } from 'react'
import { ApiError, api, type Game } from '../api'
import { Scoreboard } from './Scoreboard'
import { round } from '../format'

const POLL_INTERVAL_MS = 2000

type Props = {
  game: Game
  playerId: string
  onExit: () => void
}

export function GameMode({ game: initialGame, playerId, onExit }: Props) {
  const [game, setGame] = useState(initialGame)
  const [prompt, setPrompt] = useState('')
  const [generating, setGenerating] = useState(false)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    if (game.status === 'completed') return

    const timer = setInterval(async () => {
      try {
        setGame(await api.getGame(game.id, playerId))
      } catch {
        // A failed poll is not fatal; the next one will pick the game up.
      }
    }, POLL_INTERVAL_MS)
    return () => clearInterval(timer)
  }, [game.id, game.status, playerId])

  const me = game.players.find((player) => player.userId === playerId)
  const opponent = game.players.find((player) => player.userId !== playerId)
  const hasGenerated = (me?.attempt.generations?.length ?? 0) > 0
  const joinUrl = `${location.origin}/#/game/${game.id}`

  async function generate() {
    setGenerating(true)
    setError(null)
    try {
      setGame(await api.generateGameImage(game.id, playerId, prompt))
    } catch (caught) {
      setError(caught instanceof ApiError ? caught.message : String(caught))
    } finally {
      setGenerating(false)
    }
  }

  return (
    <section className="mode">
      <header className="mode-header">
        <h2>Game Mode</h2>
        <button className="link" onClick={onExit}>
          Leave game
        </button>
      </header>

      {game.status === 'waiting' && (
        <p className="waiting">
          Waiting for an opponent. Share this link: <code>{joinUrl}</code>
        </p>
      )}

      <div className="image-row">
        <figure>
          <figcaption>Target</figcaption>
          <img src={`/api/challenges/${game.challengeId}/image`} alt="Target" />
        </figure>
      </div>

      {game.status === 'completed' ? (
        <div className="results game-results">
          {game.players.map((player) => {
            const generation = player.attempt.generations?.[0]
            return (
              <div key={player.userId} className="player-result">
                <h3>
                  {player.displayName}
                  {game.winnerUserId === player.userId && <span className="winner"> — winner</span>}
                </h3>
                {generation && <img src={generation.imageUrl} alt={`${player.displayName} result`} />}
                <Scoreboard attempt={player.attempt} showFinal />
                <p className="prompt-text">{generation?.prompt}</p>
              </div>
            )
          })}
          {game.winnerUserId === null && <p className="winner">Draw</p>}
        </div>
      ) : (
        <div className="prompt-panel">
          <p className="hint">
            One generation. Make it count.
            {opponent
              ? ` Opponent: ${opponent.attempt.status === 'submitted' ? 'finished' : 'writing…'}`
              : ''}
          </p>
          <textarea
            rows={5}
            value={prompt}
            disabled={hasGenerated}
            placeholder="Describe the target image so an image model can recreate it."
            onChange={(event) => setPrompt(event.target.value)}
          />
          <div className="actions">
            <button
              onClick={generate}
              disabled={!prompt.trim() || generating || hasGenerated || game.status !== 'active'}
            >
              {generating ? 'Generating… this takes a while' : 'Generate'}
            </button>
          </div>
          {hasGenerated && (
            <p className="hint">
              Your prompt scored {round(me?.attempt.scores?.promptQuality)}. Waiting for your opponent.
            </p>
          )}
        </div>
      )}

      {error && <p className="error">{error}</p>}
    </section>
  )
}
