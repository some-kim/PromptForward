export function LogoMark() {
  return (
    <svg
      className="logo-mark"
      viewBox="0 0 64 64"
      role="img"
      aria-label="PromptForward logo"
    >
      <rect x="6" y="6" width="52" height="52" rx="4" fill="var(--violet)" />
      <path
        className="logo-arrow"
        d="M18 32h20M30 22l12 10-12 10"
        fill="none"
        stroke="#fff"
        strokeWidth="6"
        strokeLinecap="square"
        strokeLinejoin="miter"
      />
    </svg>
  );
}
