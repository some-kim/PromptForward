import { useCallback, useEffect, useRef, useState } from "react";
import "./App.css";
import {
  ApiError,
  api,
  type Attempt,
  type Challenge,
  type Difficulty,
  type Game,
  type ProblemSet,
  type Session,
  type User,
} from "./api";
import { Agent } from "./components/Agent";
import { Backdrop } from "./components/Backdrop";
import { GameMode } from "./components/GameMode";
import { Home } from "./components/Home";
import { LearningMode } from "./components/LearningMode";
import { LogoMark } from "./components/LogoMark";
import { ProblemList } from "./components/ProblemList";
import { SignIn } from "./components/SignIn";
import { TrainingLobby } from "./components/TrainingLobby";
import { Splash } from "./components/Splash";
import { pickRandom } from "./pick";
import { nextProblem, toChallenge } from "./problems";
import type { LearnTab } from "./components/LearnHeader";
import { summarize } from "./progress";
import { getDifficulty, setDifficulty } from "./player";
import { getToken, setToken } from "./session";

type PendingAction =
  | { kind: "browse" }
  | { kind: "learn"; challenge: Challenge }
  | { kind: "battle" };

type View =
  | { name: "home" }
  | { name: "train" }
  | { name: "problems" }
  | { name: "learning"; challenge: Challenge; attempt: Attempt }
  | { name: "game"; game: Game };

