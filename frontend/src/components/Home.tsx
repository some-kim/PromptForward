import { useEffect, useState } from "react";
import { DIFFICULTIES, api, type Challenge, type Difficulty } from "../api";
import { pickRandom } from "../pick";

const BLURB: Record<Difficulty, string> = {
  easy: "One clear subject.",
  medium: "A subject, a setting, specific lighting.",
  hard: "Many subjects, unusual style, precise composition.",
};

type HomeProps = {
  difficulty: Difficulty;
  onDifficultyChange: (difficulty: Difficulty) => void;
  busy: boolean;
  onLearn: (challenge: Challenge) => void;
  onBattle: () => void;
  onError: (message: string) => void;
};

export function Home({
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
        </button>
        <button
          className="big battle"
          disabled={busy || !ready}
          onClick={onBattle}
        >
          Battle
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
