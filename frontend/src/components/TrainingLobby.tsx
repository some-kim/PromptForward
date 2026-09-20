import { useEffect, useState } from "react";
import { DIFFICULTIES, api, type Challenge, type Difficulty } from "../api";
import { pickRandom } from "../pick";
import { StatStrip } from "./StatStrip";
import type { ProgressSummary } from "../progress";
import { LearnHeader, type LearnTab } from "./LearnHeader";

const BLURB: Record<Difficulty, string> = {
  easy: "One clear subject.",
  medium: "A subject, a setting, specific lighting.",
  hard: "Many subjects, unusual style, precise composition.",
};

type TrainingLobbyProps = {
  difficulty: Difficulty;
  onDifficultyChange: (difficulty: Difficulty) => void;
  busy: boolean;
  onStart: (challenge: Challenge) => void;
  onTab: (tab: LearnTab) => void;
  onExit: () => void;
  onError: (message: string) => void;
  progress: ProgressSummary;
};

export function TrainingLobby({
  difficulty,
  onDifficultyChange,
  busy,
  onStart,
  onTab,
  onExit,
  onError,
  progress,
}: TrainingLobbyProps) {
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
      <LearnHeader tab="random" onTab={onTab} onExit={onExit} />

      <StatStrip progress={progress} />

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
          <figure className="example">
            <img
              src={`/examples/${difficulty}.jpg`}
              alt={`Example of a ${difficulty} image`}
            />
            <figcaption>Example {difficulty} image</figcaption>
          </figure>
        ) : (
          <p className="arena-empty">
            {challenges === null
              ? "Loading images…"
              : `No ${difficulty} images yet — seed some at this difficulty.`}
          </p>
        )}
      </div>

      <button
        className="big learning"
        disabled={busy || !ready}
        onClick={() => {
          const target = pickRandom(challenges ?? []);
          if (target) onStart(target);
        }}
      >
        Start
      </button>
    </section>
  );
}
