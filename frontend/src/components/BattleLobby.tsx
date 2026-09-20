import { useState } from "react";
import { ApiError, BATTLE_LIMITS, api, type Battle } from "../api";

type Props = {
  playerId: string;
  displayName: string;
  onEntered: (battle: Battle) => void;
  onExit: () => void;
};

const { durationSeconds: DURATION, imagesPerPlayer: IMAGES } = BATTLE_LIMITS;

export function BattleLobby({
  playerId,
  displayName,
  onEntered,
  onExit,
}: Props) {
  const [minutes, setMinutes] = useState<number>(DURATION.default / 60);
  const [images, setImages] = useState<number>(IMAGES.default);
  const [useDefaults, setUseDefaults] = useState(false);
  const [code, setCode] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function run(action: () => Promise<Battle>) {
    setBusy(true);
    setError(null);
    try {
      onEntered(await action());
    } catch (caught) {
      setError(caught instanceof ApiError ? caught.message : String(caught));
    } finally {
      setBusy(false);
    }
  }

  const create = () =>
    run(() =>
      api.createBattle(
        playerId,
        displayName,
        { durationSeconds: minutes * 60, imagesPerPlayer: images },
        useDefaults,
      ),
    );

  const join = () => run(() => api.joinBattle(code, playerId, displayName));

  return (
    <section className="mode battle-lobby">
      <header className="mode-header">
        <h2>Prompt Royale</h2>
        <button className="link" onClick={onExit}>
          Back
        </button>
      </header>

      <div className="lobby-grid">
        <div className="lobby-card">
          <h3>Host a battle</h3>
          <p className="hint">
            Both players prompt every image in the pool —{" "}
            <strong>{images * 2} images</strong> in {minutes} minute
            {minutes === 1 ? "" : "s"}.
          </p>

          <label className="setting">
            <span>
              Time limit <strong>{minutes} min</strong>
            </span>
            <input
              type="range"
              min={DURATION.min / 60}
              max={DURATION.max / 60}
              step={1}
              value={minutes}
              disabled={busy}
              onChange={(event) => setMinutes(Number(event.target.value))}
            />
          </label>

          <label className="setting">
            <span>
              Images per player <strong>{images}</strong>
            </span>
            <input
              type="range"
              min={IMAGES.min}
              max={IMAGES.max}
              step={1}
              value={images}
              disabled={busy}
              onChange={(event) => setImages(Number(event.target.value))}
            />
          </label>

          <label className="setting checkbox">
            <input
              type="checkbox"
              checked={useDefaults}
              disabled={busy}
              onChange={(event) => setUseDefaults(event.target.checked)}
            />
            <span>Skip uploads and use PromptForward images for my side</span>
          </label>

          <button className="primary" disabled={busy} onClick={create}>
            Create battle
          </button>
        </div>

        <div className="lobby-card">
          <h3>Join with a code</h3>
          <p className="hint">Ask the host for their six-character code.</p>
          <input
            className="code-input"
            value={code}
            maxLength={6}
            placeholder="ABC123"
            disabled={busy}
            onChange={(event) => setCode(event.target.value.toUpperCase())}
            onKeyDown={(event) => {
              if (event.key === "Enter" && code.length === 6) join();
            }}
          />
          <button
            className="primary"
            disabled={busy || code.trim().length < 6}
            onClick={join}
          >
            Join battle
          </button>
        </div>
      </div>

      {error && <p className="error">{error}</p>}
    </section>
  );
}
