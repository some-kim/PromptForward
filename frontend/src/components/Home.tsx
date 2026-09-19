import { useEffect, useState } from "react";
import { DIFFICULTIES, api, type Challenge, type Difficulty } from "../api";

const BLURB: Record<Difficulty, string> = {
  easy: "One clear subject.",
  medium: "A subject, a setting, specific lighting.",
  hard: "Many subjects, unusual style, precise composition.",
};

function pickRandom(
  challenges: Challenge[],
  avoid?: Challenge,
): Challenge | null {
  const pool =
    challenges.length > 1
      ? challenges.filter((c) => c.id !== avoid?.id)
      : challenges;
  return pool.length === 0
    ? null
    : pool[Math.floor(Math.random() * pool.length)];
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
  const [preview, setPreview] = useState<Challenge | null>(null);

  // Remounted per difficulty (keyed by the parent), so this only ever runs one fetch.
  useEffect(() => {
    let current = true;
    api
      .listChallenges(difficulty)
      .then((found) => {
        if (!current) return;
        setChallenges(found);
        setPreview(pickRandom(found));
      })
      .catch((caught) => current && onError(String(caught)));
    return () => {
      current = false;
    };
  }, [difficulty, onError]);

  const empty = challenges !== null && challenges.length === 0;

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
        {preview ? (
          <>
            <img src={preview.imageUrl} alt="Random target" />
            <button
              className="link shuffle"
              onClick={() => setPreview(pickRandom(challenges ?? [], preview))}
              disabled={busy || (challenges?.length ?? 0) < 2}
            >
              ⟳ Shuffle target
            </button>
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
          disabled={busy || empty || !preview}
          onClick={() => preview && onLearn(preview)}
        >
          Learning
          <small>Practice, 3 tries</small>
        </button>
        <button
          className="big battle"
          disabled={busy || empty}
          onClick={onBattle}
        >
          Battle
          <small>1 try, vs a friend</small>
        </button>
      </div>
    </section>
  );
}
