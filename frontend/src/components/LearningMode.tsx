import { useState } from "react";
import {
  ApiError,
  api,
  type Attempt,
  type Challenge,
  type Coaching,
  type PromptEvaluation,
} from "../api";
import { CoachPanel } from "./CoachPanel";
import { Scoreboard } from "./Scoreboard";
import { Composer, SendButton } from "./Composer";
import { EcoPrompt } from "./EcoPrompt";
import { XraySlider } from "./XraySlider";
import { AttentionHeatmap } from "./AttentionHeatmap";

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
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  // The coach's latest release: every response carries it, so the newest one wins.
  const [coaching, setCoaching] = useState<Coaching | null>(
    initialAttempt.coaching ?? null,
  );

  const evaluated = evaluatedPrompt === prompt ? evaluation : null;
  // Stale boxes would lie about the prompt in the box, so the overlay follows the live evaluation.
  const attention = evaluated?.attention ?? [];

  // One press scores the prompt and the image it produces; a weak prompt is a lesson, not a block.
  async function generateImage() {
    setBusy(true);
    setError(null);
    try {
      const scored = await api.generateLearningImage(attempt.id, prompt);
      setAttempt(scored);
      if (scored.promptEvaluation) {
        setEvaluation(scored.promptEvaluation);
        setEvaluatedPrompt(prompt);
      }
      if (scored.coaching) setCoaching(scored.coaching);
      if (scored.status === "submitted") {
        onScored(
          scored.id,
          scored.scores?.final ?? 0,
          scored.usage?.generations ?? 1,
        );
      }
    } catch (caught) {
      setError(caught instanceof ApiError ? caught.message : String(caught));
    } finally {
      setBusy(false);
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
          {coaching ? (
            <>
              <span className="problem-order">#{challenge.problem?.order}</span>{" "}
              {coaching.title}
            </>
          ) : (
            "Prompt Training"
          )}{" "}
          <span className={`difficulty ${challenge.difficulty}`}>
            {challenge.difficulty}
          </span>
        </h2>
        <button className="link" onClick={onExit}>
          {coaching ? "← Problems" : "← Home"}
        </button>
      </header>

      {coaching && (
        <CoachPanel
          coaching={coaching}
          submitted={attempt.status === "submitted"}
          missed={evaluated?.needsImprovement ?? []}
        />
      )}

      {selected ? (
        <div className="result-views">
          <XraySlider
            targetUrl={challenge.imageUrl}
            resultUrl={selected.imageUrl}
          />
          {/* The shown result may be an earlier, higher-scoring generation than the last
              prompt checked, and coverage for a different prompt would be a lie. */}
          {attention.length > 0 && selected.prompt === evaluatedPrompt && (
            <AttentionHeatmap
              imageUrl={challenge.imageUrl}
              regions={attention}
            />
          )}
        </div>
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
          {evaluated && (
            <div
              className={`evaluation ${evaluated.passed ? "passed" : "failed"}`}
            >
              <p className="score">
                {evaluated.passed ? "✓ Strong prompt" : "Weak prompt"}
              </p>
              {!coaching && evaluated.needsImprovement.length > 0 && (
                <>
                  <p>Needs improvement:</p>
                  <ul>
                    {evaluated.needsImprovement.map((hint) => (
                      <li key={hint}>{hint}</li>
                    ))}
                  </ul>
                </>
              )}
              <p className="feedback">{evaluated.feedback}</p>
            </div>
          )}
          {selected?.resultFeedback && (
            <p className="feedback">
              <strong>Image feedback</strong>
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
              {switching
                ? "Loading…"
                : coaching
                  ? "Next problem →"
                  : "Next target →"}
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
              disabled={busy}
              onChange={setPrompt}
              onSubmit={generateImage}
              submitDisabled={!prompt.trim() || busy}
              actions={
                <SendButton
                  busy={busy}
                  tone={
                    evaluated ? (evaluated.passed ? "pass" : "fail") : "neutral"
                  }
                  title="Generate and score this prompt"
                  disabled={!prompt.trim() || busy}
                  onClick={generateImage}
                />
              }
            />
            <EcoPrompt prompt={prompt} onChange={setPrompt} disabled={busy} />
          </div>
          {busy && (
            <p className="hint">
              Scoring your prompt, then generating and scoring the image… this
              can take a minute.
            </p>
          )}
        </div>
      )}

      {error && <p className="error">{error}</p>}
    </section>
  );
}
