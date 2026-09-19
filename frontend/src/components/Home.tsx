import { useEffect, useState } from "react";
import { DIFFICULTIES, api, type Challenge, type Difficulty } from "../api";

const BLURB: Record<Difficulty, string> = {
  easy: "One clear subject.",
  medium: "A subject, a setting, specific lighting.",
  hard: "Many subjects, unusual style, precise composition.",
};

function pickRandom(challenges: Challenge[]): Challenge | null {
  return challenges.length === 0
    ? null
    : challenges[Math.floor(Math.random() * challenges.length)];
}

type HomeProps = {
  name: string;
  onNameChange: (name: string) => void;
  difficulty: Difficulty;
  onDifficultyChange: (difficulty: Difficulty) => void;
  busy: boolean;
  onLearn: (challenge: Challenge) => void;
  onBattle: () => void;
  onError: (message: string) => void;
};

export function Home({
  name,
  onNameChange,
  difficulty,
  onDifficultyChange,
  busy,
  onLearn,
  onBattle,
  onError,
}: HomeProps) {
  const [challenges, setChallenges] = useState<Challenge[] | null>(null);

  // Remounted per difficulty (keyed by the parent), so this only ever runs one fetch.
  useEffect(() => {
    let current = true;
    api
      .listChallenges(difficulty)
      .then((found) => {
        if (!current) return;
        setChallenges(found);
      })
      .catch((caught) => current && onError(String(caught)));
    return () => {
      current = false;
    };
  }, [difficulty, onError]);

  const ready = challenges !== null && challenges.length > 0;

  return (
    <section className="home">
      <div className="top-bar">
        <div className="player-chip">
          <span className="avatar">
            {(name || "P").slice(0, 1).toUpperCase()}
          </span>
          <input
            value={name}
            placeholder="Player"
            aria-label="Display name"
            onChange={(event) => onNameChange(event.target.value)}
          />
        </div>
        <span className="target-count">
          {challenges === null ? "…" : `${challenges.length} targets`}
        </span>
      </div>

      <div className="difficulty-bar">
        <span className="difficulty-label">Difficulty</span>
        <div className="difficulty-tabs">
          {DIFFICULTIES.map((level) => (
            <button
              key={level}
              className={`tab ${level} ${difficulty === level ? "selected" : ""}`}
              onClick={() => onDifficultyChange(level)}
            >
              {level}
            </button>
          ))}
        </div>
        <p className="hint">{BLURB[difficulty]}</p>
      </div>

      <div className="arena">
        {ready ? (
          <>
            <div className="hidden-target" aria-hidden="true">
              ?
            </div>
            <p className="arena-empty">
              Your target stays hidden until you start.
            </p>
          </>
        ) : (
          <p className="arena-empty">
            {challenges === null
              ? "Loading targets…"
              : `No ${difficulty} targets yet — seed some images at this difficulty.`}
          </p>
        )}
      </div>

      <div className="big-buttons">
        <button
          className="big learning"
          disabled={busy || !ready}
          onClick={() => {
            const target = pickRandom(challenges ?? []);
            if (target) onLearn(target);
          }}
        >
          Learning
          <small>Practice, 3 tries</small>
        </button>
        <button
          className="big battle"
          disabled={busy || !ready}
          onClick={onBattle}
        >
          Battle
          <small>1 try, vs a friend</small>
        </button>
      </div>

      <section className="info">
        <h2>How it works</h2>
        <p>
          You are shown a target image. Write the prompt that would make an
          image model recreate it, then see how close you got.
        </p>
        <dl>
          <div>
            <dt>Learning</dt>
            <dd>
              Practice alone. Your prompt is reviewed before it is used, and you
              get up to three generations.
            </dd>
          </div>
          <div>
            <dt>Battle</dt>
            <dd>
              Share the link with a friend. You both describe the same target,
              one generation each, higher score wins.
            </dd>
          </div>
        </dl>
        <p className="hint">
          Score = how close your image is to the target, how well your prompt
          describes it, and how few words and tries you needed.
        </p>
      </section>
    </section>
  );
}
