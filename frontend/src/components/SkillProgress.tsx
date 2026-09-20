import type { Skill, SkillSummary } from "../api";

type Props = {
  skills: SkillSummary[];
  selected?: Skill | null;
  onSelect?: (skill: Skill | null) => void;
};

// One bar per skill: solved fills green, attempted fills yellow, the rest stays empty.
export function SkillProgress({ skills, selected, onSelect }: Props) {
  const total = skills.reduce((sum, skill) => sum + skill.total, 0);
  const solved = skills.reduce((sum, skill) => sum + skill.solved, 0);

  return (
    <div className="skill-progress">
      <div className="skill-progress-head">
        <span>Curriculum</span>
        <strong>
          {solved} / {total} solved
        </strong>
      </div>
      <ul className="skill-list">
        {skills.map((skill) => {
          const pct = (value: number) =>
            skill.total ? `${(value / skill.total) * 100}%` : "0%";
          const done = skill.total > 0 && skill.solved === skill.total;
          const content = (
            <>
              <span className="skill-name">
                {skill.title}
                {done && <span className="skill-badge">mastered</span>}
              </span>
              <span className="skill-bar" aria-hidden="true">
                <span
                  className="skill-fill attempted"
                  style={{ width: pct(skill.solved + skill.attempted) }}
                />
                <span
                  className="skill-fill solved"
                  style={{ width: pct(skill.solved) }}
                />
              </span>
              <span className="skill-count">
                {skill.solved}/{skill.total}
              </span>
            </>
          );
          return (
            <li
              key={skill.skill}
              className={selected === skill.skill ? "selected" : ""}
            >
              {onSelect ? (
                <button
                  className="skill-row"
                  title={skill.lesson}
                  onClick={() =>
                    onSelect(selected === skill.skill ? null : skill.skill)
                  }
                >
                  {content}
                </button>
              ) : (
                <span className="skill-row" title={skill.lesson}>
                  {content}
                </span>
              )}
            </li>
          );
        })}
      </ul>
    </div>
  );
}
