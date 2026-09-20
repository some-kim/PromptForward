import { getToken } from "./session";

export const DIFFICULTIES = ["easy", "medium", "hard"] as const;

export type Difficulty = (typeof DIFFICULTIES)[number];

export type Challenge = {
  id: string;
  type: string;
  difficulty: Difficulty;
  imageUrl: string;
  width?: number;
  height?: number;
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
};

export type BattleSettings = {
  durationSeconds: number;
  imagesPerPlayer: number;
};

export const BATTLE_LIMITS = {
  durationSeconds: { min: 60, max: 600, step: 60, default: 180 },
  imagesPerPlayer: { min: 2, max: 7, default: 3 },
} as const;

export type RoundScores = {
  final: number;
  resultQuality: number;
  promptQuality: number;
  efficiency: number;
};

/** One image, for one player. Scores and the generated image only arrive once the battle ends. */
export type BattleRound = {
  index: number;
  challengeId: string;
  targetImageUrl: string;
  status: "empty" | "working" | "ready" | "failed";
  prompt: string | null;
  error: string | null;
  attemptId?: string;
  imageUrl?: string | null;
  scores?: RoundScores;
  feedback?: string | null;
  promptTokens?: number;
};

export type BattlePlayer = {
  isYou: boolean;
  displayName: string;
  imagesChosen: number;
  usedDefaults: boolean;
  ready: boolean;
  submittedRounds: number;
  total: number | null;
  promptTokens: number | null;
  images: { challengeId: string; imageUrl: string }[];
  rounds: BattleRound[];
};

export type Battle = {
  id: string;
  code: string;
  status: "waiting" | "active" | "completed";
  settings: BattleSettings;
  totalRounds: number;
  secondsRemaining: number | null;
  winner: "you" | "opponent" | "draw" | null;
  players: BattlePlayer[];
};

export type LibraryImage = {
  id: string;
  type: string;
  difficulty: Difficulty;
  imageUrl: string;
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
  const isForm = init?.body instanceof FormData;
  const response = await fetch(path, {
    ...init,
    headers: {
      ...(isForm ? {} : { "Content-Type": "application/json" }),
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

  createBattle: (
    userId: string,
    displayName: string,
    settings: BattleSettings,
    useDefaultImages: boolean,
  ) =>
    request<Battle>("/api/games", {
      method: "POST",
      body: JSON.stringify({ userId, displayName, settings, useDefaultImages }),
    }),

  joinBattle: (code: string, userId: string, displayName: string) =>
    request<Battle>("/api/games/join", {
      method: "POST",
      body: JSON.stringify({ code, userId, displayName }),
    }),

  getBattle: (battleId: string, userId: string) =>
    request<Battle>(
      `/api/games/${battleId}?userId=${encodeURIComponent(userId)}`,
    ),

  addBattleImage: (battleId: string, userId: string, challengeId: string) =>
    request<Battle>(`/api/games/${battleId}/images`, {
      method: "POST",
      body: JSON.stringify({ userId, challengeId }),
    }),

  removeBattleImage: (battleId: string, userId: string, challengeId: string) =>
    request<Battle>(
      `/api/games/${battleId}/images/${challengeId}?userId=${encodeURIComponent(userId)}`,
      { method: "DELETE" },
    ),

  fillBattleWithDefaults: (battleId: string, userId: string) =>
    request<Battle>(`/api/games/${battleId}/default-images`, {
      method: "POST",
      body: JSON.stringify({ userId }),
    }),

  promptBattleRound: (
    battleId: string,
    userId: string,
    index: number,
    prompt: string,
  ) =>
    request<Battle>(`/api/games/${battleId}/rounds/${index}/prompt`, {
      method: "POST",
      body: JSON.stringify({ userId, prompt }),
    }),

  listLibraryImages: (userId: string) =>
    request<LibraryImage[]>(
      `/api/library/images?userId=${encodeURIComponent(userId)}`,
    ),

  uploadLibraryImage: (userId: string, file: File) => {
    const body = new FormData();
    body.append("userId", userId);
    body.append("image", file);
    // No Content-Type here: the browser has to set the multipart boundary itself.
    return request<LibraryImage>("/api/library/images", {
      method: "POST",
      body,
    });
  },

  deleteLibraryImage: (userId: string, challengeId: string) =>
    request<void>(
      `/api/library/images/${challengeId}?userId=${encodeURIComponent(userId)}`,
      { method: "DELETE" },
    ),
};
