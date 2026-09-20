import { useEffect, useState } from "react";
import { ApiError, api, type Battle, type BattleRound } from "../api";
import { Composer, SendButton } from "./Composer";

type Props = {
  battle: Battle;
  deadlineAt: number;
  playerId: string;
  onBattle: (battle: Battle) => void;
};

function clock(seconds: number): string {
  const safe = Math.max(0, seconds);
  return `${Math.floor(safe / 60)}:${String(safe % 60).padStart(2, "0")}`;
}

const LABELS: Record<BattleRound["status"], string> = {
  empty: "Open",
  working: "Generating…",
  ready: "Locked in",
  failed: "Retry",
};

export function BattleArena({ battle, deadlineAt, playerId, onBattle }: Props) {
  const me = battle.players.find((player) => player.isYou);
  const opponent = battle.players.find((player) => !player.isYou);
  const rounds = me?.rounds ?? [];

  const [selected, setSelected] = useState(0);
  const [prompt, setPrompt] = useState("");
  const [sending, setSending] = useState(false);
  const [error, setError] = useState<string | null>(null);
  // The deadline comes from the poll; the tick only keeps the display moving between polls.
  const [tick, setTick] = useState(0);
  const seconds =
    deadlineAt && tick
      ? Math.max(0, Math.round((deadlineAt - tick) / 1000))
      : (battle.secondsRemaining ?? 0);

  useEffect(() => {
    const timer = setInterval(() => setTick(Date.now()), 1000);
    return () => clearInterval(timer);
  }, []);

  const round = rounds[selected];
  const answered = rounds.filter((one) => one.status === "ready").length;
  const canSend =
    !sending &&
    prompt.trim().length > 0 &&
    round !== undefined &&
    round.status !== "ready" &&
    round.status !== "working";

  async function send() {
    if (!round) return;
    setSending(true);
    setError(null);
    try {
      const updated = await api.promptBattleRound(
        battle.id,
        playerId,
        round.index,
        prompt,
      );
      onBattle(updated);
      setPrompt("");
      const next = (
        updated.players.find((player) => player.isYou)?.rounds ?? []
      )
        .filter((one) => one.status === "empty" || one.status === "failed")
        .find((one) => one.index !== round.index);
      if (next) setSelected(next.index);
    } catch (caught) {
      setError(caught instanceof ApiError ? caught.message : String(caught));
    } finally {
      setSending(false);
    }
  }

  return (
    <div className="battle-arena">
      <div className="arena-bar">
        <div className={`battle-clock ${seconds <= 30 ? "urgent" : ""}`}>
          {clock(seconds)}
        </div>
        <div className="arena-progress">
          <span>
            You {answered}/{battle.totalRounds}
          </span>
          {opponent && (
            <span>
              {opponent.displayName} {opponent.submittedRounds}/
              {battle.totalRounds}
            </span>
          )}
        </div>
        <p className="hint">Scores stay sealed until the battle ends.</p>
      </div>

      <div className="round-strip">
        {rounds.map((one) => (
          <button
            key={one.index}
            className={`round-chip ${one.status} ${one.index === selected ? "selected" : ""}`}
            onClick={() => setSelected(one.index)}
          >
            <img src={one.targetImageUrl} alt={`Image ${one.index + 1}`} />
            <span>{LABELS[one.status]}</span>
          </button>
        ))}
      </div>

      {round && (
        <div className="round-panel">
          <figure>
            <figcaption>
              Image {round.index + 1} of {battle.totalRounds}
            </figcaption>
            <img src={round.targetImageUrl} alt="Target" />
          </figure>

          <div className="prompt-panel">
            {round.status === "ready" || round.status === "working" ? (
              <>
                <p className="hint">
                  {round.status === "working"
                    ? "Generating your image…"
                    : "Locked in. Move to the next image."}
                </p>
                <p className="prompt-text">{round.prompt}</p>
              </>
            ) : (
              <>
                {round.status === "failed" && (
                  <p className="hint">
                    That generation failed ({round.error}). Prompt it again — it
                    costs you nothing but time.
                  </p>
                )}
                <Composer
                  value={prompt}
                  placeholder="Describe this image so an image model can recreate it."
                  onChange={setPrompt}
                  onSubmit={send}
                  submitDisabled={!canSend}
                  actions={
                    <SendButton
                      busy={sending}
                      title="Lock in this prompt"
                      disabled={!canSend}
                      onClick={send}
                    />
                  }
                />
              </>
            )}
          </div>
        </div>
      )}

      {error && <p className="error">{error}</p>}
    </div>
  );
}
