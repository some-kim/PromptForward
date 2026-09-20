import { useEffect, useState } from "react";
import { api, type HeadToHead, type Standings } from "../api";

type Props = { playerId: string };

function streakLabel(current: number, best: number) {
  if (current > 0) return `W${current} streak`;
  return best > 0 ? `best W${best}` : "—";
}

function record(one: HeadToHead) {
  return `${one.wins}-${one.losses}${one.draws ? `-${one.draws}` : ""}`;
}

/** The series so far against the player just battled, read after the result is in. */
export function BattleSeries({
  playerId,
  opponent,
}: Props & { opponent: string }) {
  const [standings, setStandings] = useState<Standings | null>(null);

  useEffect(() => {
    let live = true;
    api
      .getStandings(playerId)
      .then((next) => live && setStandings(next))
      .catch(() => undefined);
    return () => {
      live = false;
    };
  }, [playerId]);

  const series = standings?.headToHead.find((one) => one.opponent === opponent);
  if (!standings?.you || !series) return null;

  return (
    <p className="series">
      <span>
        vs {opponent} <strong>{record(series)}</strong>
      </span>
      <span>
        {streakLabel(standings.you.currentStreak, standings.you.bestStreak)}
      </span>
    </p>
  );
}

export function BattleStandings({ playerId }: Props) {
  const [standings, setStandings] = useState<Standings | null>(null);
  const [failed, setFailed] = useState(false);

  useEffect(() => {
    let live = true;
    api
      .getStandings(playerId)
      .then((next) => live && setStandings(next))
      .catch(() => live && setFailed(true));
    return () => {
      live = false;
    };
  }, [playerId]);

  if (failed || !standings) return null;

  const { leaderboard, you, headToHead } = standings;
  if (leaderboard.length === 0) return null;

  return (
    <div className="standings">
      <div className="standings-card">
        <h3>Leaderboard</h3>
        <table className="standings-table">
          <thead>
            <tr>
              <th>#</th>
              <th>Player</th>
              <th>W–L</th>
              <th>Win %</th>
              <th>Avg</th>
              <th>Streak</th>
            </tr>
          </thead>
          <tbody>
            {leaderboard.map((entry) => (
              <tr
                key={`${entry.rank}-${entry.displayName}`}
                className={entry.isYou ? "is-you" : undefined}
              >
                <td>{entry.rank}</td>
                <td>{entry.displayName}</td>
                <td>
                  {entry.wins}–{entry.losses}
                  {entry.draws > 0 ? `–${entry.draws}` : ""}
                </td>
                <td>{entry.winRate}%</td>
                <td>{entry.averageScore}</td>
                <td>{streakLabel(entry.currentStreak, entry.bestStreak)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      <div className="standings-card">
        <h3>Head to head</h3>
        {you && (
          <p className="hint">
            {you.wins}–{you.losses}
            {you.draws > 0 ? `–${you.draws}` : ""} overall ·{" "}
            {streakLabel(you.currentStreak, you.bestStreak)}
          </p>
        )}
        {headToHead.length === 0 ? (
          <p className="hint">
            No battles yet — host one and read out the code.
          </p>
        ) : (
          <ul className="head-to-head">
            {headToHead.map((one) => (
              <li key={one.opponent}>
                <span className="opponent">vs {one.opponent}</span>
                <span
                  className={`h2h-record ${
                    one.wins > one.losses
                      ? "leading"
                      : one.wins < one.losses
                        ? "trailing"
                        : "level"
                  }`}
                >
                  {record(one)}
                </span>
              </li>
            ))}
          </ul>
        )}
      </div>
    </div>
  );
}
