import { useCallback, useEffect, useRef, useState } from "react";
import "./App.css";
import {
  ApiError,
  api,
  type Attempt,
  type Challenge,
  type Difficulty,
  type Game,
  type Session,
  type User,
} from "./api";
import { GameMode } from "./components/GameMode";
import { Home } from "./components/Home";
import { LearningMode } from "./components/LearningMode";
import { LogoMark } from "./components/LogoMark";
import { SignIn } from "./components/SignIn";
import { TrainingLobby } from "./components/TrainingLobby";
import { Splash } from "./components/Splash";
import { pickRandom } from "./pick";
import { summarize } from "./progress";
import { getDifficulty, setDifficulty } from "./player";
import { getToken, setToken } from "./session";

type View =
  | { name: "home" }
  | { name: "train" }
  | { name: "learning"; challenge: Challenge; attempt: Attempt }
  | { name: "game"; game: Game };

function gameIdFromHash(): string | null {
  const match = location.hash.match(/^#\/game\/(\w+)$/);
  return match ? match[1] : null;
}

export default function App() {
  const [user, setUser] = useState<User | null>(null);
  const [loadingSession, setLoadingSession] = useState(
    () => getToken() !== null,
  );
  const [difficulty, setLevel] = useState<Difficulty>(getDifficulty);
  const [view, setView] = useState<View>({ name: "home" });
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [invitedGameId, setInvitedGameId] = useState(gameIdFromHash);
  const [splashDone, setSplashDone] = useState(false);
  const joining = useRef<string | null>(null);

  const playerId = user?.id ?? "";
  const name = user?.displayName ?? "";
  const progress = summarize(
    user?.progress ?? {
      xp: 0,
      attempts: 0,
      generations: 0,
      streak: 0,
      lastPlayedDay: null,
    },
  );

  // A stored token outlives a reload, so the session is restored before anything renders.
  useEffect(() => {
    if (!getToken()) return;
    api
      .me()
      .then(setUser)
      .catch(() => setToken(null))
      .finally(() => setLoadingSession(false));
  }, []);

  useEffect(() => {
    const onHashChange = () => setInvitedGameId(gameIdFromHash());
    addEventListener("hashchange", onHashChange);
    return () => removeEventListener("hashchange", onHashChange);
  }, []);

  useEffect(() => {
    // A ref, not state: StrictMode runs this effect twice and two joins race into a false 409.
    if (
      !user ||
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
  }, [invitedGameId, name, playerId, user, view.name]);

  const showError = useCallback((message: string) => setError(message), []);
  const endSplash = useCallback(() => setSplashDone(true), []);

  const scored = useCallback(
    (attemptId: string, score: number, generations: number) => {
      api
        .addProgress(attemptId, score, generations)
        .then((updated) =>
          setUser((current) =>
            current ? { ...current, progress: updated } : current,
          ),
        )
        .catch(() => undefined);
    },
    [],
  );

  function signedIn(session: Session) {
    setToken(session.token);
    setUser(session.user);
    setLoadingSession(false);
  }

  function signOut() {
    api.logOut().catch(() => undefined);
    setToken(null);
    setUser(null);
    exit();
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
    // Clear the invite id with the hash: leaving it set re-joins the game we are leaving.
    setInvitedGameId(null);
    location.hash = "";
    setError(null);
    setView({ name: "home" });
  }

  // The splash holds the first paint, then the app or the login form takes over.
  if (!splashDone || loadingSession) return <Splash onDone={endSplash} />;

  return (
    <main>
      <header className="app-header">
        {user && (
          <div className="player-chip">
            <button className="link" onClick={signOut}>
              Log out
            </button>
            <span className="player-name">{name}</span>
            <span className="avatar">
              {(name || "P").slice(0, 1).toUpperCase()}
            </span>
          </div>
        )}
        <h1 className="logo">
          <LogoMark />
          <span>
            Prompt<span className="logo-accent">Forward</span>
          </span>
        </h1>
        <p>Write better prompts with fewer wasted generations.</p>
      </header>

      {!user && <SignIn onSignedIn={signedIn} />}

      {user && view.name === "home" && (
        <Home
          busy={busy}
          onTrain={() => setView({ name: "train" })}
          onBattle={startBattle}
        />
      )}

      {user && view.name === "train" && (
        <TrainingLobby
          key={difficulty}
          difficulty={difficulty}
          onDifficultyChange={changeDifficulty}
          busy={busy}
          onStart={startLearning}
          onExit={exit}
          onError={showError}
          progress={progress}
        />
      )}

      {user && view.name === "learning" && (
        <LearningMode
          key={view.attempt.id}
          challenge={view.challenge}
          attempt={view.attempt}
          busy={busy}
          onScored={scored}
          onNext={() => nextLearning(view.challenge)}
          onExit={() => setView({ name: "train" })}
        />
      )}

      {user && view.name === "game" && (
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
