import type { Coaching } from "../api";

type Props = {
  coaching: Coaching;
  submitted: boolean;
  // Category-level gaps from the live evaluation, shown as the "what you missed" recap.
  missed: string[];
};

export function CoachPanel({ coaching, submitted, missed }: Props) {
  const locked = coaching.hintsRemaining;

  return (
    <aside className={`coach ${coaching.solved ? "solved" : ""}`}>
      <div className="coach-head">
        <span className="skill-chip">{coaching.skillTitle}</span>
        {coaching.solved && <span className="solved-badge">Solved</span>}
      </div>
      <p className="coach-lesson">{coaching.lesson}</p>
      <p className="coach-tests">
        <strong>This problem tests:</strong> {coaching.tests}
      </p>

      {(coaching.hints.length > 0 || locked > 0) && (
        <div className="coach-hints">
          <strong>Hints</strong>
          <ol>
            {coaching.hints.map((hint) => (
              <li key={hint}>{hint}</li>
            ))}
            {Array.from({ length: locked }, (_, index) => (
              <li key={`locked-${index}`} className="locked">
                Locked — unlocks after a weak prompt
              </li>
            ))}
          </ol>
        </div>
      )}

      {!submitted && missed.length > 0 && (
        <div className="coach-missed">
          <strong>What you missed</strong>
          <ul>
            {missed.map((gap) => (
              <li key={gap}>{gap}</li>
            ))}
          </ul>
        </div>
      )}

      {coaching.referencePrompt && (
        <div className="coach-reference">
          <strong>Reference prompt</strong>
          <p>{coaching.referencePrompt}</p>
        </div>
      )}
    </aside>
  );
}
