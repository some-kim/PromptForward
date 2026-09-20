import type { ProgressSummary } from '../progress'

function formatSaved(grams: number): string {
  return grams >= 1000 ? `${(grams / 1000).toFixed(1)}kg` : `${grams.toFixed(1)}g`
}

const ICONS = {
  streak: 'M12 3c1 3.5-1.5 4.5-1.5 7a3.5 3.5 0 0 0 7 0c0-1-.3-2-1-3 2.5 1.7 4 4 4 6.5a8.5 8.5 0 1 1-17 0C3.5 8 8 6 12 3z',
  eco: 'M20 4C10 4 4 9 4 16c0 1.5.4 3 1 4M5 19C5 10 12 7 20 4c0 9-4 15-11 15-1.6 0-3-.3-4-1z',
  level:
    'M7 4h10v4a5 5 0 0 1-10 0zM7 6H4v2a4 4 0 0 0 3 3.9M17 6h3v2a4 4 0 0 1-3 3.9M9 20h6M12 13v7',
} as const

function StatIcon({ name }: { name: keyof typeof ICONS }) {
  return (
    <svg className="stat-icon" viewBox="0 0 24 24" aria-hidden="true">
      <path
        d={ICONS[name]}
        fill="none"
        stroke="currentColor"
        strokeWidth="2"
        strokeLinecap="round"
        strokeLinejoin="round"
      />
    </svg>
  )
}

export function StatStrip({ progress }: { progress: ProgressSummary }) {
  return (
    <div className="stat-strip">
      <span className="stat streak" title="Days in a row you have played">
        <StatIcon name="streak" />
        {progress.streak} day streak
      </span>
      <span
        className="stat eco"
        title="CO₂e avoided by not burning extra image generations"
      >
        <StatIcon name="eco" />
        {formatSaved(progress.gramsSaved)} CO₂ saved
      </span>
      <span
        className="stat level"
        title={`${progress.xpIntoLevel}/250 XP to the next level`}
      >
        <StatIcon name="level" />
        Lvl {progress.level}: {progress.title}
      </span>
    </div>
  )
}
