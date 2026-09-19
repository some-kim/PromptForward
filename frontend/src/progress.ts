const PROGRESS_KEY = "promptforward.progress";

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

export type Progress = {
  xp: number;
  attempts: number;
  generations: number;
  streak: number;
  lastPlayedDay: string | null;
};

export type ProgressSummary = Progress & {
  level: number;
  title: string;
  xpIntoLevel: number;
  gramsSaved: number;
};

const EMPTY: Progress = {
  xp: 0,
  attempts: 0,
  generations: 0,
  streak: 0,
  lastPlayedDay: null,
};

function today(): string {
  return new Date().toISOString().slice(0, 10);
}

function dayBefore(day: string): string {
  const date = new Date(`${day}T00:00:00Z`);
  date.setUTCDate(date.getUTCDate() - 1);
  return date.toISOString().slice(0, 10);
}

function read(): Progress {
  try {
    const stored = localStorage.getItem(PROGRESS_KEY);
    if (!stored) return EMPTY;
    return { ...EMPTY, ...(JSON.parse(stored) as Partial<Progress>) };
  } catch {
    return EMPTY;
  }
}

function summarize(progress: Progress): ProgressSummary {
  const level = Math.floor(progress.xp / XP_PER_LEVEL) + 1;
  return {
    ...progress,
    level,
    title: TITLES[Math.min(level - 1, TITLES.length - 1)],
    xpIntoLevel: progress.xp % XP_PER_LEVEL,
    gramsSaved: Math.max(
      0,
      progress.attempts * BASELINE_GENERATIONS - progress.generations,
    ) * GRAMS_PER_GENERATION,
  };
}

export function getProgress(): ProgressSummary {
  return summarize(read());
}

/** Records one finished attempt and returns the updated summary. */
export function recordAttempt(score: number, generations: number): ProgressSummary {
  const previous = read();
  const day = today();
  const streak =
    previous.lastPlayedDay === day
      ? Math.max(previous.streak, 1)
      : previous.lastPlayedDay === dayBefore(day)
        ? previous.streak + 1
        : 1;

  const next: Progress = {
    xp: previous.xp + Math.max(0, Math.round(score)),
    attempts: previous.attempts + 1,
    generations: previous.generations + Math.max(1, generations),
    streak,
    lastPlayedDay: day,
  };
  localStorage.setItem(PROGRESS_KEY, JSON.stringify(next));
  return summarize(next);
}
