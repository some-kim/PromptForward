import { useEffect, useMemo, useState } from "react";
import type { Battle, BattlePlayer, BattleRound } from "../api";

type Props = {
  battle: Battle;
  onDone: () => void;
};

/** Each round plays out in three beats before the next one starts. */
const BEATS = {
  faceoff: 1600,
  spotlight: 1800,
  scores: 2000,
  drumroll: 2600,
  verdict: 4000,
} as const;

type Beat = keyof typeof BEATS;
type Stage = { beat: Beat; index: number };

function scoreOf(round?: BattleRound): number {
  return Math.round(round?.scores?.final ?? 0);
}

function Card({
  player,
  round,
  beat,
  outcome,
}: {
  player: BattlePlayer;
  round?: BattleRound;
  beat: Beat;
  outcome: "won" | "lost" | "tied";
}) {
  const scored = beat === "scores";
  const judged = beat !== "faceoff";
  return (
    <div
      className={`reveal-card ${player.isYou ? "mine" : "theirs"} ${judged ? outcome : ""}`}
    >
      <div className="reveal-image">
        {round?.imageUrl ? (
          <img src={round.imageUrl} alt={`${player.displayName} result`} />
        ) : (
          <div className="missed">No image</div>
        )}
      </div>
      <span className="who">{player.displayName}</span>
      <span
        key={scored ? "in" : "hidden"}
        className={`score ${scored ? "in" : "hidden"}`}
      >
        {scored ? scoreOf(round) : "??"}
      </span>
    </div>
  );
}

/** The cinematic: images first, then the spotlight, then the scores, then the verdict. */
export function BattleReveal({ battle, onDone }: Props) {
  const me = battle.players.find((player) => player.isYou);
  const opponent = battle.players.find((player) => !player.isYou);
  const outcome = battle.winner ?? "draw";

  const stages = useMemo<Stage[]>(() => {
    const rounds = Array.from({ length: battle.totalRounds }, (_, index) =>
      (["faceoff", "spotlight", "scores"] as Beat[]).map((beat): Stage => ({
        beat,
        index,
      })),
    ).flat();
    return [
      ...rounds,
      { beat: "drumroll", index: -1 },
      { beat: "verdict", index: -1 },
    ];
  }, [battle.totalRounds]);

  const [step, setStep] = useState(0);
  const stage = stages[Math.min(step, stages.length - 1)];

  useEffect(() => {
    const last = step >= stages.length - 1;
    const timer = window.setTimeout(
      () => (last ? onDone() : setStep((current) => current + 1)),
      BEATS[stages[Math.min(step, stages.length - 1)].beat],
    );
    return () => window.clearTimeout(timer);
  }, [step, stages, onDone]);

  const drops = useMemo(
    () =>
      Array.from({ length: 70 }, (_, index) => ({
        left: (index * 37) % 100,
        delay: ((index * 13) % 22) / 10,
        hue: (index * 47) % 360,
      })),
    [],
  );

  if (stage.beat === "drumroll") {
    return (
      <div className="battle-cinema">
        <p className="cinema-step">Tallying the final scores</p>
        <div className="drumroll" aria-hidden="true">
          <span />
          <span />
          <span />
        </div>
        <button className="link cinema-skip" onClick={onDone}>
          Skip to results
        </button>
      </div>
    );
  }

  if (stage.beat === "verdict") {
    return (
      <div className={`battle-cinema finale dark ${outcome}`}>
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
    <div className={`battle-cinema ${stage.beat === "faceoff" ? "" : "dark"}`}>
      <p className="cinema-step">
        Image {stage.index + 1} of {battle.totalRounds}
        {stage.beat === "faceoff" && " · who nailed it?"}
        {stage.beat === "spotlight" && " · the winner is…"}
      </p>
      <div key={stage.index} className="reveal-row">
        {me && (
          <Card
            player={me}
            round={mine}
            beat={stage.beat}
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
            beat={stage.beat}
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