const AGENT_LINES: Record<View["name"] | "signIn", string[]> = {
  signIn: [
    "Sign in before you start so your streak, saved CO\u2082 and solved problems are kept.",
    "New here? An account is just a username and a password.",
  ],
  home: [
    "Hello. Learn works through the Problem Set skill by skill, or hands you a random target.",
    "New here? Start with the Problem Set — each problem teaches one prompt-writing habit.",
  ],
  problems: [
    "Each problem isolates one skill. Solve it by scoring 70 or better.",
    "Stuck? A weak prompt unlocks a hint; solving reveals a reference prompt.",
  ],
  train: [
    "Choose a difficulty and I will pull a random target for you.",
    "Easy is one clear subject. Hard is many subjects, odd styles, precise composition.",
  ],
  learning: [
    "Describe the target as precisely as you can, then press the arrow and I will score it.",
    "Green boxes are details you covered, red pulses are details you missed.",
    "Fewer words for the same coverage means a better efficiency score.",
  ],
  game: [
    "Same target for everyone, one image each. Best quality per token wins.",
    "Scores stay hidden until both players have finished.",
  ],
};

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
  const [problemSet, setProblemSet] = useState<ProblemSet | null>(null);
  // Set while the sign-in form is shown; remembers what the visitor was about to do.
  const [pendingAction, setPendingAction] = useState<PendingAction | null>(null);
  const joining = useRef<string | null>(null);
  // Bumped whenever the account changes so responses started under the old identity are
  // dropped instead of overwriting the new one.
  const epoch = useRef(0);

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

  // Progress on the problem set belongs to the account, so it reloads with the user and
  // after every scored attempt.
  const refreshProblems = useCallback(() => {
    const started = epoch.current;
    api
      .listProblems()
      .then((set) => {
        if (epoch.current === started) setProblemSet(set);
      })
      .catch(() => undefined);
  }, []);

  // Anonymous visitors see the problem list too, just without their own progress.
  const userId = user?.id ?? null;
  useEffect(() => {
    epoch.current += 1;
    refreshProblems();
  }, [userId, refreshProblems]);

  useEffect(() => {
    const onHashChange = () => setInvitedGameId(gameIdFromHash());
    addEventListener("hashchange", onHashChange);
    return () => removeEventListener("hashchange", onHashChange);
  }, []);

  // An invite link needs an account to join with, so it opens on the sign-in form.
  useEffect(() => {
    if (invitedGameId && !user) setPendingAction({ kind: "browse" });
  }, [invitedGameId, user]);

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

    const started = epoch.current;
    api
      .joinGame(invitedGameId, playerId, name || "Player")
      .then((game) => {
        if (epoch.current !== started) return;
        setError(null);
        setView({ name: "game", game });
      })
      .catch((caught) => {
        joining.current = null;
        setError(caught instanceof ApiError ? caught.message : String(caught));
      });
  }, [invitedGameId, name, playerId, user, view.name]);

  const showError = useCallback((message: string) => setError(message), []);
  const openLearnTab = useCallback(
    (tab: LearnTab) =>
      setView(tab === "problems" ? { name: "problems" } : { name: "train" }),
    [],
  );
  const endSplash = useCallback(() => setSplashDone(true), []);

  const scored = useCallback(
    (attemptId: string, score: number, generations: number) => {
      api
        .addProgress(attemptId, score, generations)
        .then((updated) => {
          setUser((current) =>
            current ? { ...current, progress: updated } : current,
          );
          refreshProblems();
        })
        .catch(() => undefined);
    },
    [refreshProblems],
  );

  function signedIn(session: Session) {
    setToken(session.token);
    setUser(session.user);
    setLoadingSession(false);
  }

  // Browsing is open to everyone; anything that creates an attempt needs an account first.
  // The action is replayed once the user is set so it runs with the real player id.
  useEffect(() => {
    if (!user || !pendingAction) return;
    setPendingAction(null);
    if (pendingAction.kind === "learn") void startLearningAs(pendingAction.challenge);
    if (pendingAction.kind === "battle") void startBattleAs();
    // eslint-disable-next-line react-hooks/exhaustive-deps -- runs only when the user arrives
  }, [user, pendingAction]);

  function requireUser(action: PendingAction) {
    if (user) {
      if (action.kind === "learn") void startLearningAs(action.challenge);
      if (action.kind === "battle") void startBattleAs();
    } else setPendingAction(action);
  }

  function signOut() {
    api.logOut().catch(() => undefined);
    setToken(null);
    setUser(null);
    setProblemSet(null);
    exit();
  }

  function changeDifficulty(next: Difficulty) {
    setLevel(next);
    setDifficulty(next);
  }

  function startLearning(challenge: Challenge) {
    requireUser({ kind: "learn", challenge });
  }

  async function startLearningAs(challenge: Challenge) {
    const started = epoch.current;
    setBusy(true);
    setError(null);
    try {
      const attempt = await api.createLearningAttempt(
        challenge.id,
        playerId,
        name || "Player",
      );
      if (epoch.current !== started) return;
      setView({ name: "learning", challenge, attempt });
    } catch (caught) {
      setError(caught instanceof ApiError ? caught.message : String(caught));
    } finally {
      setBusy(false);
    }
  }

  async function nextLearning(current: Challenge) {
    const started = epoch.current;
    setBusy(true);
    setError(null);
    try {
      let next: Challenge | undefined;
      if (current.problem) {
        const set = await api.listProblems();
        setProblemSet(set);
        const upcoming = nextProblem(set.problems, current.id);
        next = upcoming ? toChallenge(upcoming) : undefined;
      } else {
        const pool = await api.listChallenges(difficulty);
        next = pickRandom(pool, (one) => one.id === current.id) ?? undefined;
      }
      if (!next) {
        setError(`No ${difficulty} targets available.`);
        return;
      }
      const attempt = await api.createLearningAttempt(
        next.id,
        playerId,
        name || "Player",
      );
      if (epoch.current !== started) return;
      setView({ name: "learning", challenge: next, attempt });
    } catch (caught) {
      setError(caught instanceof ApiError ? caught.message : String(caught));
    } finally {
      setBusy(false);
    }
  }

  function startBattle() {
    requireUser({ kind: "battle" });
  }

  async function startBattleAs() {
    const started = epoch.current;
    setBusy(true);
    setError(null);
    try {
      const game = await api.createGame(
        playerId,
        name || "Player",
        undefined,
        difficulty,
      );
      if (epoch.current !== started) return;
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
    setPendingAction(null);
    setView({ name: "home" });
  }

  // The splash holds the first paint, then the app or the login form takes over.
  if (!splashDone || loadingSession)
    return (
      <>
        <Backdrop />
        <Splash onDone={endSplash} />
      </>
    );

  const signingIn = !user && pendingAction !== null;

  return (
    <>
      <Backdrop />
      <main>
        <header className="app-header">
          {user ? (
            <div className="player-chip">
              <button className="link" onClick={signOut}>
                Log out
              </button>
              <span className="player-name">{name}</span>
              <span className="avatar">
                {(name || "P").slice(0, 1).toUpperCase()}
              </span>
            </div>
          ) : (
            !signingIn && (
              <div className="player-chip">
                <button
                  className="link"
                  onClick={() => setPendingAction({ kind: "browse" })}
                >
                  Log in
                </button>
              </div>
            )
          )}
          <h1 className="logo">
            <LogoMark />
            <span>
              Prompt<span className="logo-accent">Forward</span>
            </span>
          </h1>
          <p>Write better prompts with fewer wasted generations.</p>
        </header>

        <Agent
          key={signingIn ? "signIn" : view.name}
          name="Forward"
          lines={signingIn ? AGENT_LINES.signIn : AGENT_LINES[view.name]}
        />

        {signingIn && (
          <>
            <SignIn onSignedIn={signedIn} />
            <button className="link" onClick={() => setPendingAction(null)}>
              Back
            </button>
          </>
        )}

        {!signingIn && view.name === "home" && (
          <Home
            busy={busy}
            onLearn={() => setView({ name: "problems" })}
            onBattle={startBattle}
            skills={problemSet?.skills ?? null}
          />
        )}

        {!signingIn && view.name === "problems" && (
          <ProblemList
            problemSet={problemSet}
            busy={busy}
            onStart={startLearning}
            onTab={openLearnTab}
            onExit={exit}
            progress={progress}
          />
        )}

        {!signingIn && view.name === "train" && (
          <TrainingLobby
            key={difficulty}
            difficulty={difficulty}
            onDifficultyChange={changeDifficulty}
            busy={busy}
            onStart={startLearning}
            onTab={openLearnTab}
            onExit={exit}
            onError={showError}
            progress={progress}
          />
        )}

        {user && !signingIn && view.name === "learning" && (
          <LearningMode
            key={view.attempt.id}
            challenge={view.challenge}
            attempt={view.attempt}
            busy={busy}
            onScored={scored}
            onNext={() => nextLearning(view.challenge)}
            onExit={() =>
              setView(
                view.challenge.problem ? { name: "problems" } : { name: "train" },
              )
            }
          />
        )}

        {user && !signingIn && view.name === "game" && (
          <GameMode
            game={view.game}
            playerId={playerId}
            onScored={scored}
            onExit={exit}
          />
        )}

        {error && <p className="error">{error}</p>}
      </main>
    </>
  );
}
