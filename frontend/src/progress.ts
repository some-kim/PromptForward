import type { Progress } from "./api";

// Rough public estimate for one text-to-image generation, in grams of CO2e.
const GRAMS_PER_GENERATION = 4.2;
// Generations a target would cost without prompt discipline; the unused ones are the saving.
const BASELINE_GENERATIONS = 3;
const XP_PER_LEVEL = 250;

const TITLES = [
  "Novice",
  "Apprentice",
  "Craftsperson",
  "Artisan",
  "Wordsmith",
  "Prompt Master",
];

export type ProgressSummary = Progress & {
  level: number;
  title: string;
  xpIntoLevel: number;
  gramsSaved: number;
};

/** Turns the account's stored totals into the numbers the lobby strip shows. */
export function summarize(progress: Progress): ProgressSummary {
  const level = Math.floor(progress.xp / XP_PER_LEVEL) + 1;
  return {
    ...progress,
    level,
    title: TITLES[Math.min(level - 1, TITLES.length - 1)],
    xpIntoLevel: progress.xp % XP_PER_LEVEL,
    gramsSaved:
      Math.max(
        0,
        progress.attempts * BASELINE_GENERATIONS - progress.generations,
      ) * GRAMS_PER_GENERATION,
  };
}
