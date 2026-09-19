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
        EcoPrompt <span aria-hidden="true">🌱</span>
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
