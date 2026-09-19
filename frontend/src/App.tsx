import { useCallback, useEffect, useRef, useState } from "react";
import "./App.css";
import {
  ApiError,
  api,
  type Attempt,
  type Challenge,
  type Difficulty,
  type Game,
} from "./api";
import { GameMode } from "./components/GameMode";
import { Home } from "./components/Home";
import { LearningMode } from "./components/LearningMode";
import { LogoMark } from "./components/LogoMark";
import { pickRandom } from "./pick";
import { getProgress, recordAttempt } from "./progress";
import {
  getDifficulty,
  getDisplayName,
  getPlayerId,
  setDifficulty,
  setDisplayName,
} from "./player";

type View =
  | { name: "home" }
  | { name: "learning"; challenge: Challenge; attempt: Attempt }
  | { name: "game"; game: Game };

function gameIdFromHash(): string | null {
  const match = location.hash.match(/^#\/game\/(\w+)$/);
  return match ? match[1] : null;
}

export default function App() {
  const playerId = getPlayerId();
  const [name, setName] = useState(getDisplayName());
  const [difficulty, setLevel] = useState<Difficulty>(getDifficulty);
  const [view, setView] = useState<View>({ name: "home" });
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [invitedGameId, setInvitedGameId] = useState(gameIdFromHash);
  const [progress, setProgress] = useState(getProgress);
  const joining = useRef<string | null>(null);

  useEffect(() => {
    const onHashChange = () => setInvitedGameId(gameIdFromHash());
    addEventListener("hashchange", onHashChange);
    return () => removeEventListener("hashchange", onHashChange);
  }, []);

  useEffect(() => {
    // A ref, not state: StrictMode runs this effect twice and two joins race into a false 409.
    if (
      !invitedGameId ||
      view.name === "game" ||
      joining.current === invitedGameId
    )
      return;
    joining.current = invitedGameId;

    api
      .joinGame(invitedGameId, playerId, name || "Player")
      .then((game) => {
        setError(null);
        setView({ name: "game", game });
      })
      .catch((caught) => {
        joining.current = null;
        setError(caught instanceof ApiError ? caught.message : String(caught));
      });
  }, [invitedGameId, name, playerId, view.name]);

  const showError = useCallback((message: string) => setError(message), []);

  const scored = useCallback(
    (score: number, generations: number) =>
      setProgress(recordAttempt(score, generations)),
    [],
  );

  function changeName(next: string) {
    setName(next);
    setDisplayName(next);
  }

  function changeDifficulty(next: Difficulty) {
    setLevel(next);
    setDifficulty(next);
  }

  async function startLearning(challenge: Challenge) {
    setBusy(true);
    setError(null);
    try {
      const attempt = await api.createLearningAttempt(
        challenge.id,
        playerId,
        name || "Player",
      );
      setView({ name: "learning", challenge, attempt });
    } catch (caught) {
      setError(caught instanceof ApiError ? caught.message : String(caught));
    } finally {
      setBusy(false);
    }
  }

  async function nextLearning(current: Challenge) {
    setBusy(true);
    setError(null);
    try {
      const pool = await api.listChallenges(difficulty);
      const next = pickRandom(pool, (one) => one.id === current.id);
      if (!next) {
        setError(`No ${difficulty} targets available.`);
        return;
      }
      const attempt = await api.createLearningAttempt(
        next.id,
        playerId,
        name || "Player",
      );
      setView({ name: "learning", challenge: next, attempt });
    } catch (caught) {
      setError(caught instanceof ApiError ? caught.message : String(caught));
    } finally {
      setBusy(false);
    }
  }

  async function startBattle() {
    setBusy(true);
    setError(null);
    try {
      const game = await api.createGame(
        playerId,
        name || "Player",
        undefined,
        difficulty,
      );
      location.hash = `#/game/${game.id}`;
      setView({ name: "game", game });
    } catch (caught) {
      setError(caught instanceof ApiError ? caught.message : String(caught));
    } finally {
      setBusy(false);
    }
  }

  function exit() {
    joining.current = null;
    location.hash = "";
    setError(null);
    setView({ name: "home" });
  }

  return (
    <main>
      <header className="app-header">
        <div className="player-chip">
          <input
            value={name}
            placeholder="Player"
            aria-label="Display name"
            onChange={(event) => changeName(event.target.value)}
          />
          <span className="avatar">
            {(name || "P").slice(0, 1).toUpperCase()}
          </span>
        </div>
        <h1 className="logo">
          <LogoMark />
          <span>
            Prompt<span className="logo-accent">Forward</span>
          </span>
        </h1>
        <p>Write better prompts with fewer wasted generations.</p>
      </header>

      {view.name === "home" && (
        <Home
          key={difficulty}
          difficulty={difficulty}
          onDifficultyChange={changeDifficulty}
          busy={busy}
          onLearn={startLearning}
          onBattle={startBattle}
          onError={showError}
          progress={progress}
        />
      )}

      {view.name === "learning" && (
        <LearningMode
          key={view.attempt.id}
          challenge={view.challenge}
          attempt={view.attempt}
          busy={busy}
          onScored={scored}
          onNext={() => nextLearning(view.challenge)}
          onExit={exit}
        />
      )}

      {view.name === "game" && (
        <GameMode
          game={view.game}
          playerId={playerId}
          onScored={scored}
          onExit={exit}
        />
      )}

      {error && <p className="error">{error}</p>}
    </main>
  );
}
