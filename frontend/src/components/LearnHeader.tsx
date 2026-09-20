export type LearnTab = "problems" | "random";

const TABS: { id: LearnTab; label: string }[] = [
  { id: "problems", label: "Problem Set" },
  { id: "random", label: "Random practice" },
];

type Props = {
  tab: LearnTab;
  onTab: (tab: LearnTab) => void;
  onExit: () => void;
};

export function LearnHeader({ tab, onTab, onExit }: Props) {
  return (
    <header className="mode-header learn-header">
      <h2>Learn</h2>
      <nav className="learn-tabs" aria-label="Learn mode">
        {TABS.map((entry) => (
          <button
            key={entry.id}
            className={`tab ${tab === entry.id ? "selected" : ""}`}
            aria-current={tab === entry.id ? "page" : undefined}
            onClick={() => onTab(entry.id)}
          >
            {entry.label}
          </button>
        ))}
      </nav>
      <button className="link" onClick={onExit}>
        ← Home
      </button>
    </header>
  );
}
