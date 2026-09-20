const PIN = ["4", "7", "2", "9"];

type HomeProps = {
  busy: boolean;
  onTrain: () => void;
  onBattle: () => void;
};

export function Home({ busy, onTrain, onBattle }: HomeProps) {
  return (
    <section className="home">
      <div className="panels">
        <article className="panel training">
          <header>
            <h2>Prompt Training</h2>
            <p>
              Practice alone. Your prompt is reviewed before it is used, the
              target shows what you covered and what you missed, and you get up
              to three images.
            </p>
          </header>

          <div className="preview training-preview" aria-hidden="true">
            <img src="/examples/easy.jpg" alt="" className="preview-target" />
            <div className="preview-chips">
              <span className="covered">covered</span>
              <span className="partial">partial</span>
              <span className="missing">missing</span>
            </div>
            <div className="preview-composer">
              <span>a single red apple on a white table…</span>
              <i className="preview-send">→</i>
            </div>
          </div>

          <button className="big learning" disabled={busy} onClick={onTrain}>
            Start training
          </button>
        </article>

        <article className="panel royale">
          <header>
            <h2>Prompt Royale</h2>
            <p>
              Head to head. Everyone describes the same target, one image each,
              and the best quality per token takes the round.
            </p>
          </header>

          <div className="preview royale-preview" aria-hidden="true">
            <span className="royale-round">Round 1 of 3</span>
            <div className="pin">
              {PIN.map((digit, index) => (
                <span key={`${digit}-${index}`}>{digit}</span>
              ))}
            </div>
            <div className="royale-players">
              <span className="p1">Kris</span>
              <span className="p2">Ryan</span>
              <span className="p3">Ang</span>
            </div>
          </div>

          <button className="big battle" disabled={busy} onClick={onBattle}>
            Enter the royale
          </button>
        </article>
      </div>

      <p className="hint how">
        Score = how close your image is to the target, how well your prompt
        describes it, and how few words and tries you needed.
      </p>
    </section>
  );
}
