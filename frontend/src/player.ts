import { DIFFICULTIES, type Difficulty } from "./api";

const DIFFICULTY_KEY = "promptforward.difficulty";

export function getDifficulty(): Difficulty {
  const stored = localStorage.getItem(DIFFICULTY_KEY);
  return DIFFICULTIES.find((level) => level === stored) ?? "easy";
}

export function setDifficulty(difficulty: Difficulty): void {
  localStorage.setItem(DIFFICULTY_KEY, difficulty);
}
