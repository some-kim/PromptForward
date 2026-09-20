// Decorative circuit traces: each path is drawn twice, once as a dim etched line and once
// as a short cyan dash that runs along it like a current pulse.
const TRACES = [
  "M-20 120 H180 L240 60 H430 L470 100 H720",
  "M-20 300 H120 L170 250 H360 L410 300 H640 L700 240 H1040",
  "M1040 420 H860 L800 480 H520 L470 430 H240 L180 490 H-20",
  "M-20 640 H300 L350 690 H620 L680 630 H1040",
  "M60 -20 V160 L110 210 V420 L60 470 V780",
  "M960 -20 V200 L900 260 V520 L960 580 V780",
];

const PARTICLES = Array.from({ length: 14 }, (_, index) => index);

export function Backdrop() {
  return (
    <div className="backdrop" aria-hidden="true">
      <div className="backdrop-grid" />
      <svg
        className="backdrop-circuit"
        viewBox="0 0 1000 760"
        preserveAspectRatio="xMidYMid slice"
      >
        {TRACES.map((trace) => (
          <path key={trace} className="trace" d={trace} />
        ))}
        {TRACES.map((trace, index) => (
          <path
            key={`pulse-${trace}`}
            className="trace-pulse"
            d={trace}
            style={{ animationDelay: `${index * 1.4}s` }}
          />
        ))}
      </svg>
      <div className="backdrop-particles">
        {PARTICLES.map((index) => (
          <span key={index} className={`particle p${index % 7}`} />
        ))}
      </div>
      <div className="backdrop-scan" />
      <div className="backdrop-scanlines" />
      <div className="backdrop-vignette" />
    </div>
  );
}
