export function LogoMark() {
  return (
    <svg
      className="logo-mark"
      viewBox="0 0 64 64"
      role="img"
      aria-label="PromptForward logo"
    >
      <rect x="4" y="10" width="46" height="40" fill="var(--violet)" />
      <rect
        x="4"
        y="10"
        width="46"
        height="40"
        fill="none"
        stroke="var(--text)"
        strokeWidth="3"
      />
      <path
        className="logo-arrow"
        d="M15 30h14V20l14 10-14 10V30z"
        fill="#fff"
      />
      <rect x="50" y="24" width="10" height="10" fill="var(--spark)" />
      <rect
        x="50"
        y="24"
        width="10"
        height="10"
        fill="none"
        stroke="var(--text)"
        strokeWidth="3"
      />
    </svg>
  );
}
