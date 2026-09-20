import { useEffect, useState } from "react";
import {
  api,
  type MatchRecord,
  type Standings,
  type StandingsEntry,
} from "../api";

type Props = { playerId: string };

const RESULT_LABEL = { win: "Won", loss: "Lost", draw: "Drew" } as const;

/** The run they are on now, signed by which way it is going: +3, -2, D1. */
function streakLabel({ streak }: StandingsEntry) {
  if (!streak.result) return "—";
  if (streak.result === "draw") return `D${streak.length} streak`;
  const sign = streak.result === "win" ? "+" : "-";
  return `${sign}${streak.length} streak`;
}

function overall(you: StandingsEntry) {
  return `${you.wins}–${you.losses}${you.draws > 0 ? `–${you.draws}` : ""}`;
}

function playedOn(match: MatchRecord) {
  if (!match.playedAt) return "";
  return new Date(match.playedAt).toLocaleDateString(undefined, {
    month: "short",
    day: "numeric",
  });
}

function useStandings(playerId: string) {
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

  return failed ? null : standings;
}

/** The viewer's record so far, read on the results screen once the battle is in. */
export function BattleSeries({ playerId }: Props) {
  const standings = useStandings(playerId);
  const you = standings?.you;
  if (!you) return null;

  return (
    <p className="series">
      <span>
        Record <strong>{overall(you)}</strong>
      </span>
      <span>{streakLabel(you)}</span>
    </p>
  );
}

export function BattleStandings({ playerId }: Props) {
  const standings = useStandings(playerId);
  if (!standings) return null;

  const { leaderboard, you, matches } = standings;
  if (leaderboard.length === 0) return null;

  return (
    <div className="standings">
      <div className="standings-card">
        <h3>Leaderboard</h3>
        <div className="standings-scroll">
          <table className="standings-table">
            <thead>
              <tr>
                <th>#</th>
                <th>Player</th>
                <th>W–L</th>
                <th className="col-rate">Win %</th>
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
                  <td className="player">{entry.displayName}</td>
                  <td>
                    {entry.wins}–{entry.losses}
                    {entry.draws > 0 ? `–${entry.draws}` : ""}
                  </td>
                  <td className="col-rate">{entry.winRate}%</td>
                  <td>{entry.averageScore}</td>
                  <td className={`streak ${entry.streak.result ?? ""}`}>
                    {streakLabel(entry)}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>

      <div className="standings-card">
        <h3>Match history</h3>
        {you && (
          <p className="hint">
            {overall(you)} overall · {streakLabel(you)}
          </p>
        )}
        {matches.length === 0 ? (
          <p className="hint">
            No battles yet — host one and read out the code.
          </p>
        ) : (
          <ul className="match-history">
            {matches.map((match, index) => (
              <li key={`${match.playedAt ?? index}-${match.opponent}`}>
                <span className={`outcome ${match.result}`}>
                  {RESULT_LABEL[match.result]}
                </span>
                <span className="opponent">vs {match.opponent}</span>
                <span className="match-score">
                  {match.yourScore}–{match.theirScore}
                </span>
                <span className="played">{playedOn(match)}</span>
              </li>
            ))}
          </ul>
        )}
      </div>
    </div>
  );
}
