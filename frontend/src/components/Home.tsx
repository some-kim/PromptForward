type HomeProps = {
  busy: boolean;
  onTrain: () => void;
  onBattle: () => void;
};

const LEAVES = [
  { cx: 44, cy: 54, r: 13 },
  { cx: 22, cy: 86, r: 10 },
  { cx: 72, cy: 30, r: 11 },
  { cx: 276, cy: 54, r: 13 },
  { cx: 298, cy: 86, r: 10 },
  { cx: 248, cy: 30, r: 11 },
  { cx: 160, cy: 18, r: 12 },
  { cx: 112, cy: 20, r: 9 },
  { cx: 208, cy: 20, r: 9 },
];

// A tree grows out of the word: brown trunk and limbs arcing around it, leaves last.
function Tree() {
  return (
    <svg
      className="mode-art tree"
      viewBox="0 0 320 160"
      preserveAspectRatio="none"
      aria-hidden="true"
    >
      <g className="limbs" fill="none" strokeLinecap="round">
        <path d="M160 158v-18" strokeWidth="9" />
        <path d="M160 142c-34 0-62-8-80-26-18-18-24-42-28-70" strokeWidth="7" />
        <path d="M160 142c34 0 62-8 80-26 18-18 24-42 28-70" strokeWidth="7" />
        <path d="M66 96c-12 2-22 10-30 22" strokeWidth="4.5" />
        <path d="M254 96c12 2 22 10 30 22" strokeWidth="4.5" />
        <path d="M52 46c8-12 20-20 34-24" strokeWidth="4.5" />
        <path d="M268 46c-8-12-20-20-34-24" strokeWidth="4.5" />
        <path d="M120 128c-6-10-6-22-2-32" strokeWidth="4" />
        <path d="M200 128c6-10 6-22 2-32" strokeWidth="4" />
      </g>
      <g className="leaves">
        {LEAVES.map((leaf) => (
          <circle key={`${leaf.cx}-${leaf.cy}`} {...leaf} />
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
