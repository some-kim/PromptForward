import { useEffect, useRef, useState } from "react";
import { ApiError, api, type Battle, type LibraryImage } from "../api";

type Props = {
  battle: Battle;
  playerId: string;
  onBattle: (battle: Battle) => void;
};

/** The room before the clock starts: bring your images, or take the house's. */
export function BattleSetup({ battle, playerId, onBattle }: Props) {
  const [library, setLibrary] = useState<LibraryImage[]>([]);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const fileInput = useRef<HTMLInputElement>(null);

  const me = battle.players.find((player) => player.isYou);
  const opponent = battle.players.find((player) => !player.isYou);
  const perPlayer = battle.settings.imagesPerPlayer;
  const chosen = me?.images ?? [];
  const remaining = perPlayer - chosen.length;
  const chosenIds = new Set(chosen.map((image) => image.challengeId));

  useEffect(() => {
    api
      .listLibraryImages(playerId)
      .then(setLibrary)
      .catch(() => undefined);
  }, [playerId]);

  async function run(action: () => Promise<Battle>) {
    setBusy(true);
    setError(null);
    try {
      onBattle(await action());
    } catch (caught) {
      setError(caught instanceof ApiError ? caught.message : String(caught));
    } finally {
      setBusy(false);
    }
  }

  async function upload(file: File) {
    setBusy(true);
    setError(null);
    try {
      const uploaded = await api.uploadLibraryImage(playerId, file);
      setLibrary((current) =>
        current.some((image) => image.id === uploaded.id)
          ? current
          : [uploaded, ...current],
      );
      if (remaining > 0) {
        onBattle(await api.addBattleImage(battle.id, playerId, uploaded.id));
      }
    } catch (caught) {
      setError(caught instanceof ApiError ? caught.message : String(caught));
    } finally {
      setBusy(false);
      if (fileInput.current) fileInput.current.value = "";
    }
  }

  return (
    <div className="battle-setup">
      <div className="battle-code">
        <span>Battle code</span>
        <strong>{battle.code}</strong>
        <button
          className="link"
          onClick={() => navigator.clipboard?.writeText(battle.code)}
        >
          Copy
        </button>
      </div>

      <p className="hint">
        {opponent
          ? `${opponent.displayName} is in. `
          : "Waiting for an opponent. "}
        Each player brings {perPlayer} image{perPlayer === 1 ? "" : "s"}; both
        of you then prompt all {perPlayer * 2} of them in{" "}
        {battle.settings.durationSeconds / 60} minutes.
      </p>

      <ul className="setup-players">
        {battle.players.map((player) => (
          <li key={player.displayName} className={player.ready ? "ready" : ""}>
            <span>{player.displayName}</span>
            <span>
              {player.imagesChosen}/{perPlayer}
              {player.usedDefaults ? " · defaults" : ""}
            </span>
          </li>
        ))}
      </ul>

      <div className="chosen-strip">
        {Array.from({ length: perPlayer }).map((_, slot) => {
          const image = chosen[slot];
          return image ? (
            <figure key={image.challengeId} className="chosen">
              <img src={image.imageUrl} alt="Chosen" />
              <button
                className="link"
                disabled={busy}
                onClick={() =>
                  run(() =>
                    api.removeBattleImage(
                      battle.id,
                      playerId,
                      image.challengeId,
                    ),
                  )
                }
              >
                Remove
              </button>
            </figure>
          ) : (
            <figure key={`empty-${slot}`} className="chosen empty">
              <span>{slot + 1}</span>
            </figure>
          );
        })}
      </div>

      <div className="setup-actions">
        <button
          className="primary"
          disabled={busy || remaining <= 0}
          onClick={() => fileInput.current?.click()}
        >
          Upload an image
        </button>
        <input
          ref={fileInput}
          type="file"
          accept="image/*"
          hidden
          onChange={(event) => {
            const file = event.target.files?.[0];
            if (file) upload(file);
          }}
        />
        <button
          disabled={busy || remaining <= 0}
          onClick={() =>
            run(() => api.fillBattleWithDefaults(battle.id, playerId))
          }
        >
          Fill {remaining > 0 ? remaining : ""} with default images
        </button>
      </div>

      {library.length > 0 && (
        <div className="library">
          <h4>Your images</h4>
          <div className="library-strip">
            {library.map((image) => (
              <button
                key={image.id}
                className="library-image"
                disabled={busy || remaining <= 0 || chosenIds.has(image.id)}
                title={
                  chosenIds.has(image.id)
                    ? "Already in the pool"
                    : "Add to pool"
                }
                onClick={() =>
                  run(() => api.addBattleImage(battle.id, playerId, image.id))
                }
              >
                <img src={image.imageUrl} alt="From your library" />
              </button>
            ))}
          </div>
        </div>
      )}

      {error && <p className="error">{error}</p>}
    </div>
  );
}
