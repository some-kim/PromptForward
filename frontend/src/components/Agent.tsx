import { useEffect, useState } from "react";

type AgentProps = {
  name: string;
  lines: string[];
};

const TYPE_MS = 18;
const HOLD_MS = 4500;

export function Agent({ name, lines }: AgentProps) {
  const [index, setIndex] = useState(0);
  // The typed line travels with its own character count, so switching lines restarts typing
  // without a render-time reset.
  const [typing, setTyping] = useState({ line: lines[0] ?? "", count: 0 });

  const line = lines[index] ?? "";
  const typed = typing.line === line ? line.slice(0, typing.count) : "";
  const done = typed.length === line.length;

  useEffect(() => {
    const timer = setInterval(
      () =>
        setTyping((current) =>
          current.line === line
            ? { line, count: Math.min(current.count + 1, line.length) }
            : { line, count: 1 },
        ),
      TYPE_MS,
    );
    return () => clearInterval(timer);
  }, [line]);

  useEffect(() => {
    if (!done || lines.length < 2) return;
    const timer = setTimeout(
      () => setIndex((current) => (current + 1) % lines.length),
      HOLD_MS,
    );
    return () => clearTimeout(timer);
  }, [done, lines.length]);

  return (
    <aside className="agent">
      <span className="agent-bot-wrap">
        <img
          src="/agent.png"
          alt=""
          className={`agent-bot${done ? "" : " talking"}`}
        />
      </span>
      <div className="agent-bubble">
        <span className="agent-name">{name}</span>
        <p aria-live="polite">
          {typed}
          <i className="agent-caret" aria-hidden="true" />
        </p>
      </div>
    </aside>
  );
}
