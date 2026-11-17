export type PlayerColor = 'w' | 'b';
export type TimeClass = 'bullet' | 'blitz' | 'rapid' | 'classical';
export type GameOutcome = 'win' | 'loss' | 'draw';
export type MoveClassification =
  | 'book'
  | 'best'
  | 'excellent'
  | 'good'
  | 'inaccuracy'
  | 'mistake'
  | 'blunder';

export type MistakeSeverity = 'blunder' | 'mistake' | 'inaccuracy';
export type GamePhase = 'opening' | 'middlegame' | 'endgame';

export type MistakeMotif =
  | 'missed_mate'
  | 'allowed_mate'
  | 'material_loss'
  | 'missed_tactic'
  | 'king_safety'
  | 'opening_principle'
  | 'endgame_technique'
  | 'positional_slip';

export type MasteryState = 'unseen' | 'needs_review' | 'learning' | 'mastered';

export interface GameSummary {
  id: string;
  source: 'archive' | 'custom';
  month: string; // e.g. "2026-10"
  date: string; // e.g. "2026.10.01"
  utcTime: string;
  white: string;
  black: string;
  whiteElo: number | null;
  blackElo: number | null;
  userColor: PlayerColor;
  userName: string;
  userElo: number | null;
  opponentName: string;
  opponentElo: number | null;
  result: string;
  userOutcome: GameOutcome;
  timeControl: string;
  timeClass: TimeClass;
  eco: string;
  openingName: string;
  termination: string;
  moveCount: number;
  link?: string;
  /** Variant from the PGN header; Chess960 games are listed but not engine-drillable. */
  variant?: string;
  /** False for variants the bundled standard chess.js replay cannot support. */
  analyzable?: boolean;
  analyzed: boolean;
  accuracy?: number;
  blundersCount?: number;
  mistakesCount?: number;
  inaccuraciesCount?: number;
  totalMistakesCount?: number;
  masteredMistakesCount?: number;
}

export interface PlyAnalysisSummary {
  ply: number; // 1-indexed ply (1 = White's 1st move)
  moveNumber: number;
  color: PlayerColor;
  san: string;
  uci: string;
  from: string;
  to: string;
  fenBefore: string;
  fenAfter: string;
  clock?: string;
  /** Centipawn score from White's perspective after this move (mate mapped to +-10000) */
  whiteEvalCp: number;
  whiteMate: number | null;
  classification: MoveClassification;
  mistakeId?: string;
}

export interface MistakeMasteryRecord {
  mistakeId: string;
  status: MasteryState;
  totalAttempts: number;
  failCount: number;
  streak: number;
  solvedFirstTry: boolean | null;
  lastAttemptAt: string | null;
}

/**
 * Spoiler-safe mistake payload sent before the player solves or fails.
 * Notice: bestMoveSan / bestMoveUci / bestPvSan are intentionally absent!
 */
export interface MistakeChallengePublic {
  id: string;
  gameId: string;
  gameOpponent: string;
  gameDate: string;
  openingName: string;
  timeClass: TimeClass;
  ply: number;
  moveNumber: number;
  userColor: PlayerColor;
  fenBefore: string;
  precedingMove: {
    san: string;
    from: string;
    to: string;
  } | null;
  playedMove: {
    san: string;
    uci: string;
    from: string;
    to: string;
  };
  /** Evaluation from user's perspective BEFORE the mistake */
  evalBeforeUserCp: number;
  evalBeforeUserMate: number | null;
  /** Evaluation from user's perspective AFTER the game mistake */
  evalAfterPlayedUserCp: number;
  evalAfterPlayedUserMate: number | null;
  /** Win probability lost (0..1, e.g. 0.24 = 24% win chance dropped) */
  winProbLost: number;
  severity: MistakeSeverity;
  phase: GamePhase;
  motif: MistakeMotif;
  /** Gentle piece-only nudge if the player explicitly asks for a hint (never spoils target square) */
  pieceNudge: string;
  mastery: MistakeMasteryRecord;
}

export interface AlternativeLine {
  san: string;
  uci: string;
  from: string;
  to: string;
  evalUserCp: number;
  evalUserMate: number | null;
  pvSan: string[];
}

export interface MistakeSolutionReveal {
  bestMove: {
    san: string;
    uci: string;
    from: string;
    to: string;
  };
  bestEvalUserCp: number;
  bestEvalUserMate: number | null;
  bestPvSan: string[];
  alternatives: AlternativeLine[];
  playedRefutationPvSan: string[];
  motifLabel: string;
  coachExplanation: string;
}

export interface AttemptMoveRequest {
  moveUci: string; // e.g. "e2e4" or "a7a8q"
  attemptNumber: number; // 1-based attempt number in current drill
  maxAttempts: number; // 1 (default strict) or 2
  isPracticeRetry?: boolean; // when re-drilling in Mistake Vault or end-of-game retry
}

export interface AttemptMoveResponse {
  /**
   * - 'same_as_game': user accidentally re-played the exact game mistake (doesn't burn attempt)
   * - 'best': user found Stockfish's #1 move!
   * - 'great': user found a strong engine-approved improvement close to #1!
   * - 'retry': wrong move, user still has an attempt remaining (best move stays hidden!)
   * - 'failed_revealed': user failed -> best move + refutations are NOW revealed!
   */
  outcome: 'same_as_game' | 'best' | 'great' | 'retry' | 'failed_revealed';
  candidateMove: {
    san: string;
    uci: string;
    from: string;
    to: string;
  };
  candidateEvalUserCp: number;
  candidateEvalUserMate: number | null;
  candidateRefutationPvSan: string[];
  feedbackHeadline: string;
  feedbackDetail: string;
  mastery: MistakeMasteryRecord;
  /** ONLY populated when outcome is 'best', 'great', or 'failed_revealed' */
  solution?: MistakeSolutionReveal;
}

