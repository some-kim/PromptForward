import type { SkillSummary } from "../api";
import { SkillProgress } from "./SkillProgress";

type HomeProps = {
  busy: boolean;
  onLearn: () => void;
  onBattle: () => void;
  skills: SkillSummary[] | null;
};

const LEAVES = [
  { cx: 160, cy: 14, rx: 52, ry: 18 },
  { cx: 94, cy: 22, rx: 38, ry: 16 },
  { cx: 226, cy: 22, rx: 38, ry: 16 },
  { cx: 44, cy: 38, rx: 30, ry: 14 },
  { cx: 276, cy: 38, rx: 30, ry: 14 },
  { cx: 122, cy: 40, rx: 34, ry: 14 },
  { cx: 198, cy: 40, rx: 34, ry: 14 },
  { cx: 66, cy: 58, rx: 24, ry: 11 },
  { cx: 254, cy: 58, rx: 24, ry: 11 },
  { cx: 160, cy: 44, rx: 30, ry: 13 },
  { cx: 16, cy: 54, rx: 16, ry: 9 },
  { cx: 304, cy: 54, rx: 16, ry: 9 },
];

// A tree frames the word: dense canopy above, trunk behind, roots spreading below.
function Tree() {
  return (
    <svg
      className="mode-art tree"
      viewBox="0 0 320 200"
      preserveAspectRatio="none"
      aria-hidden="true"
    >
      <g className="limbs" fill="none" strokeLinecap="round">
        <path d="M160 150V52" strokeWidth="13" />
        <path d="M160 82c-26-4-48-14-68-32" strokeWidth="8" />
        <path d="M160 82c26-4 48-14 68-32" strokeWidth="8" />
        <path d="M160 62c-16-12-24-26-26-44" strokeWidth="6.5" />
        <path d="M160 62c16-12 24-26 26-44" strokeWidth="6.5" />
        <path d="M116 60c-20 0-38-6-54-18" strokeWidth="5" />
        <path d="M204 60c20 0 38-6 54-18" strokeWidth="5" />
        <path d="M132 44c-8-10-12-22-12-34" strokeWidth="3.5" />
        <path d="M188 44c8-10 12-22 12-34" strokeWidth="3.5" />
        <path d="M78 46c-14-2-26-8-36-18" strokeWidth="3" />
        <path d="M242 46c14-2 26-8 36-18" strokeWidth="3" />
        <path
          d="M160 150c-24 12-40 26-66 34-24 8-52 10-80 14"
          strokeWidth="8"
        />
        <path d="M160 150c24 12 40 26 66 34 24 8 52 10 80 14" strokeWidth="8" />
        <path d="M160 150c-10 18-14 34-12 50" strokeWidth="5.5" />
        <path d="M160 150c10 18 14 34 12 50" strokeWidth="5.5" />
        <path d="M160 152c-32 6-58 18-84 34" strokeWidth="4.5" />
        <path d="M160 152c32 6 58 18 84 34" strokeWidth="4.5" />
        <path d="M112 170c-18 12-42 16-68 18" strokeWidth="3.4" />
        <path d="M208 170c18 12 42 16 68 18" strokeWidth="3.4" />
        <path d="M92 184c-16 6-34 10-56 12" strokeWidth="2.4" />
        <path d="M228 184c16 6 34 10 56 12" strokeWidth="2.4" />
        <path d="M134 178c-6 8-10 16-12 24" strokeWidth="2.2" />
        <path d="M186 178c6 8 10 16 12 24" strokeWidth="2.2" />
      </g>
      <g className="leaves">
        {LEAVES.map((leaf) => (
          <ellipse key={`${leaf.cx}-${leaf.cy}`} {...leaf} />
        ))}
      </g>
    </svg>
  );
}

// Bolts strike down both sides of the word rather than sitting under it.
function Lightning() {
  return (
    <svg
      className="mode-art lightning"
      viewBox="0 0 320 160"
      preserveAspectRatio="none"
      aria-hidden="true"
    >
      <g className="bolts">
        <path d="M34 2 6 70h20L10 158l44-102H32z" />
        <path d="M286 2l28 68h-20l16 88-44-102h22z" />
      </g>
      <g className="sparks">
        <circle cx="62" cy="26" r="3" />
        <circle cx="258" cy="132" r="3" />
        <circle cx="160" cy="8" r="2.4" />
      </g>
    </svg>
  );
}


export function Home({
  busy,
  onLearn,
  onBattle,
  skills,
}: HomeProps) {
  return (
    <section className="home">
      <p className="home-kicker">Pick a mode</p>

      <div className="marquee">
        <button
          className="mode-word train"
          disabled={busy}
          onClick={onLearn}
          aria-label="Open the problem set"
        >
          <span className="word-wrap">
            <Tree />
            <span className="word">LEARN</span>
          </span>
          <span className="sub">Problem Set · random practice</span>
        </button>

        <button
          className="mode-word battle"
          disabled={busy}
          onClick={onBattle}
          aria-label="Enter prompt royale"
        >
          <span className="word-wrap">
            <Lightning />
            <span className="word">BATTLE</span>
          </span>
          <span className="sub">Prompt Royale · head to head</span>
        </button>
      </div>

      {skills && skills.some((skill) => skill.total > 0) && (
        <SkillProgress skills={skills} />
      )}

      <dl className="marquee-notes">
        <div className="note train">
          <dt>Learn</dt>
          <dd>
            A problem set of titled targets, each isolating one prompt skill,
            with hints that unlock as you go — or a random target at any
            difficulty. Score 70 to solve.
          </dd>
        </div>
        <div className="note battle">
          <dt>Royale</dt>
          <dd>
            Same target for everyone, one image each, best quality per token
            takes the round.
          </dd>
        </div>
      </dl>
    </section>
  );
}
