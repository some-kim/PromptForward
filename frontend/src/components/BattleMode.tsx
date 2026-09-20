import { useCallback, useEffect, useRef, useState } from "react";
import { api, type Battle } from "../api";
import { prefersReducedMotion } from "../motion";
import { BattleArena } from "./BattleArena";
import { BattleIntro } from "./BattleIntro";
import { BattleResults } from "./BattleResults";
import { BattleSetup } from "./BattleSetup";

const POLL_INTERVAL_MS = 2000;
const ALERT_MS = 3200;

type Props = {
  battle: Battle;
  playerId: string;
  onScored: (attemptId: string, score: number, generations: number) => void;
  onRematch: () => void;
  onExit: () => void;
};

type Alert = { id: number; text: string };

export function BattleMode({
  battle: initial,
  playerId,
  onScored,
  onRematch,
  onExit,
}: Props) {
  const [battle, setBattle] = useState(initial);
  // Anchored here, off the render path, so the arena clock can tick between polls.
  const [deadlineAt, setDeadlineAt] = useState(0);
  const [introDone, setIntroDone] = useState(initial.status === "active");
  const [alerts, setAlerts] = useState<Alert[]>([]);
  const alertId = useRef(0);
  const opponentSubmitted = useRef(
    initial.players.find((player) => !player.isYou)?.submittedRounds ?? 0,
  );

  const receive = useCallback((next: Battle) => {
    setBattle(next);
    setDeadlineAt(
      next.secondsRemaining === null
        ? 0
        : Date.now() + next.secondsRemaining * 1000,
    );

    const opponent = next.players.find((player) => !player.isYou);
    const submitted = opponent?.submittedRounds ?? 0;
    if (opponent && submitted > opponentSubmitted.current) {
      const id = ++alertId.current;
      setAlerts((current) => [
        ...current,
        {
          id,
          text: `${opponent.displayName} locked in ${submitted} of ${next.totalRounds}`,
        },
      ]);
      window.setTimeout(
        () => setAlerts((current) => current.filter((one) => one.id !== id)),
        ALERT_MS,
      );
    }
    opponentSubmitted.current = submitted;
  }, []);

  useEffect(() => {
    if (battle.status === "completed") return;
    const timer = setInterval(async () => {
      try {
        receive(await api.getBattle(battle.id, playerId));
      } catch {
        // A dropped poll is not fatal; the next one catches up.
      }
    }, POLL_INTERVAL_MS);
    return () => clearInterval(timer);
  }, [battle.id, battle.status, playerId, receive]);

  // Reporting is keyed by attempt, so reopening a finished battle never double counts.
  useEffect(() => {
    if (battle.status !== "completed") return;
    const mine = battle.players.find((player) => player.isYou);
    for (const round of mine?.rounds ?? []) {
      if (round.attemptId && round.status === "ready") {
        onScored(round.attemptId, round.scores?.final ?? 0, 1);
      }
    }
  }, [battle, onScored]);

  const me = battle.players.find((player) => player.isYou);
  const opponent = battle.players.find((player) => !player.isYou);
  const showIntro =
    battle.status === "active" && !introDone && !prefersReducedMotion();

  return (
    <section className="mode battle-mode">
      <header className="mode-header">
        <h2>Prompt Royale</h2>
        <button className="link" onClick={onExit}>
          Leave battle
        </button>
      </header>

      {battle.status === "waiting" && (
        <BattleSetup battle={battle} playerId={playerId} onBattle={receive} />
      )}

      {battle.status === "active" && (
        <>
          {showIntro && (
            <BattleIntro
              you={me?.displayName ?? "You"}
              opponent={opponent?.displayName ?? "Opponent"}
              totalRounds={battle.totalRounds}
              onDone={() => setIntroDone(true)}
            />
          )}
          <div className="battle-alerts" aria-live="polite">
            {alerts.map((alert) => (
              <p key={alert.id} className="battle-alert">
                {alert.text}
              </p>
            ))}
          </div>
          <BattleArena
            battle={battle}
            deadlineAt={deadlineAt}
            playerId={playerId}
            onBattle={receive}
          />
        </>
      )}

      {battle.status === "completed" && (
        <BattleResults battle={battle} onRematch={onRematch} onExit={onExit} />
      )}
    </section>
  );
}
