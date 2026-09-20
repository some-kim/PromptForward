import { useEffect, useState } from "react";

type AgentProps = {
  name: string;
  lines: string[];
};

const LINE_MS = 6000;

export function Agent({ name, lines }: AgentProps) {
  const [index, setIndex] = useState(0);

  // Remounted per screen by the caller, so the rotation always starts at the first line.
  useEffect(() => {
    if (lines.length < 2) return;
    const timer = setInterval(
      () => setIndex((current) => (current + 1) % lines.length),
      LINE_MS,
    );
    return () => clearInterval(timer);
  }, [lines]);

  return (
    <aside className="agent">
      <img src="/agent.png" alt="" className="agent-bot" />
      <div className="agent-bubble" key={index}>
        <span className="agent-name">{name}</span>
        <p>{lines[index]}</p>
      </div>
    </aside>
  );
}
