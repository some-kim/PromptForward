import { useEffect, useMemo, useState } from "react";
import type { Battle, BattlePlayer, BattleRound } from "../api";

type Props = {
  battle: Battle;
  onDone: () => void;
};

const ROUND_MS = 2600;
const FINALE_MS = 2600;

type Stage = { kind: "round"; index: number } | { kind: "finale" };

function scoreOf(round?: BattleRound): number {
  return Math.round(round?.scores?.final ?? 0);
}

function Card({
  player,
  round,
  outcome,
}: {
  player: BattlePlayer;
  round?: BattleRound;
  outcome: "won" | "lost" | "tied";
}) {
  return (
    <div
      className={`reveal-card ${player.isYou ? "mine" : "theirs"} ${outcome}`}
    >
      <div className="reveal-image">
        {round?.imageUrl ? (
          <img src={round.imageUrl} alt={`${player.displayName} result`} />
        ) : (
          <div className="missed">No image</div>
        )}
      </div>
      <span className="who">{player.displayName}</span>
      <span className="score">{scoreOf(round)}</span>
    </div>
  );
}

/** The cinematic: each round scored one at a time, then the verdict with weather. */
export function BattleReveal({ battle, onDone }: Props) {
  const me = battle.players.find((player) => player.isYou);
  const opponent = battle.players.find((player) => !player.isYou);
  const outcome = battle.winner ?? "draw";

  const stages = useMemo<Stage[]>(
    () => [
      ...Array.from({ length: battle.totalRounds }, (_, index): Stage => ({
        kind: "round",
        index,
      })),
      { kind: "finale" },
    ],
    [battle.totalRounds],
  );
  const [step, setStep] = useState(0);
  const stage = stages[Math.min(step, stages.length - 1)];

  useEffect(() => {
    const last = step >= stages.length - 1;
    const timer = window.setTimeout(
      () => (last ? onDone() : setStep((current) => current + 1)),
      last ? FINALE_MS : ROUND_MS,
    );
    return () => window.clearTimeout(timer);
  }, [step, stages.length, onDone]);

  const drops = useMemo(
    () =>
      Array.from({ length: 70 }, (_, index) => ({
        left: (index * 37) % 100,
        delay: ((index * 13) % 22) / 10,
        hue: (index * 47) % 360,
      })),
    [],
  );

  if (stage.kind === "finale") {
    return (
      <div className={`battle-cinema finale ${outcome}`}>
        <div
          className={outcome === "you" ? "confetti" : "rain"}
          aria-hidden="true"
        >
          {drops.map((drop, index) => (
            <span
              key={index}
              style={{
                left: `${drop.left}%`,
                animationDelay: `${drop.delay}s`,
                ...(outcome === "you"
                  ? { background: `hsl(${drop.hue} 85% 60%)` }
                  : {}),
              }}
            />
          ))}
        </div>
        <h2 className="cinema-verdict">
          {outcome === "you"
            ? "VICTORY"
            : outcome === "opponent"
              ? "DEFEAT"
              : "DEAD HEAT"}
        </h2>
        <div className="cinema-totals">
          {battle.players.map((player) => (
            <div key={player.displayName}>
              <span className="who">{player.displayName}</span>
              <span className="points">{Math.round(player.total ?? 0)}</span>
            </div>
          ))}
        </div>
        <button className="link cinema-skip" onClick={onDone}>
          See the breakdown
        </button>
      </div>
    );
  }

  const mine = me?.rounds[stage.index];
  const theirs = opponent?.rounds[stage.index];
  const gap = scoreOf(mine) - scoreOf(theirs);

  return (
    <div className="battle-cinema">
      <p className="cinema-step">
        Image {stage.index + 1} of {battle.totalRounds}
      </p>
      <div key={stage.index} className="reveal-row">
        {me && (
          <Card
            player={me}
            round={mine}
            outcome={gap > 0 ? "won" : gap < 0 ? "lost" : "tied"}
          />
        )}
        <figure className="reveal-target">
          {(mine?.targetImageUrl ?? theirs?.targetImageUrl) && (
            <img
              src={mine?.targetImageUrl ?? theirs?.targetImageUrl}
              alt="Target"
            />
          )}
          <figcaption>Target</figcaption>
        </figure>
        {opponent && (
          <Card
            player={opponent}
            round={theirs}
            outcome={gap < 0 ? "won" : gap > 0 ? "lost" : "tied"}
          />
        )}
      </div>
      <button className="link cinema-skip" onClick={onDone}>
        Skip to results
      </button>
    </div>
  );
}
