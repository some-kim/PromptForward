import { useEffect } from "react";
import { LogoMark } from "./LogoMark";

const SPLASH_MS = 1600;

export function Splash({ onDone }: { onDone: () => void }) {
  useEffect(() => {
    const timer = setTimeout(onDone, SPLASH_MS);
    return () => clearTimeout(timer);
  }, [onDone]);

  return (
    <div className="splash" onClick={onDone}>
      <div className="splash-inner">
        <LogoMark />
        <h1 className="logo">
          <span>
            Prompt<span className="logo-accent">Forward</span>
          </span>
        </h1>
        <p>Write better prompts with fewer wasted generations.</p>
      </div>
    </div>
  );
}
