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
  const readyToGenerate = evaluated?.passed === true;

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
          scored.scores?.resultQuality ?? 0,
          scored.usage?.generations ?? 1,
        );
      }
    } catch (caught) {
      setError(caught instanceof ApiError ? caught.message : String(caught));
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
          Learning Mode{" "}
          <span className={`difficulty ${challenge.difficulty}`}>
            {challenge.difficulty}
          </span>
        </h2>
        <button className="link" onClick={onExit}>
          ← Home
        </button>
      </header>

      <div className="image-row">
        <figure>
          <figcaption>Target</figcaption>
          <img src={challenge.imageUrl} alt="Target" />
        </figure>
        {selected && (
          <figure>
            <figcaption>Your result</figcaption>
            <img src={selected.imageUrl} alt="Generated result" />
          </figure>
        )}
      </div>

      {attempt.status === "submitted" ? (
        <div className="results">
          <Scoreboard attempt={attempt} />
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
                  readyToGenerate ? "Generate image" : "Check this prompt"
                }
                disabled={!prompt.trim() || busy !== null}
                onClick={readyToGenerate ? generateImage : evaluatePrompt}
              />
            }
          />
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
              {evaluation.passed && evaluated ? (
                <p>✓ Ready — press the arrow again to generate</p>
              ) : (
                <>
                  {!evaluated && <p>Prompt changed — check it again.</p>}
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
