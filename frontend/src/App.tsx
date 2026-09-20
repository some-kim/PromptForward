import { useCallback, useEffect, useRef, useState } from "react";
import "./App.css";
import {
  ApiError,
  api,
  type Attempt,
  type Challenge,
  type Battle,
  type Difficulty,
  type ProblemSet,
  type Session,
  type User,
} from "./api";
import { Agent } from "./components/Agent";
import { Backdrop } from "./components/Backdrop";
import { BattleLobby } from "./components/BattleLobby";
import { BattleMode } from "./components/BattleMode";
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

type View =
  | { name: "home" }
  | { name: "train" }
  | { name: "problems" }
  | { name: "learning"; challenge: Challenge; attempt: Attempt }
  | { name: "lobby" }
  | { name: "game"; battle: Battle };

const AGENT_LINES: Record<View["name"] | "signedOut", string[]> = {
  signedOut: [
    "Hello. I am Forward, your prompt coach — sign in and I will walk you through it.",
    "One account keeps your streak, your saved CO\u2082, and your level.",
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
  lobby: [
    "Host a battle and read out the code, or type the code your opponent gave you.",
    "Custom battles run one to ten minutes, with two to seven images each.",
  ],
  game: [
    "Both of you prompt every image in the pool, one prompt per image.",
    "Nothing is scored on screen until the clock stops.",
  ],
};

function codeFromHash(): string | null {
  const match = location.hash.match(/^#\/battle\/([A-Za-z0-9]{6})$/);
  return match ? match[1].toUpperCase() : null;
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
  const [invitedCode, setInvitedCode] = useState(codeFromHash);
  const [splashDone, setSplashDone] = useState(false);
  const [problemSet, setProblemSet] = useState<ProblemSet | null>(null);
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

  // Progress on the problem set belongs to the account, so it reloads with the user and
  // after every scored attempt.
  const refreshProblems = useCallback(() => {
    api
      .listProblems()
      .then(setProblemSet)
      .catch(() => undefined);
  }, []);

  const userId = user?.id ?? null;
  useEffect(() => {
    if (userId) refreshProblems();
  }, [userId, refreshProblems]);

  useEffect(() => {
    const onHashChange = () => setInvitedCode(codeFromHash());
    addEventListener("hashchange", onHashChange);
    return () => removeEventListener("hashchange", onHashChange);
  }, []);

  useEffect(() => {
    // A ref, not state: StrictMode runs this effect twice and two joins race into a false 409.
    if (
      !user ||
      !invitedCode ||
      view.name === "game" ||
      joining.current === invitedCode
    )
      return;
    joining.current = invitedCode;

    api
      .joinBattle(invitedCode, playerId, name || "Player")
      .then((battle) => {
        setError(null);
        setView({ name: "game", battle });
      })
      .catch((caught) => {
        joining.current = null;
        setError(caught instanceof ApiError ? caught.message : String(caught));
      });
  }, [invitedCode, name, playerId, user, view.name]);

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
      setView({ name: "learning", challenge: next, attempt });
    } catch (caught) {
      setError(caught instanceof ApiError ? caught.message : String(caught));
    } finally {
      setBusy(false);
    }
  }

  function enterBattle(battle: Battle) {
    joining.current = battle.code;
    setInvitedCode(battle.code);
    // The hash is the invite: opening it elsewhere joins by code.
    location.hash = `#/battle/${battle.code}`;
    setError(null);
    setView({ name: "game", battle });
  }

  function openLobby() {
    joining.current = null;
    setInvitedCode(null);
    location.hash = "";
    setError(null);
    setView({ name: "lobby" });
  }

  function exit() {
    joining.current = null;
    // Clear the invite code with the hash: leaving it set re-joins the battle we are leaving.
    setInvitedCode(null);
    location.hash = "";
    setError(null);
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

  return (
    <>
      <Backdrop />
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

        <Agent
          key={user ? view.name : "signedOut"}
          name="Forward"
          lines={user ? AGENT_LINES[view.name] : AGENT_LINES.signedOut}
        />

        {!user && <SignIn onSignedIn={signedIn} />}

        {user && view.name === "home" && (
          <Home
            busy={busy}
            onLearn={() => setView({ name: "problems" })}
            onBattle={openLobby}
          />
        )}

        {user && view.name === "problems" && (
          <ProblemList
            problemSet={problemSet}
            busy={busy}
            onStart={startLearning}
            onTab={openLearnTab}
            onExit={exit}
            progress={progress}
          />
        )}

        {user && view.name === "train" && (
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

        {user && view.name === "learning" && (
          <LearningMode
            key={view.attempt.id}
            challenge={view.challenge}
            attempt={view.attempt}
            busy={busy}
            onScored={scored}
            onNext={() => nextLearning(view.challenge)}
            onExit={() =>
              setView(
                view.challenge.problem
                  ? { name: "problems" }
                  : { name: "train" },
              )
            }
          />
        )}

        {user && view.name === "lobby" && (
          <BattleLobby
            playerId={playerId}
            displayName={name || "Player"}
            onEntered={enterBattle}
            onExit={exit}
          />
        )}

        {user && view.name === "game" && (
          <BattleMode
            key={view.battle.id}
            battle={view.battle}
            playerId={playerId}
            onScored={scored}
            onRematch={openLobby}
            onExit={exit}
          />
        )}

        {error && <p className="error">{error}</p>}
      </main>
    </>
  );
}
