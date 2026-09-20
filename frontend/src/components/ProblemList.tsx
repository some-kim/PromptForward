import { useState } from "react";
import {
  DIFFICULTIES,
  type Difficulty,
  type Challenge,
  type Problem,
  type ProblemSet,
  type Skill,
} from "../api";
import { nextProblem, toChallenge } from "../problems";
import type { ProgressSummary } from "../progress";
import { SkillProgress } from "./SkillProgress";
import { StatStrip } from "./StatStrip";

type Props = {
  problemSet: ProblemSet | null;
  busy: boolean;
  onStart: (challenge: Challenge) => void;
  onExit: () => void;
  progress: ProgressSummary;
};

const STATUS_LABEL: Record<Problem["status"], string> = {
  unsolved: "Todo",
  attempted: "Attempted",
  solved: "Solved",
};

export function ProblemList({
  problemSet,
  busy,
  onStart,
  onExit,
  progress,
}: Props) {
  const [skill, setSkill] = useState<Skill | null>(null);
  const [difficulty, setDifficulty] = useState<Difficulty | null>(null);

  const problems = problemSet?.problems ?? [];
  const shown = problems.filter(
    (problem) =>
      (skill === null || problem.skill === skill) &&
      (difficulty === null || problem.difficulty === difficulty),
  );
  const next = nextProblem(problems);

  return (
    <section className="home problems">
      <header className="mode-header">
        <h2>Problem Set</h2>
        <button className="link" onClick={onExit}>
          ← Home
        </button>
      </header>

      <StatStrip progress={progress} />

      {problemSet && (
        <SkillProgress
          skills={problemSet.skills}
          selected={skill}
          onSelect={setSkill}
        />
      )}

      <div className="difficulty-bar">
        <span className="difficulty-label">Difficulty</span>
        <div className="difficulty-tabs">
          <button
            className={`tab ${difficulty === null ? "selected" : ""}`}
            onClick={() => setDifficulty(null)}
          >
            all
          </button>
          {DIFFICULTIES.map((level) => (
            <button
              key={level}
              className={`tab ${level} ${difficulty === level ? "selected" : ""}`}
              onClick={() => setDifficulty(level)}
            >
              {level}
            </button>
          ))}
        </div>
        {next && (
          <button
            className="secondary continue"
            disabled={busy}
            onClick={() => onStart(toChallenge(next))}
          >
            Continue: {next.title} →
          </button>
        )}
      </div>

      {problemSet === null ? (
        <p className="arena-empty">Loading problems…</p>
      ) : shown.length === 0 ? (
        <p className="arena-empty">
          {problems.length === 0
            ? "No problems seeded yet — run the seed script with a manifest."
            : "No problems match these filters."}
        </p>
      ) : (
        <table className="problem-table">
          <thead>
            <tr>
              <th className="col-status">Status</th>
              <th className="col-num">#</th>
              <th>Title</th>
              <th className="col-skill">Skill</th>
              <th className="col-diff">Difficulty</th>
              <th className="col-score">Best</th>
            </tr>
          </thead>
          <tbody>
            {shown.map((problem) => (
              <tr
                key={problem.id}
                className={`problem-row ${problem.status}`}
                onClick={() => !busy && onStart(toChallenge(problem))}
                tabIndex={0}
                onKeyDown={(event) => {
                  if (event.key === "Enter" && !busy)
                    onStart(toChallenge(problem));
                }}
                aria-label={`Start ${problem.title}`}
              >
                <td className="col-status">
                  <span className={`status-dot ${problem.status}`} />
                  <span className="status-text">
                    {STATUS_LABEL[problem.status]}
                  </span>
                </td>
                <td className="col-num">{problem.order}</td>
                <td>
                  <span className="problem-title">{problem.title}</span>
                  <span className="problem-tests">{problem.tests}</span>
                </td>
                <td className="col-skill">
                  <span className="skill-chip">{problem.skillTitle}</span>
                </td>
                <td className="col-diff">
                  <span className={`difficulty ${problem.difficulty}`}>
                    {problem.difficulty}
                  </span>
                </td>
                <td className="col-score">
                  {problem.bestScore === null ? "—" : problem.bestScore}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
    </section>
  );
}
