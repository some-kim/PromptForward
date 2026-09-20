import { useEffect, useState } from "react";
import { ApiError, api, type Game } from "../api";
import { Scoreboard } from "./Scoreboard";
import { Composer, SendButton } from "./Composer";
import { EcoPrompt } from "./EcoPrompt";

const POLL_INTERVAL_MS = 2000;

type Props = {
  game: Game;
  playerId: string;
  onScored: (attemptId: string, score: number, generations: number) => void;
  onExit: () => void;
};

export function GameMode({
  game: initialGame,
  playerId,
  onScored,
  onExit,
}: Props) {
  const [game, setGame] = useState(initialGame);
  const [prompt, setPrompt] = useState("");
  const [generating, setGenerating] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (game.status === "completed") return;

    const timer = setInterval(async () => {
      try {
        setGame(await api.getGame(game.id, playerId));
      } catch {
        // A failed poll is not fatal; the next one will pick the game up.
      }
    }, POLL_INTERVAL_MS);
    return () => clearInterval(timer);
  }, [game.id, game.status, playerId]);

  const me = game.players.find((player) => player.isYou);
  const opponent = game.players.find((player) => !player.isYou);
  const myGeneration = me?.attempt.generations?.[0];
  const hasGenerated = myGeneration !== undefined;
  // The image is made but scoring the prompt failed: the only action left is to score it again.
  const needsScore =
    hasGenerated && myGeneration.promptQuality === null && !generating;
  const joinUrl = `${location.origin}/#/game/${game.id}`;
  const cannotGenerate =
    generating || game.status !== "active" || !prompt.trim() || hasGenerated;

  // Reporting is keyed by attempt, so reopening a finished battle re-reports without double counting.
  useEffect(() => {
    const mine = game.players.find((player) => player.isYou);
    if (game.status !== "completed" || !mine) return;
    onScored(mine.attempt.id, mine.attempt.scores?.final ?? 0, 1);
  }, [game, onScored]);

  async function generate() {
    setGenerating(true);
    setError(null);
    try {
      setGame(
        await api.generateGameImage(
          game.id,
          playerId,
          myGeneration?.prompt ?? prompt,
        ),
      );
    } catch (caught) {
      setError(caught instanceof ApiError ? caught.message : String(caught));
    } finally {
      setGenerating(false);
    }
  }

  return (
    <section className="mode">
      <header className="mode-header">
        <h2>Prompt Royale</h2>
        <button className="link" onClick={onExit}>
          Leave game
        </button>
      </header>

      {game.status === "waiting" && (
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

      {game.status === "completed" ? (
        <div className="results game-results">
          {game.players.map((player) => {
            const generation = player.attempt.generations?.[0];
            const won = game.winner === (player.isYou ? "you" : "opponent");
            return (
              <div
                key={player.displayName}
                className={`player-result ${won ? "won" : ""}`}
              >
                <h3>
                  {player.displayName}
                  {won && <span className="winner"> — winner</span>}
                </h3>
                {generation && (
                  <img
                    src={generation.imageUrl}
                    alt={`${player.displayName} result`}
                  />
                )}
                <Scoreboard attempt={player.attempt} showFinal />
                <p className="prompt-text">{generation?.prompt}</p>
              </div>
            );
          })}
          {game.winner === "draw" && <p className="winner">Draw</p>}
        </div>
      ) : (
        <div className="prompt-panel">
          <p className="hint">
            One generation. Make it count.
            {opponent
              ? ` Opponent: ${opponent.attempt.status === "submitted" ? "finished" : "writing…"}`
              : ""}
          </p>
          <div className="composer-row">
            <Composer
              value={hasGenerated ? (myGeneration?.prompt ?? prompt) : prompt}
              disabled={hasGenerated}
              placeholder="Describe the target image so an image model can recreate it."
              onChange={setPrompt}
              onSubmit={generate}
              submitDisabled={cannotGenerate}
              actions={
                needsScore ? (
                  <button onClick={generate} disabled={generating}>
                    Score my prompt again
                  </button>
                ) : (
                  <SendButton
                    busy={generating}
                    title={generating ? "Working…" : "Generate image"}
                    disabled={cannotGenerate}
                    onClick={generate}
                  />
                )
              }
            />
            <EcoPrompt
              prompt={prompt}
              onChange={setPrompt}
              disabled={hasGenerated || generating}
            />
          </div>
          {generating && (
            <p className="hint">Generating and scoring… this can take a minute.</p>
          )}
          {needsScore ? (
            <p className="hint">
              Your image is safe, but scoring your prompt failed. Retry scoring
              — it will not use a second generation.
            </p>
          ) : (
            hasGenerated && (
              <p className="hint">
                Your image is in. Scores are revealed once your opponent
                finishes.
              </p>
            )
          )}
        </div>
      )}

      {error && <p className="error">{error}</p>}
    </section>
  );
}
