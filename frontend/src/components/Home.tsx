type HomeProps = {
  busy: boolean;
  onTrain: () => void;
  onBattle: () => void;
};

const LEAVES = [
  { cx: 152, cy: 12, rx: 44, ry: 16 },
  { cx: 92, cy: 24, rx: 32, ry: 14 },
  { cx: 216, cy: 24, rx: 32, ry: 14 },
  { cx: 46, cy: 40, rx: 24, ry: 12 },
  { cx: 268, cy: 40, rx: 24, ry: 12 },
  { cx: 124, cy: 38, rx: 26, ry: 11 },
  { cx: 194, cy: 38, rx: 26, ry: 11 },
];

// A tree frames the word: canopy above, trunk behind, roots spreading underneath.
function Tree() {
  return (
    <svg
      className="mode-art tree"
      viewBox="0 0 320 200"
      preserveAspectRatio="none"
      aria-hidden="true"
    >
      <g className="limbs" fill="none" strokeLinecap="round">
        <path d="M160 146V58" strokeWidth="11" />
        <path d="M160 74c-22-4-40-14-56-30" strokeWidth="6" />
        <path d="M160 74c22-4 40-14 56-30" strokeWidth="6" />
        <path d="M160 60c-12-12-18-26-18-42" strokeWidth="5" />
        <path d="M160 60c12-12 18-26 18-42" strokeWidth="5" />
        <path d="M116 50c-16-2-30-8-42-18" strokeWidth="3.5" />
        <path d="M204 50c16-2 30-8 42-18" strokeWidth="3.5" />
        <path
          d="M160 146c-22 10-38 24-62 32-22 8-48 10-74 14"
          strokeWidth="6"
        />
        <path d="M160 146c22 10 38 24 62 32 22 8 48 10 74 14" strokeWidth="6" />
        <path d="M160 146c-8 18-12 34-10 52" strokeWidth="4.5" />
        <path d="M160 146c8 18 12 34 10 52" strokeWidth="4.5" />
        <path d="M118 166c-18 12-40 16-64 18" strokeWidth="3" />
        <path d="M202 166c18 12 40 16 64 18" strokeWidth="3" />
        <path d="M96 182c-14 6-30 10-50 12" strokeWidth="2.2" />
        <path d="M224 182c14 6 30 10 50 12" strokeWidth="2.2" />
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

export function Home({ busy, onTrain, onBattle }: HomeProps) {
  return (
    <section className="home">
      <p className="home-kicker">Pick a mode</p>

      <div className="marquee">
        <button
          className="mode-word train"
          disabled={busy}
          onClick={onTrain}
          aria-label="Start prompt training"
        >
          <span className="word-wrap">
            <Tree />
            <span className="word">LEARN</span>
          </span>
          <span className="sub">Prompt Training · solo</span>
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

      <dl className="marquee-notes">
        <div className="note train">
          <dt>Training</dt>
          <dd>
            Describe a target, see what your words covered and missed, three
            images per target.
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
