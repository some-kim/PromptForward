import { useState } from "react";
import type { Battle, BattlePlayer, BattleRound } from "../api";
import { prefersReducedMotion } from "../motion";
import { BattleReveal } from "./BattleReveal";
import { BattleSeries } from "./BattleStandings";

type Props = {
  battle: Battle;
  playerId: string;
  onRematch: () => void;
  onExit: () => void;
};

const BANNER: Record<NonNullable<Battle["winner"]>, string> = {
  you: "VICTORY",
  opponent: "DEFEAT",
  draw: "DEAD HEAT",
};

function Side({
  player,
  round,
}: {
  player: BattlePlayer;
  round?: BattleRound;
}) {
  return (
    <div className={`side ${player.isYou ? "mine" : "theirs"}`}>
      <div className="side-image">
        {round?.imageUrl ? (
          <img src={round.imageUrl} alt={`${player.displayName} result`} />
        ) : (
          <div className="missed">No image</div>
        )}
      </div>
      <div className="side-scores">
        <span className="who">{player.displayName}</span>
        <span className="score">{Math.round(round?.scores?.final ?? 0)}</span>
        <dl>
          <div>
            <dt>Match</dt>
            <dd>{Math.round(round?.scores?.resultQuality ?? 0)}</dd>
          </div>
          <div>
            <dt>Prompt</dt>
            <dd>{Math.round(round?.scores?.promptQuality ?? 0)}</dd>
          </div>
          <div>
            <dt>Efficiency</dt>
            <dd>{Math.round(round?.scores?.efficiency ?? 0)}</dd>
          </div>
        </dl>
        {round?.prompt && <p className="prompt-text">{round.prompt}</p>}
      </div>
    </div>
  );
}

export function BattleResults({ battle, playerId, onRematch, onExit }: Props) {
  const me = battle.players.find((player) => player.isYou);
  const opponent = battle.players.find((player) => !player.isYou);
  const outcome = battle.winner ?? "draw";
  const indexes = Array.from({ length: battle.totalRounds }, (_, i) => i);
  const [revealed, setRevealed] = useState(prefersReducedMotion());

  if (!revealed) {
    return <BattleReveal battle={battle} onDone={() => setRevealed(true)} />;
  }

  return (
    <div className={`battle-results ${outcome}`}>
      <div className="verdict">
        <h2>{BANNER[outcome]}</h2>
        <div className="totals">
          {battle.players.map((player) => (
            <div
              key={player.displayName}
              className={`total ${player.isYou === (outcome === "you") && outcome !== "draw" ? "won" : ""}`}
            >
              <span className="who">{player.displayName}</span>
              <span className="points">{Math.round(player.total ?? 0)}</span>
              <span className="tokens">{player.promptTokens ?? 0} tokens</span>
            </div>
          ))}
        </div>
        {opponent && (
          <BattleSeries playerId={playerId} opponent={opponent.displayName} />
        )}
      </div>

      <div className="round-results">
        {indexes.map((index) => {
          const mine = me?.rounds[index];
          const theirs = opponent?.rounds[index];
          const target = mine?.targetImageUrl ?? theirs?.targetImageUrl;
          return (
            <section key={index} className="round-result">
              <figure className="target">
                <figcaption>Image {index + 1}</figcaption>
                {target && <img src={target} alt="Target" />}
              </figure>
              {me && <Side player={me} round={mine} />}
              {opponent && <Side player={opponent} round={theirs} />}
            </section>
          );
        })}
      </div>

      <div className="setup-actions">
        <button className="primary" onClick={onRematch}>
          New battle
        </button>
        <button onClick={onExit}>Leave</button>
      </div>
    </div>
  );
}
