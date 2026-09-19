export type Challenge = {
  id: string
  type: string
  imageUrl: string
  width?: number
  height?: number
}

export type PromptEvaluation = {
  promptQuality: number
  targetCoverage: number
  craftsmanship: number
  passed: boolean
  feedback: string
  needsImprovement: string[]
  promptTokens: number | null
  generationsRemaining?: number
}

export type Generation = {
  number: number
  prompt: string
  imageUrl: string
  promptQuality: number | null
  resultQuality: number | null
  resultFeedback: string | null
  promptTokens: number
}

export type Scores = {
  resultQuality: number | null
  promptQuality: number | null
  efficiency: number | null
  final: number | null
}

export type Attempt = {
  id: string
  challengeId: string
  gameId: string | null
  userId: string
  displayName: string | null
  mode: 'learning' | 'game'
  status: 'in_progress' | 'submitted'
  latestEvaluation: PromptEvaluation | null
  generations?: Generation[]
  generationsRemaining?: number
  selectedGeneration?: number | null
  scores?: Scores
  usage?: { promptTokens: number; promptEvaluations: number; generations: number }
}

export type Game = {
  id: string
  challengeId: string
  status: 'waiting' | 'active' | 'completed'
  winnerUserId: string | null
  players: { userId: string; displayName: string; attempt: Attempt }[]
}

export class ApiError extends Error {
  status: number

  constructor(status: number, message: string) {
    super(message)
    this.status = status
  }
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(path, {
    ...init,
    headers: { 'Content-Type': 'application/json', ...init?.headers },
  })
  if (!response.ok) {
    const body = await response.json().catch(() => ({}))
    throw new ApiError(response.status, body.detail ?? response.statusText)
  }
  return response.json() as Promise<T>
}

export const api = {
  listChallenges: () => request<Challenge[]>('/api/challenges'),

  createLearningAttempt: (challengeId: string, userId: string, displayName: string) =>
    request<Attempt>('/api/learning/attempts', {
      method: 'POST',
      body: JSON.stringify({ challengeId, userId, displayName }),
    }),

  evaluatePrompt: (attemptId: string, prompt: string) =>
    request<PromptEvaluation>(`/api/learning/attempts/${attemptId}/evaluate`, {
      method: 'POST',
      body: JSON.stringify({ prompt }),
    }),

  generateLearningImage: (attemptId: string, prompt: string) =>
    request<Attempt>(`/api/learning/attempts/${attemptId}/generate`, {
      method: 'POST',
      body: JSON.stringify({ prompt }),
    }),

  createGame: (userId: string, displayName: string, challengeId?: string) =>
    request<Game>('/api/games', {
      method: 'POST',
      body: JSON.stringify({ userId, displayName, challengeId }),
    }),

  joinGame: (gameId: string, userId: string, displayName: string) =>
    request<Game>(`/api/games/${gameId}/join`, {
      method: 'POST',
      body: JSON.stringify({ userId, displayName }),
    }),

  getGame: (gameId: string, userId: string) =>
    request<Game>(`/api/games/${gameId}?userId=${encodeURIComponent(userId)}`),

  generateGameImage: (gameId: string, userId: string, prompt: string) =>
    request<Game>(`/api/games/${gameId}/generate`, {
      method: 'POST',
      body: JSON.stringify({ userId, prompt }),
    }),
}
