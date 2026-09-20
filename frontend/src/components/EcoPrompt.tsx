import { footprint, trimFiller } from "../eco";

type Props = {
  prompt: string;
  onChange: (value: string) => void;
  disabled?: boolean;
};

export function EcoPrompt({ prompt, onChange, disabled }: Props) {
  const cost = footprint(prompt);
  const trimmed = trimFiller(prompt);
  const saved = cost.tokens - footprint(trimmed).tokens;

  return (
    <aside className="eco">
      <h3>
        EcoPrompt
        <svg viewBox="0 0 24 24" aria-hidden="true">
          <path
            d="M20 4c0 9-5 13-11 13-2 0-4-1-4-1s1-9 9-10c3-.4 6-2 6-2z"
            fill="var(--green)"
          />
          <path
            d="M5 20c1-6 5-9 10-11"
            fill="none"
            stroke="var(--green)"
            strokeWidth="1.6"
            strokeLinecap="round"
          />
        </svg>
      </h3>
      <dl>
        <div>
          <dt>Tokens</dt>
          <dd>{cost.tokens}</dd>
        </div>
        <div>
          <dt>Energy</dt>
          <dd>{cost.energyMilliWattHours.toFixed(0)} mWh</dd>
        </div>
        <div>
          <dt>Emissions</dt>
          <dd>{cost.co2Milligrams.toFixed(2)} mg CO₂</dd>
        </div>
      </dl>
      <p className="eco-equivalents">
        ≈ {cost.phoneChargePercent.toFixed(1)}% phone charge · ≈{" "}
        {cost.bulbSeconds.toFixed(0)} s (60W) · ≈ {cost.searches.toFixed(1)}{" "}
        searches
      </p>
      <button
        className="secondary"
        disabled={disabled || saved <= 0}
        onClick={() => onChange(trimmed)}
      >
        Trim filler
      </button>
      <p className="hint">
        {saved > 0
          ? `Cuts ${saved} token${saved === 1 ? "" : "s"} of hype words.`
          : "Nothing to trim."}
      </p>
    </aside>
  );
}
