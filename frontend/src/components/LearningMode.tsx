import { useState } from "react";
import {
  ApiError,
  api,
  type Attempt,
  type Challenge,
  type PromptEvaluation,
} from "../api";
import { Scoreboard } from "./Scoreboard";
import { Composer, SendButton } from "./Composer";
import { EcoPrompt } from "./EcoPrompt";
import { XraySlider } from "./XraySlider";
import { AttentionHeatmap } from "./AttentionHeatmap";
import { round } from "../format";

type Props = {
  challenge: Challenge;
  attempt: Attempt;
  busy: boolean;
  onScored: (attemptId: string, score: number, generations: number) => void;
  onNext: () => void;
  onExit: () => void;
};

export function LearningMode({
  challenge,
  attempt: initialAttempt,
  busy: switching,
  onScored,
  onNext,
  onExit,
}: Props) {
  const [attempt, setAttempt] = useState(initialAttempt);
  const [prompt, setPrompt] = useState("");
  const [evaluation, setEvaluation] = useState<PromptEvaluation | null>(null);
  const [evaluatedPrompt, setEvaluatedPrompt] = useState<string | null>(null);
  const [busy, setBusy] = useState<"evaluating" | "generating" | null>(null);
  const [error, setError] = useState<string | null>(null);

  const evaluated = evaluatedPrompt === prompt ? evaluation : null;
  // Any checked prompt may generate; a weak one is a lesson, not a block.
  const readyToGenerate = evaluated !== null;
  // Stale boxes would lie about the prompt in the box, so the overlay follows the live evaluation.
  const attention = evaluated?.attention ?? [];

  async function evaluatePrompt() {
    setBusy("evaluating");
    setError(null);
    try {
      const result = await api.evaluatePrompt(attempt.id, prompt);
      setEvaluation(result);
      setEvaluatedPrompt(prompt);
    } catch (caught) {
      setError(caught instanceof ApiError ? caught.message : String(caught));
    } finally {
      setBusy(null);
    }
  }

  async function generateImage() {
    setBusy("generating");
    setError(null);
    try {
      const scored = await api.generateLearningImage(attempt.id, prompt);
      setAttempt(scored);
      if (scored.status === "submitted") {
        onScored(
          scored.id,
          scored.scores?.final ?? 0,
          scored.usage?.generations ?? 1,
        );
      }
    } catch (caught) {
      setError(caught instanceof ApiError ? caught.message : String(caught));
      setEvaluation(null);
      setEvaluatedPrompt(null);
    } finally {
      setBusy(null);
    }
  }

  const generations = attempt.generations ?? [];
  const selected = generations.find(
    (g) => g.number === attempt.selectedGeneration,
  );

  return (
    <section className="mode">
      <header className="mode-header">
        <h2>
          Prompt Training{" "}
          <span className={`difficulty ${challenge.difficulty}`}>
            {challenge.difficulty}
          </span>
        </h2>
        <button className="link" onClick={onExit}>
          ← Home
        </button>
      </header>

      {selected ? (
        <XraySlider
          targetUrl={challenge.imageUrl}
          resultUrl={selected.imageUrl}
        />
      ) : attention.length > 0 ? (
        <AttentionHeatmap imageUrl={challenge.imageUrl} regions={attention} />
      ) : (
        <div className="image-row">
          <figure>
            <figcaption>Target</figcaption>
            <img src={challenge.imageUrl} alt="Target" />
          </figure>
        </div>
      )}

      {attempt.status === "submitted" ? (
        <div className="results">
          <Scoreboard attempt={attempt} showFinal />
          {selected?.resultFeedback && (
            <p className="feedback">
              <strong>Feedback</strong>
              <br />
              {selected.resultFeedback}
            </p>
          )}
          <div className="actions">
            {(attempt.generationsRemaining ?? 0) > 0 && (
              <button
                className="secondary"
                disabled={switching}
                onClick={() => {
                  setEvaluation(null);
                  setEvaluatedPrompt(null);
                  setAttempt({ ...attempt, status: "in_progress" });
                }}
              >
                Try another prompt ({attempt.generationsRemaining} left)
              </button>
            )}
            <button disabled={switching} onClick={onNext}>
              {switching ? "Loading…" : "Next target →"}
            </button>
          </div>
        </div>
      ) : (
        <div className="prompt-panel">
          <div className="composer-row">
            <Composer
              label="Write a prompt"
              value={prompt}
              placeholder="Describe the target image so an image model can recreate it."
              onChange={setPrompt}
              onSubmit={readyToGenerate ? generateImage : evaluatePrompt}
              submitDisabled={!prompt.trim() || busy !== null}
              actions={
                <SendButton
                  busy={busy !== null}
                  tone={
                    evaluated ? (evaluated.passed ? "pass" : "fail") : "neutral"
                  }
                  title={
                    readyToGenerate
                      ? "Generate image with this prompt"
                      : "Check this prompt"
                  }
                  disabled={!prompt.trim() || busy !== null}
                  onClick={readyToGenerate ? generateImage : evaluatePrompt}
                />
              }
            />
            <EcoPrompt
              prompt={prompt}
              onChange={setPrompt}
              disabled={busy !== null}
            />
          </div>
          {busy && (
            <p className="hint">
              {busy === "evaluating"
                ? "Checking your prompt…"
                : "Generating… this takes a while."}
            </p>
          )}

          {evaluation && (
            <div
              className={`evaluation ${evaluation.passed ? "passed" : "failed"}`}
            >
              <p className="score">
                Prompt Quality: {round(evaluation.promptQuality)}
              </p>
              {evaluated ? (
                <p>
                  {evaluation.passed ? "✓ Strong prompt" : "Weak prompt"} —
                  press the arrow again to generate
                </p>
              ) : (
                <p>Prompt changed — check it again.</p>
              )}
              {evaluation.needsImprovement.length > 0 && (
                <>
                  <p>Needs improvement:</p>
                  <ul>
                    {evaluation.needsImprovement.map((hint) => (
                      <li key={hint}>{hint}</li>
                    ))}
                  </ul>
                </>
              )}
              <p className="feedback">{evaluation.feedback}</p>
            </div>
          )}
        </div>
      )}

      {error && <p className="error">{error}</p>}
    </section>
  );
}
