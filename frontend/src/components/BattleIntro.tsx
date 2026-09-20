import { useEffect, useState } from "react";

type Props = {
  you: string;
  opponent: string;
  totalRounds: number;
  onDone: () => void;
};

const BANNER_MS = 1400;
const TICK_MS = 700;
const MARKS = ["3", "2", "1", "PROMPT!"];

/** The drop-in before the clock starts: who you are facing, then a countdown. */
export function BattleIntro({ you, opponent, totalRounds, onDone }: Props) {
  const [mark, setMark] = useState(-1);

  useEffect(() => {
    const timers = [
      ...MARKS.map((_, index) =>
        window.setTimeout(() => setMark(index), BANNER_MS + index * TICK_MS),
      ),
      window.setTimeout(onDone, BANNER_MS + MARKS.length * TICK_MS),
    ];
    return () => timers.forEach(window.clearTimeout);
  }, [onDone]);

  return (
    <div className="battle-intro" role="dialog" aria-label="Battle starting">
      <div className="intro-versus">
        <span className="fighter mine">{you}</span>
        <span className="versus">VS</span>
        <span className="fighter theirs">{opponent}</span>
      </div>
      <p className="intro-stakes">
        {totalRounds} images · one prompt each · scores sealed
      </p>
      {mark >= 0 && (
        <div
          key={mark}
          className={`intro-count ${mark === MARKS.length - 1 ? "go" : ""}`}
        >
          {MARKS[mark]}
        </div>
      )}
      <button className="link intro-skip" onClick={onDone}>
        Skip
      </button>
    </div>
  );
}
