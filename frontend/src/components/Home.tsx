import { useEffect, useState } from "react";
import { DIFFICULTIES, api, type Challenge, type Difficulty } from "../api";
import { pickRandom } from "../pick";
import { StatStrip } from "./StatStrip";
import type { ProgressSummary } from "../progress";

const BLURB: Record<Difficulty, string> = {
  easy: "One clear subject.",
  medium: "A subject, a setting, specific lighting.",
  hard: "Many subjects, unusual style, precise composition.",
};

const PIN = ["4", "7", "2", "9"];

type HomeProps = {
  difficulty: Difficulty;
  onDifficultyChange: (difficulty: Difficulty) => void;
  busy: boolean;
  onLearn: (challenge: Challenge) => void;
  onBattle: () => void;
  onError: (message: string) => void;
  progress: ProgressSummary;
};

export function Home({
  difficulty,
  onDifficultyChange,
  busy,
  onLearn,
  onBattle,
  onError,
  progress,
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

      <div className="panels">
        <article className="panel training">
          <header>
            <h2>Prompt Training</h2>
            <p>
              Practice alone. Your prompt is reviewed before it is used, the
              target shows what you covered and what you missed, and you get up
              to three images.
            </p>
          </header>

          <div className="preview training-preview" aria-hidden="true">
            {ready ? (
              <img
                src={`/examples/${difficulty}.jpg`}
                alt=""
                className="preview-target"
              />
            ) : (
              <div className="preview-target placeholder">?</div>
            )}
            <div className="preview-chips">
              <span className="covered">covered</span>
              <span className="partial">partial</span>
              <span className="missing">missing</span>
            </div>
            <div className="preview-composer">
              <span>a single red apple on a white table…</span>
              <i className="preview-send">→</i>
            </div>
          </div>

          <button
            className="big learning"
            disabled={busy || !ready}
            onClick={() => {
              const target = pickRandom(challenges ?? []);
              if (target) onLearn(target);
            }}
          >
            Start training
          </button>
        </article>

        <article className="panel royale">
          <header>
            <h2>Prompt Royale</h2>
            <p>
              Head to head. Everyone describes the same target, one image each,
              and the best quality per token takes the round.
            </p>
          </header>

          <div className="preview royale-preview" aria-hidden="true">
            <span className="royale-round">Round 1 of 3</span>
            <div className="pin">
              {PIN.map((digit, index) => (
                <span key={`${digit}-${index}`}>{digit}</span>
              ))}
            </div>
            <div className="royale-players">
              <span className="p1">Kris</span>
              <span className="p2">Ryan</span>
              <span className="p3">Ang</span>
            </div>
          </div>

          <button
            className="big battle"
            disabled={busy || !ready}
            onClick={onBattle}
          >
            Enter the royale
          </button>
        </article>
      </div>

      {!ready && challenges !== null && (
        <p className="arena-empty">
          No {difficulty} images yet — seed some at this difficulty.
        </p>
      )}

      <p className="hint how">
        Score = how close your image is to the target, how well your prompt
        describes it, and how few words and tries you needed.
      </p>
    </section>
  );
}