export interface GameDetailResponse {
  summary: GameSummary;
  pgn: string;
  analyzed: boolean;
  plies: PlyAnalysisSummary[];
  mistakes: MistakeChallengePublic[];
  whiteAccuracy?: number;
  blackAccuracy?: number;
  userAccuracy?: number;
}

export interface ArchiveOverviewResponse {
  player: string;
  totalArchiveGames: number;
  totalSupportedGames: number;
  totalChess960Games: number;
  totalCustomGames: number;
  analyzedGamesCount: number;
  wins: number;
  losses: number;
  draws: number;
  byTimeClass: Record<TimeClass, { games: number; wins: number; losses: number; latestElo: number | null; peakElo: number | null }>;
  eloTimeline: { month: string; rapidElo: number | null; blitzElo: number | null; bulletElo: number | null; games: number }[];
  topOpenings: { name: string; games: number; winRate: number }[];
  mistakeStats: {
    totalDiscovered: number;
    unseen: number;
    needsReview: number;
    learning: number;
    mastered: number;
    blunders: number;
    mistakes: number;
    inaccuracies: number;
    firstTrySolveRate: number;
    byMotif: { motif: MistakeMotif; label: string; count: number; mastered: number }[];
    byPhase: Record<GamePhase, number>;
  };
}

// ---- Full-archive batch analysis & learning curriculum --------------------

export interface AnalyzeAllResult {
  totalGames: number;
  supportedGames: number;
  analyzedGames: number;
  skippedGames: number;
  skippedVariantGames: number;
  failedGames: number;
  totalMistakes: number;
  durationSeconds: number;
  failures: Array<{ gameId: string; error: string }>;
}

export interface AnalyzeAllProgress {
  total: number;
  supported: number;
  processed: number;
  analyzed: number;
  skipped: number;
  skippedVariant: number;
  failed: number;
  percent: number;
  elapsedSeconds: number;
  etaSeconds: number | null;
  totalMistakes: number;
  currentGameId: string | null;
  currentOpening: string | null;
  message: string;
}

export interface AnalyzeAllStatus extends AnalyzeAllProgress {
  running: boolean;
  startedAt: string | null;
  finishedAt: string | null;
  error: string | null;
  result: AnalyzeAllResult | null;
}

export interface LearningPlanDrill {
  rank: number;
  mistakeId: string;
  gameId: string;
  gameDate: string;
  opponent: string;
  openingName: string;
  timeClass: TimeClass;
  moveNumber: number;
  userColor: PlayerColor;
  playedMoveSan: string;
  severity: MistakeSeverity;
  motif: MistakeMotif;
  motifLabel: string;
  phase: GamePhase;
  phaseLabel: string;
  winProbLost: number;
  mastery: MistakeMasteryRecord;
  focus: string;
  reason: string;
}

export interface LearningPlanResponse {
  generatedAt: string;
  player: string;
  engine: string;
  totalArchiveGames: number;
  totalSupportedGames: number;
  totalChess960Games: number;
  totalCustomGames: number;
  analyzedGames: number;
  totalMistakes: number;
  dueCount: number;
  masteredCount: number;
  firstTrySolveRate: number;
  counts: {
    bySeverity: Record<MistakeSeverity, number>;
    byPhase: Record<GamePhase, number>;
    byMastery: Record<MasteryState, number>;
    byMotif: Array<{ motif: MistakeMotif; label: string; count: number; mastered: number }>;
  };
  recommendedDrills: LearningPlanDrill[];
  analyzeAll: AnalyzeAllStatus;
  files: {
    fullAnalysisCache: string;
    learningPlanJson: string;
    whatToLearnMarkdown: string;
  };
}

// ---- Gemini coach layer ---------------------------------------------------
// Gemini may select an allowlisted intent; answers are generated locally.

export type CoachSource = 'gemini' | 'local';
export type CoachStatus =
  | 'ok'
  | 'disabled'
  | 'quota'
  | 'throttled'
  | 'error'
  | 'blocked'
  | 'empty'
  | 'spoiler_rejected';

export interface CoachStatusResponse {
  provider: 'gemini';
  configured: boolean;
  model: string;
  baseUrl: string;
  dailyCallBudget: number;
  callsToday: number;
  minIntervalMs: number;
  localFallback: true;
  knowledgeEngine: 'Stockfish 18 Lite NNUE (local)';
  spoilerSafe: true;
  /** Human-readable reason Gemini is on/off. Never contains the key. */
  reason?: string;
  /** Actionable, non-secret setup hint for the server operator. */
  hint?: string;
  /** Last sanitized provider failure, if any. */
  lastProviderError?: string | null;
}

export interface CoachAskRequest {
  question: string;
  history?: Array<{ role: 'user' | 'coach'; text: string }>;
}

export interface CoachAnswerResponse {
  answer: string;
  source: CoachSource;
  status: CoachStatus;
  model: string | null;
  latencyMs: number;
  configured: boolean;
  generatedAt: string;
  knowledge: {
    engine: string;
    archiveGames: number;
    analyzedGames: number;
    totalMistakes: number;
    dueCount: number;
    masteredCount: number;
    firstTrySolveRate: number;
  };
  suggestions: string[];
  error?: string;
}
