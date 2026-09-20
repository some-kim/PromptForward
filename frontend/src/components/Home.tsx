type HomeProps = {
  busy: boolean;
  onTrain: () => void;
  onBattle: () => void;
};

// Roots are drawn as dashed strokes, so the growth is a dashoffset sweep down each branch.
function Roots() {
  return (
    <svg className="roots" viewBox="0 0 220 90" aria-hidden="true">
      <g fill="none" strokeLinecap="round" strokeWidth="3">
        <path d="M110 0v34" />
        <path d="M110 34c-14 6-24 18-30 34" />
        <path d="M110 34c14 6 24 18 30 34" />
        <path d="M110 34c-4 14-4 30-2 48" />
        <path d="M86 56c-12 2-22 8-30 18" strokeWidth="2" />
        <path d="M134 56c12 2 22 8 30 18" strokeWidth="2" />
        <path d="M108 70c-8 4-14 10-18 18" strokeWidth="2" />
      </g>
    </svg>
  );
}

// The bolt runs down the blade, so the sword reads as struck rather than merely drawn.
function LightningSword() {
  return (
    <svg className="sword" viewBox="0 0 220 90" aria-hidden="true">
      <g className="blade" strokeLinejoin="round" strokeWidth="3">
        <path d="M32 78 44 66 150 14l14 14L112 66 96 78z" />
        <path d="M84 62 68 78" strokeWidth="4" />
        <path d="M60 60 44 76" strokeWidth="6" />
      </g>
      <path
        className="bolt"
        d="M150 18 122 46h16l-22 30 40-34h-16z"
        strokeWidth="2"
      />
      <g className="sparks">
        <circle cx="166" cy="24" r="3" />
        <circle cx="140" cy="54" r="2.4" />
        <circle cx="106" cy="72" r="2" />
      </g>
    </svg>
  );
}

export function Home({ busy, onTrain, onBattle }: HomeProps) {
  return (
    <section className="home">
      {/* The two words tilt toward each other so the pair reads as one big V. */}
      <div className="marquee">
        <button
          className="mode-word train"
          disabled={busy}
          onClick={onTrain}
          aria-label="Start prompt training"
        >
          <span className="index">01</span>
          <span className="word">LEARN</span>
          <Roots />
          <span className="sub">Prompt Training · solo</span>
        </button>

        <button
          className="mode-word battle"
          disabled={busy}
          onClick={onBattle}
          aria-label="Enter prompt royale"
        >
          <span className="index">02</span>
          <span className="word">BATTLE</span>
          <LightningSword />
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

      <p className="hint how">
        Score = how close your image is to the target, how well your prompt
        describes it, and how few words and tries you needed.
      </p>
    </section>
  );
}
