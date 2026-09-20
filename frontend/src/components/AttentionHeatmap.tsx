import { useState } from "react";
import type { AttentionRegion } from "../api";

type Props = {
  imageUrl: string;
  regions: AttentionRegion[];
};

const LABEL: Record<AttentionRegion["status"], string> = {
  covered: "covered",
  partial: "partly covered",
  missing: "missing",
};

/** The target image with a box per rubric criterion: green where the prompt landed, red where it missed. */
export function AttentionHeatmap({ imageUrl, regions }: Props) {
  const [active, setActive] = useState<string | null>(null);

  return (
    <div className="image-row">
      <figure className="heatmap">
        <figcaption>Target — where your prompt landed</figcaption>
        <div className="heatmap-frame">
          <img src={imageUrl} alt="Target" />
          {regions.map((entry) => (
            <button
              key={entry.id}
              type="button"
              className={`heatmap-box ${entry.status}${active === entry.id ? " active" : ""}`}
              style={{
                left: `${entry.region.x * 100}%`,
                top: `${entry.region.y * 100}%`,
                width: `${Math.min(entry.region.width, 1 - entry.region.x) * 100}%`,
                height: `${Math.min(entry.region.height, 1 - entry.region.y) * 100}%`,
              }}
              title={`${entry.hint} — ${LABEL[entry.status]}`}
              aria-label={`${entry.hint} — ${LABEL[entry.status]}`}
              onFocus={() => setActive(entry.id)}
              onBlur={() => setActive(null)}
              onMouseEnter={() => setActive(entry.id)}
              onMouseLeave={() => setActive(null)}
            />
          ))}
        </div>
        <ul className="heatmap-legend">
          {regions.map((entry) => (
            <li
              key={entry.id}
              className={`${entry.status}${active === entry.id ? " active" : ""}`}
              onMouseEnter={() => setActive(entry.id)}
              onMouseLeave={() => setActive(null)}
            >
              {entry.hint}
            </li>
          ))}
        </ul>
      </figure>
    </div>
  );
}
