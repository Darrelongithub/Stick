import type {
  AnalyzeAllStatus,
  ArchiveOverviewResponse,
  AttemptMoveRequest,
  AttemptMoveResponse,
  CoachAnswerResponse,
  CoachAskRequest,
  CoachStatusResponse,
  GameDetailResponse,
  GameSummary,
  LearningPlanResponse,
  MistakeChallengePublic,
} from '../../shared/types';

export interface AnalysisProgress {
  stage: string;
  current: number;
  total: number;
  percent: number;
}

export interface GamesQuery {
  source?: string;
  analyzed?: string;
  timeClass?: string;
  outcome?: string;
  color?: string;
  month?: string;
  search?: string;
  page?: number;
  limit?: number;
}

export interface GameListResponse {
  total: number;
  page: number;
  limit: number;
  months: string[];
  games: GameSummary[];
}

export interface MistakesQuery {
  status?: string;
  severity?: string;
  motif?: string;
  phase?: string;
}

export interface MistakesResponse {
  total: number;
  mistakes: MistakeChallengePublic[];
}

export interface ImportPgnResponse {
  importedCount: number;
  games: GameSummary[];
}

export class ApiError extends Error {
  status: number;

  constructor(message: string, status: number) {
    super(message);
    this.name = 'ApiError';
    this.status = status;
  }
}

function queryString(params: object): string {
  const search = new URLSearchParams();
  for (const [key, value] of Object.entries(params)) {
    if (value === undefined || value === null || value === '' || value === 'all') continue;
    if (typeof value === 'string' || typeof value === 'number' || typeof value === 'boolean') {
      search.set(key, String(value));
    }
  }
  const text = search.toString();
  return text ? `?${text}` : '';
}

async function requestJson<T>(url: string, init?: RequestInit): Promise<T> {
  const response = await fetch(url, {
    ...init,
    headers: {
      ...(init?.body ? { 'Content-Type': 'application/json' } : {}),
      ...(init?.headers ?? {}),
    },
  });

  const contentType = response.headers.get('content-type') ?? '';
  const payload = contentType.includes('application/json')
    ? await response.json()
    : await response.text();

  if (!response.ok) {
    const message =
      payload && typeof payload === 'object' && 'error' in payload
        ? String((payload as { error: unknown }).error)
        : typeof payload === 'string' && payload
          ? payload
          : `Request failed (${response.status})`;
    throw new ApiError(message, response.status);
  }

  return payload as T;
}

export const api = {
  mirrorProfile(): Promise<{ indexed: number; games: number; skipped: number }> {
    return requestJson('/api/mirror/profile');
  },
  mirrorMove(moves: string[]): Promise<{ move: string; source: 'archive' | 'stockfish'; occurrences: number; samples: number }> {
    return requestJson('/api/mirror/move', { method: 'POST', body: JSON.stringify({ moves }) });
  },
  overview(): Promise<ArchiveOverviewResponse> {
    return requestJson<ArchiveOverviewResponse>('/api/overview');
  },

  health(): Promise<{ ok: boolean; player: string; engine: string; analyzeAllRunning: boolean }> {
    return requestJson<{ ok: boolean; player: string; engine: string; analyzeAllRunning: boolean }>(
      '/api/health'
    );
  },

  learningPlan(): Promise<LearningPlanResponse> {
    return requestJson<LearningPlanResponse>('/api/learning-plan');
  },

  coachStatus(): Promise<CoachStatusResponse> {
    return requestJson<CoachStatusResponse>('/api/coach/status');
  },

  askCoach(question: string, history: CoachAskRequest['history'] = []): Promise<CoachAnswerResponse> {
    return requestJson<CoachAnswerResponse>('/api/coach/ask', {
      method: 'POST',
      body: JSON.stringify({ question, history }),
    });
  },

  analyzeAllStatus(): Promise<AnalyzeAllStatus> {
    return requestJson<AnalyzeAllStatus>('/api/admin/analyze-all/status');
  },

  startAnalyzeAll(): Promise<{ started: boolean; status: AnalyzeAllStatus }> {
    return requestJson<{ started: boolean; status: AnalyzeAllStatus }>(
      '/api/admin/analyze-all',
      { method: 'POST' }
    );
  },

  nextCoachGame(excludeId?: string): Promise<{ game: GameSummary | null }> {
    return requestJson<{ game: GameSummary | null }>(
      `/api/games/next-coach${queryString({ excludeId })}`
    );
  },

  game(id: string): Promise<GameDetailResponse> {
    return requestJson<GameDetailResponse>(`/api/games/${encodeURIComponent(id)}`);
  },

  games(query: GamesQuery = {}): Promise<GameListResponse> {
    return requestJson<GameListResponse>(`/api/games${queryString(query)}`);
  },

  mistakes(query: MistakesQuery = {}): Promise<MistakesResponse> {
    return requestJson<MistakesResponse>(`/api/mistakes${queryString(query)}`);
  },

  attemptMistake(
    id: string,
    body: AttemptMoveRequest
  ): Promise<AttemptMoveResponse> {
    return requestJson<AttemptMoveResponse>(`/api/mistakes/${encodeURIComponent(id)}/attempt`, {
      method: 'POST',
      body: JSON.stringify(body),
    });
  },

  resetMistake(id: string): Promise<{ mastery: MistakeChallengePublic['mastery'] }> {
    return requestJson<{ mastery: MistakeChallengePublic['mastery'] }>(
      `/api/mistakes/${encodeURIComponent(id)}/reset`,
      { method: 'POST' }
    );
  },

  importPgn(
    pgn: string,
    preferredSide: 'auto' | 'w' | 'b',
    playerHint?: string
  ): Promise<ImportPgnResponse> {
    return requestJson<ImportPgnResponse>('/api/pgn/import', {
      method: 'POST',
      body: JSON.stringify({ pgn, preferredSide, playerHint }),
    });
  },

  analyzeGame(id: string): Promise<GameDetailResponse> {
    return requestJson<GameDetailResponse>(`/api/games/${encodeURIComponent(id)}/analyze`, {
      method: 'POST',
    });
  },
};

export interface AnalysisStreamHandlers {
  onProgress: (info: AnalysisProgress) => void;
  onDone: (game: GameDetailResponse) => void;
  onError: (message: string) => void;
}

/**
 * Opens the real Stockfish 18 NNUE server-sent-event stream. Relative URL keeps
 * the browser on the preview host; the unified Express/Vite server owns the API.
 */
export function streamGameAnalysis(id: string, handlers: AnalysisStreamHandlers): () => void {
  const source = new EventSource(`/api/games/${encodeURIComponent(id)}/analyze-stream`);
  let finished = false;

  const finish = () => {
    if (finished) return;
    finished = true;
    source.close();
  };

  source.onmessage = (event) => {
    let data: Record<string, unknown>;
    try {
      data = JSON.parse(event.data) as Record<string, unknown>;
    } catch {
      return;
    }

    if (data.type === 'progress') {
      handlers.onProgress({
        stage: String(data.stage ?? 'Analyzing'),
        current: Number(data.current ?? 0),
        total: Number(data.total ?? 0),
        percent: Math.max(0, Math.min(100, Number(data.percent ?? 0))),
      });
      return;
    }

    if (data.type === 'done') {
      handlers.onDone(data.game as GameDetailResponse);
      finish();
      return;
    }

    if (data.type === 'error') {
      handlers.onError(String(data.message ?? 'Stockfish analysis failed'));
      finish();
    }
  };

  source.onerror = () => {
    if (!finished) {
      handlers.onError('The analysis stream disconnected. Please retry.');
      finish();
    }
  };

  return finish;
}
