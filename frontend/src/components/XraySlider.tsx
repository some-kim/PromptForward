import { useState } from "react";

type Props = {
  targetUrl: string;
  resultUrl: string;
};

/** Drag-to-reveal comparison: the target on the left of the handle, your generation on the right. */
export function XraySlider({ targetUrl, resultUrl }: Props) {
  const [position, setPosition] = useState(50);

  return (
    <figure className="xray">
      <figcaption>Target vs your result — drag to compare</figcaption>
      <div className="xray-frame">
        <img src={resultUrl} alt="Your generated result" />
        <div
          className="xray-reveal"
          style={{ clipPath: `inset(0 ${100 - position}% 0 0)` }}
        >
          <img src={targetUrl} alt="Target" />
        </div>
        <div
          className="xray-handle"
          style={{ left: `${position}%` }}
          aria-hidden="true"
        />
        <input
          type="range"
          min={0}
          max={100}
          value={position}
          aria-label="Reveal target versus result"
          onChange={(event) => setPosition(Number(event.target.value))}
        />
      </div>
      <div className="xray-legend">
        <span>Target</span>
        <span>Your result</span>
      </div>
    </figure>
  );
}
