import { getToken } from "./session";

export const DIFFICULTIES = ["easy", "medium", "hard"] as const;

export type Difficulty = (typeof DIFFICULTIES)[number];

export const SKILLS = [
  "subject",
  "attributes",
  "setting",
  "lighting",
  "style",
  "composition",
  "multi_subject",
  "concision",
] as const;

export type Skill = (typeof SKILLS)[number];

export type ProblemTag = {
  slug: string;
  title: string;
  skill: Skill;
  skillTitle: string;
  order: number;
};

export type Challenge = {
  id: string;
  type: string;
  difficulty: Difficulty;
  imageUrl: string;
  width?: number;
  height?: number;
  problem?: ProblemTag | null;
};

export type ProblemStatus = "unsolved" | "attempted" | "solved";

export type Problem = ProblemTag & {
  id: string;
  lesson: string;
  tests: string;
  difficulty: Difficulty;
  imageUrl: string;
  hintCount: number;
  status: ProblemStatus;
  bestScore: number | null;
  attempts: number;
};

export type SkillSummary = {
  skill: Skill;
  title: string;
  lesson: string;
  total: number;
  solved: number;
  attempted: number;
};

export type ProblemSet = { problems: Problem[]; skills: SkillSummary[] };

// What the coach has released for one attempt: hints unlock per weak prompt, the reference
// prompt once the problem is solved or every generation is spent.
export type Coaching = {
  slug: string;
  title: string;
  skill: Skill;
  skillTitle: string;
  lesson: string;
  tests: string;
  hints: string[];
  hintsRemaining: number;
  solved: boolean;
  referencePrompt: string | null;
};

export type AttentionRegion = {
  id: string;
  status: "covered" | "partial" | "missing";
  category: string;
  hint: string;
  weight: number;
  region: { x: number; y: number; width: number; height: number };
};

export type PromptEvaluation = {
  promptQuality: number;
  targetCoverage: number;
  craftsmanship: number;
  passed: boolean;
  feedback: string;
  needsImprovement: string[];
  attention?: AttentionRegion[];
  promptTokens: number | null;
  generationsRemaining?: number;
  coaching?: Coaching | null;
};

export type Generation = {
  number: number;
  prompt: string;
  imageUrl: string;
  promptQuality: number | null;
  resultQuality: number | null;
  resultFeedback: string | null;
  promptTokens: number;
};

export type Scores = {
  resultQuality: number | null;
  promptQuality: number | null;
  efficiency: number | null;
  final: number | null;
};

export type Attempt = {
  id: string;
  challengeId: string;
  gameId: string | null;
  displayName: string | null;
  mode: "learning" | "game";
  status: "in_progress" | "submitted";
  latestEvaluation: PromptEvaluation | null;
  generations?: Generation[];
  generationsRemaining?: number;
  selectedGeneration?: number | null;
  scores?: Scores;
  usage?: {
    promptTokens: number;
    promptEvaluations: number;
    generations: number;
  };
  coaching?: Coaching | null;
};

export type Game = {
  id: string;
  challengeId: string;
  status: "waiting" | "active" | "completed";
  winner: "you" | "opponent" | "draw" | null;
  players: { isYou: boolean; displayName: string; attempt: Attempt }[];
};

export type Progress = {
  xp: number;
  attempts: number;
  generations: number;
  streak: number;
  lastPlayedDay: string | null;
};

export type User = {
  id: string;
  username: string;
  displayName: string;
  progress: Progress;
};

export type Session = { token: string; user: User };

export class ApiError extends Error {
  status: number;

  constructor(status: number, message: string) {
    super(message);
    this.status = status;
  }
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const token = getToken();
  const response = await fetch(path, {
    ...init,
    headers: {
      "Content-Type": "application/json",
      ...(token ? { Authorization: `Bearer ${token}` } : {}),
      ...init?.headers,
    },
  });
  if (!response.ok) {
    const body = await response.json().catch(() => ({}));
    throw new ApiError(response.status, body.detail ?? response.statusText);
  }
  if (response.status === 204) return undefined as T;
  return response.json() as Promise<T>;
}

export const api = {
  signUp: (username: string, password: string, displayName: string) =>
    request<Session>("/api/auth/signup", {
      method: "POST",
      body: JSON.stringify({ username, password, displayName }),
    }),

  logIn: (username: string, password: string) =>
    request<Session>("/api/auth/login", {
      method: "POST",
      body: JSON.stringify({ username, password }),
    }),

  logOut: () => request<void>("/api/auth/logout", { method: "POST" }),

  me: () => request<User>("/api/auth/me"),

  // Keyed by attempt: reporting the same attempt twice adjusts it instead of counting it twice.
  addProgress: (attemptId: string, score: number, generations: number) =>
    request<Progress>("/api/auth/progress", {
      method: "POST",
      keepalive: true,
      body: JSON.stringify({ attemptId, score, generations }),
    }),

  listChallenges: (difficulty?: Difficulty) =>
    request<Challenge[]>(
      difficulty
        ? `/api/challenges?difficulty=${difficulty}`
        : "/api/challenges",
    ),

  listProblems: () => request<ProblemSet>("/api/problems"),

  createLearningAttempt: (
    challengeId: string,
    userId: string,
    displayName: string,
  ) =>
    request<Attempt>("/api/learning/attempts", {
      method: "POST",
      body: JSON.stringify({ challengeId, userId, displayName }),
    }),

  evaluatePrompt: (attemptId: string, prompt: string) =>
    request<PromptEvaluation>(`/api/learning/attempts/${attemptId}/evaluate`, {
      method: "POST",
      body: JSON.stringify({ prompt }),
    }),

  generateLearningImage: (attemptId: string, prompt: string) =>
    request<Attempt>(`/api/learning/attempts/${attemptId}/generate`, {
      method: "POST",
      body: JSON.stringify({ prompt }),
    }),

  createGame: (
    userId: string,
    displayName: string,
    challengeId?: string,
    difficulty?: Difficulty,
  ) =>
    request<Game>("/api/games", {
      method: "POST",
      body: JSON.stringify({ userId, displayName, challengeId, difficulty }),
    }),

  joinGame: (gameId: string, userId: string, displayName: string) =>
    request<Game>(`/api/games/${gameId}/join`, {
      method: "POST",
      body: JSON.stringify({ userId, displayName }),
    }),

  getGame: (gameId: string, userId: string) =>
    request<Game>(`/api/games/${gameId}?userId=${encodeURIComponent(userId)}`),

  generateGameImage: (gameId: string, userId: string, prompt: string) =>
    request<Game>(`/api/games/${gameId}/generate`, {
      method: "POST",
      body: JSON.stringify({ userId, prompt }),
    }),
};
