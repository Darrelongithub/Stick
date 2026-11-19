import fs from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';
import { Chess, PieceSymbol } from 'chess.js';
import { stockfishPool, mateToCp } from './stockfishPool.js';
import { pgnArchive, StoredGameRecord } from './pgnArchive.js';
import { progressStore } from './progressStore.js';
import type {
  AlternativeLine,
  AnalyzeAllProgress,
  AnalyzeAllResult,
  AttemptMoveRequest,
  AttemptMoveResponse,
  GameDetailResponse,
  GamePhase,
  GameSummary,
  MistakeChallengePublic,
  MistakeMotif,
  MistakeSeverity,
  MistakeSolutionReveal,
  MoveClassification,
  PlayerColor,
  PlyAnalysisSummary,
} from '../shared/types.js';

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const DATA_DIR = path.resolve(__dirname, '../data');
const SEED_ANALYSIS_PATH = path.join(DATA_DIR, 'preanalyzed-games.json');
const RUNTIME_CACHE_PATH = path.join(DATA_DIR, 'analysis-cache.json');
const ANALYZE_ALL_PROGRESS_PATH = path.join(DATA_DIR, 'analyze-all-progress.json');

const PIECE_NAMES: Record<PieceSymbol, string> = {
  p: 'pawn',
  n: 'knight',
  b: 'bishop',
  r: 'rook',
  q: 'queen',
  k: 'king',
};

const PIECE_VALUES: Record<PieceSymbol, number> = {
  p: 1,
  n: 3,
  b: 3,
  r: 5,
  q: 9,
  k: 0,
};

export const MOTIF_LABELS: Record<MistakeMotif, string> = {
  missed_mate: 'Missed Checkmate',
  allowed_mate: 'Allowed Checkmate',
  material_loss: 'Hanging Piece / Material Loss',
  missed_tactic: 'Missed Tactical Shot',
  king_safety: 'King Safety Slip',
  opening_principle: 'Opening Inaccuracy',
  endgame_technique: 'Endgame Technique',
  positional_slip: 'Positional / Middlegame Slip',
};

/**
 * Older seeded analyses stored a hint that named the best piece's origin square.
 * Public challenges must never expose that detail (and especially not a castling
 * instruction), so every outgoing hint is normalized to a theme-only nudge.
 */
export function sanitizePieceNudge(rawHint: string): string {
  const pieceMatch = rawHint.match(/your\s+([a-z]+)\s+on\s+[a-hA-H][1-8]/i);
  if (pieceMatch) {
    const piece = pieceMatch[1].toLowerCase();
    if (piece === 'king') {
      return 'King safety is the theme. Scan checks, escapes and coordination — no square or move is shown.';
    }
    return `One of your ${piece}s holds the key. Re-check its forcing moves and safe squares — no square or move is shown.`;
  }
  if (/castl/i.test(rawHint)) {
    return 'King safety is the theme. Scan the entire board before committing — the answer stays hidden.';
  }
  return 'Scan checks, captures and threats in that order. The best move stays hidden until you fail.';
}

export interface StoredMistakeInternal {
  id: string;
  gameId: string;
  ply: number;
  moveNumber: number;
  userColor: PlayerColor;
  fenBefore: string;
  precedingMove: { san: string; from: string; to: string } | null;
  playedMove: { san: string; uci: string; from: string; to: string };
  evalBeforeUserCp: number;
  evalBeforeUserMate: number | null;
  evalAfterPlayedUserCp: number;
  evalAfterPlayedUserMate: number | null;
  winProbLost: number;
  severity: MistakeSeverity;
  phase: GamePhase;
  motif: MistakeMotif;
  pieceNudge: string;
  // Private solution fields (only revealed on solve or fail!)
  bestMove: { san: string; uci: string; from: string; to: string };
  bestEvalUserCp: number;
  bestEvalUserMate: number | null;
  bestPvSan: string[];
  alternatives: AlternativeLine[];
  playedRefutationPvSan: string[];
  coachExplanation: string;
}

export interface StoredGameAnalysis {
  gameId: string;
  analyzedAt: string;
  engineName: string;
  whiteAccuracy: number;
  blackAccuracy: number;
  userAccuracy: number;
  plies: PlyAnalysisSummary[];
  mistakes: StoredMistakeInternal[];
}

export function cpToWinProb(cp: number): number {
  const clamped = Math.max(-4000, Math.min(4000, cp));
  return 1 / (1 + Math.exp(-0.00368208 * clamped));
}

function moveAccuracyPercent(winProbBefore: number, winProbAfter: number): number {
  const winDiff = Math.max(0, (winProbBefore - winProbAfter) * 100);
  const raw = 103.1668 * Math.exp(-0.04354 * winDiff) - 3.1669;
  return Math.max(0, Math.min(100, raw));
}

function turnScoreToWhite(
  turn: PlayerColor,
  cpFromTurn: number,
  mateFromTurn: number | null
): { whiteCp: number; whiteMate: number | null } {
  if (turn === 'w') {
    return { whiteCp: cpFromTurn, whiteMate: mateFromTurn };
  }
  return {
    whiteCp: -cpFromTurn,
    whiteMate: mateFromTurn === null ? null : -mateFromTurn,
  };
}

function whiteScoreToUser(
  userColor: PlayerColor,
  whiteCp: number,
  whiteMate: number | null
): { userCp: number; userMate: number | null } {
  if (userColor === 'w') {
    return { userCp: whiteCp, userMate: whiteMate };
  }
  return {
    userCp: -whiteCp,
    userMate: whiteMate === null ? null : -whiteMate,
  };
}

export function uciPvToSan(startFen: string, pvUci: string[], maxPlies = 6): string[] {
  const chess = new Chess(startFen);
  const out: string[] = [];
  for (const uci of pvUci.slice(0, maxPlies)) {
    if (!uci || uci.length < 4) break;
    const from = uci.slice(0, 2);
    const to = uci.slice(2, 4);
    const promotion = uci.length >= 5 ? uci[4] : undefined;
    try {
      const m = chess.move({ from, to, promotion });
      if (!m) break;
      out.push(m.san);
    } catch {
      break;
    }
  }
  return out;
}

function uciToMoveDetails(
  fen: string,
  uci: string
): { san: string; uci: string; from: string; to: string; captured?: PieceSymbol; piece: PieceSymbol } | null {
  const chess = new Chess(fen);
  const from = uci.slice(0, 2);
  const to = uci.slice(2, 4);
  const promotion = uci.length >= 5 ? uci[4] : undefined;
  try {
    const m = chess.move({ from, to, promotion });
    if (!m) return null;
    return {
      san: m.san,
      uci,
      from: m.from,
      to: m.to,
      captured: m.captured,
      piece: m.piece,
    };
  } catch {
    return null;
  }
}

function countNonKingPieces(fen: string): number {
  const boardPart = fen.split(' ')[0];
  let count = 0;
  for (const ch of boardPart) {
    if (/[pnbrqPNBRQ]/.test(ch)) count++;
  }
  return count;
}

function detectPhase(ply: number, fen: string): GamePhase {
  const pieces = countNonKingPieces(fen);
  if (pieces <= 12) return 'endgame';
  if (ply <= 18) return 'opening';
  return 'middlegame';
}

function formatEvalLabel(cp: number, mate: number | null): string {
  if (mate !== null) {
    if (mate === 0) return 'Checkmate';
    return mate > 0 ? `Mate in ${mate}` : `Mated in ${Math.abs(mate)}`;
  }
  const pawns = cp / 100;
  return `${pawns >= 0 ? '+' : ''}${pawns.toFixed(2)}`;
}

function classifyMotifAndExplanation(params: {
  fenBefore: string;
  phase: GamePhase;
  playedSan: string;
  bestSan: string;
  bestPiece: PieceSymbol;
  bestFrom: string;
  bestCaptured?: PieceSymbol;
  bestEvalUserCp: number;
  bestEvalUserMate: number | null;
  afterPlayedUserCp: number;
  afterPlayedUserMate: number | null;
  playedRefutationPvSan: string[];
  fenAfterPlayed: string;
  oppFirstRefutationUci?: string;
}): { motif: MistakeMotif; coachExplanation: string; pieceNudge: string } {
  const {
    phase,
    playedSan,
    bestSan,
    bestPiece,
    bestFrom,
    bestCaptured,
    bestEvalUserCp,
    bestEvalUserMate,
    afterPlayedUserCp,
    afterPlayedUserMate,
    playedRefutationPvSan,
    fenAfterPlayed,
    oppFirstRefutationUci,
  } = params;

  const pieceName = PIECE_NAMES[bestPiece] || 'piece';
  const pieceNudge =
    bestPiece === 'k' && (bestSan === 'O-O' || bestSan === 'O-O-O')
      ? 'Look at king safety — can you castle right now?'
      : `Look closely at your ${pieceName} on ${bestFrom.toUpperCase()}.`;

  const oppReplyText = playedRefutationPvSan[0]
    ? ` allowing ${playedRefutationPvSan.slice(0, 3).join(' ')}`
    : '';

  if (bestEvalUserMate !== null && bestEvalUserMate > 0 && (afterPlayedUserMate === null || afterPlayedUserMate <= 0)) {
    return {
      motif: 'missed_mate',
      pieceNudge,
      coachExplanation: `You had a forced checkmate in ${bestEvalUserMate} starting with ${bestSan}! Playing ${playedSan} let the mate slip (${formatEvalLabel(afterPlayedUserCp, afterPlayedUserMate)}).`,
    };
  }

  if (afterPlayedUserMate !== null && afterPlayedUserMate < 0 && (bestEvalUserMate === null || bestEvalUserMate >= 0)) {
    return {
      motif: 'allowed_mate',
      pieceNudge,
      coachExplanation: `${playedSan} walks straight into a forced mate in ${Math.abs(afterPlayedUserMate)}${oppReplyText}. ${bestSan} (${formatEvalLabel(bestEvalUserCp, bestEvalUserMate)}) keeps your king alive and safe.`,
    };
  }

  // Check if opponent's immediate reply wins significant material by capture
  if (oppFirstRefutationUci) {
    const oppMove = uciToMoveDetails(fenAfterPlayed, oppFirstRefutationUci);
    if (oppMove?.captured && PIECE_VALUES[oppMove.captured] >= 3 && bestEvalUserCp - afterPlayedUserCp >= 220) {
      const lostPieceName = PIECE_NAMES[oppMove.captured];
      return {
        motif: 'material_loss',
        pieceNudge,
        coachExplanation: `${playedSan} leaves material vulnerable — your opponent punishes it immediately with ${oppMove.san}, capturing a ${lostPieceName}. ${bestSan} (${formatEvalLabel(bestEvalUserCp, bestEvalUserMate)}) avoids the loss.`,
      };
    }
  }

  if (bestCaptured && PIECE_VALUES[bestCaptured] >= 3 && bestEvalUserCp - afterPlayedUserCp >= 200) {
    return {
      motif: 'missed_tactic',
      pieceNudge,
      coachExplanation: `There was a tactical capture available right away with ${bestSan}, winning a ${PIECE_NAMES[bestCaptured]} (${formatEvalLabel(bestEvalUserCp, bestEvalUserMate)}) instead of ${playedSan} (${formatEvalLabel(afterPlayedUserCp, afterPlayedUserMate)}).`,
    };
  }

  if (bestEvalUserCp - afterPlayedUserCp >= 230) {
    return {
      motif: 'missed_tactic',
      pieceNudge,
      coachExplanation: `${playedSan} drops tactical control${oppReplyText} (${formatEvalLabel(afterPlayedUserCp, afterPlayedUserMate)}). Stockfish's ${bestSan} seizes the initiative (${formatEvalLabel(bestEvalUserCp, bestEvalUserMate)}).`,
    };
  }

  if (bestSan === 'O-O' || bestSan === 'O-O-O' || playedRefutationPvSan.some((m) => m.includes('+'))) {
    return {
      motif: 'king_safety',
      pieceNudge,
      coachExplanation: `${playedSan} exposes your position${oppReplyText} (${formatEvalLabel(afterPlayedUserCp, afterPlayedUserMate)}). ${bestSan} stabilizes king safety and coordination (${formatEvalLabel(bestEvalUserCp, bestEvalUserMate)}).`,
    };
  }

  if (phase === 'opening') {
    return {
      motif: 'opening_principle',
      pieceNudge,
      coachExplanation: `In the opening, ${playedSan} cedes momentum${oppReplyText} (${formatEvalLabel(afterPlayedUserCp, afterPlayedUserMate)}). ${bestSan} develops cleanly and keeps ${formatEvalLabel(bestEvalUserCp, bestEvalUserMate)}.`,
    };
  }

  if (phase === 'endgame') {
    return {
      motif: 'endgame_technique',
      pieceNudge,
      coachExplanation: `Endgame precision matters here: ${playedSan}${oppReplyText} shifts the evaluation to ${formatEvalLabel(afterPlayedUserCp, afterPlayedUserMate)}, whereas ${bestSan} holds ${formatEvalLabel(bestEvalUserCp, bestEvalUserMate)}.`,
    };
  }

  return {
    motif: 'positional_slip',
    pieceNudge,
    coachExplanation: `${playedSan}${oppReplyText} hands over ${Math.round((cpToWinProb(bestEvalUserCp) - cpToWinProb(afterPlayedUserCp)) * 100)}% win expectancy (${formatEvalLabel(afterPlayedUserCp, afterPlayedUserMate)}). ${bestSan} maintains ${formatEvalLabel(bestEvalUserCp, bestEvalUserMate)}.`,
  };
}

class GameAnalyzerService {
  private cache = new Map<string, StoredGameAnalysis>();
  private inFlight = new Map<string, Promise<StoredGameAnalysis>>();
  private loaded = false;
  revision = 0;

  ensureLoaded() {
    if (this.loaded) return;
    fs.mkdirSync(DATA_DIR, { recursive: true });

    for (const filePath of [SEED_ANALYSIS_PATH, RUNTIME_CACHE_PATH]) {
      if (fs.existsSync(filePath)) {
        try {
          const parsed = JSON.parse(fs.readFileSync(filePath, 'utf8')) as Record<
            string,
            StoredGameAnalysis
          >;
          for (const [gameId, analysis] of Object.entries(parsed)) {
            this.cache.set(gameId, analysis);
          }
        } catch (err) {
          console.warn(`[analyzer] Failed to load ${filePath}:`, err);
        }
      }
    }
    this.loaded = true;
  }

  /** Public so the full-archive batch job can checkpoint and do one final write. */
  persistRuntimeCache() {
    const obj: Record<string, StoredGameAnalysis> = {};
    for (const [k, v] of this.cache.entries()) {
      obj[k] = v;
    }
    // Compact JSON: the full archive cache is tens of megabytes.
    fs.writeFileSync(RUNTIME_CACHE_PATH, JSON.stringify(obj), 'utf8');
  }

  saveSeedFile(gameIds?: string[]) {
    this.ensureLoaded();
    const obj: Record<string, StoredGameAnalysis> = {};
    for (const [k, v] of this.cache.entries()) {
      if (!gameIds || gameIds.includes(k)) {
        obj[k] = v;
      }
    }
    fs.writeFileSync(SEED_ANALYSIS_PATH, JSON.stringify(obj, null, 2), 'utf8');
  }

  getCached(gameId: string): StoredGameAnalysis | undefined {
    this.ensureLoaded();
    return this.cache.get(gameId);
  }

  getAllCached(): StoredGameAnalysis[] {
    this.ensureLoaded();
    return Array.from(this.cache.values());
  }

  toPublicChallenge(
    m: StoredMistakeInternal,
    gameRecord: StoredGameRecord
  ): MistakeChallengePublic {
    return {
      id: m.id,
      gameId: m.gameId,
      gameOpponent: gameRecord.summary.opponentName,
      gameDate: gameRecord.summary.date,
      openingName: gameRecord.summary.openingName,
      timeClass: gameRecord.summary.timeClass,
      ply: m.ply,
      moveNumber: m.moveNumber,
      userColor: m.userColor,
      fenBefore: m.fenBefore,
      precedingMove: m.precedingMove,
      playedMove: m.playedMove,
      evalBeforeUserCp: m.evalBeforeUserCp,
      evalBeforeUserMate: m.evalBeforeUserMate,
      evalAfterPlayedUserCp: m.evalAfterPlayedUserCp,
      evalAfterPlayedUserMate: m.evalAfterPlayedUserMate,
      winProbLost: m.winProbLost,
      severity: m.severity,
      phase: m.phase,
      motif: m.motif,
      pieceNudge: sanitizePieceNudge(m.pieceNudge),
      mastery: progressStore.getRecord(m.id),
    };
  }

  toSolutionReveal(m: StoredMistakeInternal): MistakeSolutionReveal {
    return {
      bestMove: m.bestMove,
      bestEvalUserCp: m.bestEvalUserCp,
      bestEvalUserMate: m.bestEvalUserMate,
      bestPvSan: m.bestPvSan,
      alternatives: m.alternatives,
      playedRefutationPvSan: m.playedRefutationPvSan,
      motifLabel: MOTIF_LABELS[m.motif],
      coachExplanation: m.coachExplanation,
    };
  }

  getMistakeInternalById(mistakeId: string): {
    mistake: StoredMistakeInternal;
    game: StoredGameRecord;
  } | null {
    this.ensureLoaded();
    for (const analysis of this.cache.values()) {
      const found = analysis.mistakes.find((m) => m.id === mistakeId);
      if (found) {
        const game = pgnArchive.getGameById(found.gameId);
        if (game) return { mistake: found, game };
      }
    }
    return null;
  }

  async analyzeGame(
    gameId: string,
    onProgress?: (info: { stage: string; current: number; total: number; percent: number }) => void,
    options: { persist?: boolean } = {}
  ): Promise<StoredGameAnalysis> {
    this.ensureLoaded();
    const existing = this.cache.get(gameId);
    if (existing) {
      onProgress?.({ stage: 'complete', current: existing.plies.length, total: existing.plies.length, percent: 100 });
      return existing;
    }

    const active = this.inFlight.get(gameId);
    if (active) return active;

    const record = pgnArchive.getGameById(gameId);
    if (!record) {
      throw new Error(`Game not found: ${gameId}`);
    }

    const jobPromise = this.runFullAnalysis(record, onProgress)
      .then((res) => {
        this.cache.set(gameId, res);
        this.revision++;
        if (options.persist !== false) this.persistRuntimeCache();
        return res;
      })
      .finally(() => {
        this.inFlight.delete(gameId);
      });

    this.inFlight.set(gameId, jobPromise);
    return jobPromise;
  }

  /**
   * Analyzes every supported archive / custom game with the real Stockfish pool.
   * Writes compact checkpoints instead of rewriting a 40MB file after each game.
   * Chess960 records remain in the library but are intentionally not drilled
   * because standard chess.js cannot replay all of their castling moves.
   */
  async analyzeAllGames(
    onProgress?: (info: AnalyzeAllProgress) => void
  ): Promise<AnalyzeAllResult> {
    this.ensureLoaded();
    await stockfishPool.warmup();

    const records = pgnArchive.getAllRecords();
    const supportedRecords = records.filter((r) => r.summary.analyzable !== false);
    const total = records.length;
    const supported = supportedRecords.length;
    const skippedVariant = total - supported;
    const started = Date.now();

    let analyzed = 0;
    let skipped = 0;
    let failed = 0;
    let processed = 0;
    let totalMistakes = 0;
    const failures: Array<{ gameId: string; error: string }> = [];

    for (const analysis of this.cache.values()) {
      if (pgnArchive.getGameById(analysis.gameId)) {
        totalMistakes += analysis.mistakes.length;
      }
    }

    const writeProgressFile = (progress: AnalyzeAllProgress) => {
      fs.writeFileSync(
        ANALYZE_ALL_PROGRESS_PATH,
        JSON.stringify({ generatedAt: new Date().toISOString(), ...progress }, null, 2),
        'utf8'
      );
    };

    const emit = (
      message: string,
      currentGameId: string | null,
      currentOpening: string | null
    ): AnalyzeAllProgress => {
      const elapsedSeconds = (Date.now() - started) / 1000;
      const etaSeconds =
        processed > 0 && processed < total
          ? Math.round((elapsedSeconds / processed) * (total - processed))
          : null;
      const progress: AnalyzeAllProgress = {
        total,
        supported,
        processed,
        analyzed,
        skipped,
        skippedVariant,
        failed,
        percent: total > 0 ? Math.round((processed / total) * 100) : 100,
        elapsedSeconds: Number(elapsedSeconds.toFixed(1)),
        etaSeconds,
        totalMistakes,
        currentGameId,
        currentOpening,
        message,
      };
      onProgress?.(progress);
      if (processed % 10 === 0 || processed === total) writeProgressFile(progress);
      if (processed % 25 === 0 || processed === total) {
        console.log(
          `[analyze-all] ${progress.percent}% · ${processed}/${total} games · ${analyzed} newly analyzed · ${totalMistakes} mistakes · ETA ${etaSeconds ?? 0}s`
        );
      }
      return progress;
    };

    for (const record of records) {
      processed++;
      if (record.summary.analyzable === false) {
        emit(
          `Chess960 / variant game indexed (not engine-drillable): ${record.summary.id}`,
          record.summary.id,
          record.summary.openingName
        );
        continue;
      }

      if (this.cache.has(record.summary.id)) {
        skipped++;
        emit(
          `Already analyzed ${record.summary.openingName}`,
          record.summary.id,
          record.summary.openingName
        );
        continue;
      }

      try {
        const result = await this.analyzeGame(record.summary.id, undefined, { persist: false });
        analyzed++;
        totalMistakes += result.mistakes.length;
        emit(
          `Stockfish analyzed ${record.summary.openingName} · ${result.mistakes.length} mistakes`,
          record.summary.id,
          record.summary.openingName
        );
        if (analyzed % 100 === 0) this.persistRuntimeCache();
      } catch (err) {
        failed++;
        const message = err instanceof Error ? err.message : String(err);
        failures.push({ gameId: record.summary.id, error: message });
        emit(
          `Could not analyze ${record.summary.id}: ${message}`,
          record.summary.id,
          record.summary.openingName
        );
      }
    }

    this.persistRuntimeCache();
    const finalProgress = emit('Full archive analysis complete', null, null);

    const result: AnalyzeAllResult = {
      totalGames: total,
      supportedGames: supported,
      analyzedGames: analyzed,
      skippedGames: skipped,
      skippedVariantGames: skippedVariant,
      failedGames: failed,
      totalMistakes,
      durationSeconds: Number(((Date.now() - started) / 1000).toFixed(2)),
      failures,
    };

    console.log(
      `[analyze-all] complete: ${result.analyzedGames} newly analyzed, ${result.skippedGames} cached, ${result.skippedVariantGames} Chess960 indexed, ${result.failedGames} failed, ${result.totalMistakes} total mistakes, ${result.durationSeconds}s, ${finalProgress.percent}%`
    );

    return result;
  }

  private async runFullAnalysis(
    record: StoredGameRecord,
    onProgress?: (info: { stage: string; current: number; total: number; percent: number }) => void
  ): Promise<StoredGameAnalysis> {
    const pgnChess = new Chess();
    pgnChess.loadPgn(record.pgn);

    // Map fenAfter -> [%clk ...]
    const clockByFen = new Map<string, string>();
    for (const c of pgnChess.getComments()) {
      const clkMatch = c.comment.match(/\[%clk\s+([^\]]+)\]/);
      if (clkMatch) {
        clockByFen.set(c.fen, clkMatch[1]);
      }
    }

    const verboseMoves = pgnChess.history({ verbose: true });
    const totalPlies = verboseMoves.length;
    const userColor = record.summary.userColor;

    // Collect all positions fen[0..totalPlies]
    const fens: string[] = [];
    const replay = new Chess();
    // Respect custom FEN header if present
    const headers = pgnChess.getHeaders();
    if (headers.FEN && headers.SetUp === '1') {
      replay.load(headers.FEN);
    }
    fens.push(replay.fen());
    for (const mv of verboseMoves) {
      replay.move(mv);
      fens.push(replay.fen());
    }

    // Stage 1: Fast full-game Stockfish 18 NNUE sweep (depth 10 across 2 workers)
    let completedSweep = 0;
    const stage1Results = await Promise.all(
      fens.map(async (fen, idx) => {
        const turn: PlayerColor = fen.split(' ')[1] === 'b' ? 'b' : 'w';
        const evalRes = await stockfishPool.evaluateFen(fen, { depth: 10, multiPv: 1 });
        completedSweep++;
        onProgress?.({
          stage: 'Scanning game moves with Stockfish 18 NNUE',
          current: completedSweep,
          total: fens.length,
          percent: Math.round((completedSweep / (fens.length + 6)) * 80),
        });

        const topLine = evalRes.lines[0];
        const cpFromTurn = topLine ? topLine.cpFromTurn : 0;
        const mateFromTurn = topLine ? topLine.mateFromTurn : null;
        const { whiteCp, whiteMate } = turnScoreToWhite(turn, cpFromTurn, mateFromTurn);
        return {
          idx,
          fen,
          turn,
          bestMoveUci: evalRes.bestMoveUci,
          pvUci: topLine?.pvUci ?? [],
          whiteCp,
          whiteMate,
        };
      })
    );

    // Identify candidate user mistakes for Stage 2 deep MultiPV-3 verification
    const candidateUserPlies: number[] = [];
    for (let i = 0; i < totalPlies; i++) {
      const mv = verboseMoves[i];
      if (mv.color !== userColor) continue;
      const playedUci = `${mv.from}${mv.to}${mv.promotion ?? ''}`;
      const before = stage1Results[i];
      const after = stage1Results[i + 1];

      if (before.bestMoveUci === playedUci) continue;

      const uBefore = whiteScoreToUser(userColor, before.whiteCp, before.whiteMate);
      const uAfter = whiteScoreToUser(userColor, after.whiteCp, after.whiteMate);
      const winLoss = cpToWinProb(uBefore.userCp) - cpToWinProb(uAfter.userCp);

      // Skip pedantic complaints when user remains overwhelmingly winning (+4.50+) and didn't miss mate in 1-2
      const stillCrushing =
        uAfter.userCp >= 450 &&
        (uBefore.userMate === null || uBefore.userMate > 2 || uBefore.userMate < 0);

      if (!stillCrushing && winLoss >= 0.055 && !(i < 4 && winLoss < 0.09)) {
        candidateUserPlies.push(i);
      }
    }

    // Stage 2: Deep depth-13 MultiPV-3 Stockfish verification on candidate mistakes!
    const deepVerified = new Map<
      number,
      {
        beforeEval: Awaited<ReturnType<typeof stockfishPool.evaluateFen>>;
        afterEval: Awaited<ReturnType<typeof stockfishPool.evaluateFen>>;
      }
    >();

    let deepDone = 0;
    await Promise.all(
      candidateUserPlies.map(async (plyIdx) => {
        const [beforeEval, afterEval] = await Promise.all([
          stockfishPool.evaluateFen(fens[plyIdx], { depth: 12, multiPv: 3 }),
          stockfishPool.evaluateFen(fens[plyIdx + 1], { depth: 12, multiPv: 1 }),
        ]);
        deepVerified.set(plyIdx, { beforeEval, afterEval });
        deepDone++;
        onProgress?.({
          stage: 'Deep-verifying critical mistakes (MultiPV 3)',
          current: deepDone,
          total: Math.max(1, candidateUserPlies.length),
          percent: 80 + Math.round((deepDone / Math.max(1, candidateUserPlies.length)) * 19),
        });
      })
    );

    const plies: PlyAnalysisSummary[] = [];
    const mistakes: StoredMistakeInternal[] = [];
    const whiteAccuracies: number[] = [];
    const blackAccuracies: number[] = [];

    for (let i = 0; i < totalPlies; i++) {
      const mv = verboseMoves[i];
      const ply = i + 1;
      const moveNumber = Math.floor(i / 2) + 1;
      const color = mv.color as PlayerColor;
      const playedUci = `${mv.from}${mv.to}${mv.promotion ?? ''}`;
      const fenBefore = fens[i];
      const fenAfter = fens[i + 1];

      let whiteBeforeCp = stage1Results[i].whiteCp;
      let whiteBeforeMate = stage1Results[i].whiteMate;
      let whiteAfterCp = stage1Results[i + 1].whiteCp;
      let whiteAfterMate = stage1Results[i + 1].whiteMate;
      let bestMoveUci = stage1Results[i].bestMoveUci;

      const deep = deepVerified.get(i);
      if (deep && deep.beforeEval.lines[0]) {
        const bTop = deep.beforeEval.lines[0];
        const bConv = turnScoreToWhite(color, bTop.cpFromTurn, bTop.mateFromTurn);
        whiteBeforeCp = bConv.whiteCp;
        whiteBeforeMate = bConv.whiteMate;
        bestMoveUci = deep.beforeEval.bestMoveUci;

        if (deep.afterEval.lines[0]) {
          const oppColor: PlayerColor = color === 'w' ? 'b' : 'w';
          const aTop = deep.afterEval.lines[0];
          const aConv = turnScoreToWhite(oppColor, aTop.cpFromTurn, aTop.mateFromTurn);
          whiteAfterCp = aConv.whiteCp;
          whiteAfterMate = aConv.whiteMate;
        }
      }

      const moverBefore = whiteScoreToUser(color, whiteBeforeCp, whiteBeforeMate);
      const moverAfter = whiteScoreToUser(color, whiteAfterCp, whiteAfterMate);
      const wpBefore = cpToWinProb(moverBefore.userCp);
      const wpAfter =
        bestMoveUci === playedUci ? wpBefore : Math.min(wpBefore, cpToWinProb(moverAfter.userCp));
      const winLoss = Math.max(0, wpBefore - wpAfter);

      const moveAcc = moveAccuracyPercent(wpBefore, wpAfter);
      if (color === 'w') whiteAccuracies.push(moveAcc);
      else blackAccuracies.push(moveAcc);

      const stillCrushing =
        moverAfter.userCp >= 450 &&
        (moverBefore.userMate === null || moverBefore.userMate > 2 || moverBefore.userMate < 0);

      let classification: MoveClassification = 'good';
      if (i < 4 && winLoss < 0.05) {
        classification = 'book';
      } else if (bestMoveUci === playedUci || winLoss <= 0.012) {
        classification = 'best';
      } else if (winLoss <= 0.032) {
        classification = 'excellent';
      } else if (winLoss < 0.06 || stillCrushing) {
        classification = 'good';
      } else if (winLoss < 0.105) {
        classification = 'inaccuracy';
      } else if (winLoss < 0.2) {
        classification = 'mistake';
      } else {
        classification = 'blunder';
      }

      let mistakeId: string | undefined;

      // Record actionable coach challenge if this was the user's move AND an inaccuracy/mistake/blunder!
      if (
        color === userColor &&
        (classification === 'inaccuracy' ||
          classification === 'mistake' ||
          classification === 'blunder') &&
        bestMoveUci &&
        bestMoveUci !== playedUci
      ) {
        const bestDetails = uciToMoveDetails(fenBefore, bestMoveUci);
        if (bestDetails) {
          mistakeId = `${record.summary.id}-ply-${ply}`;
          const prevMv = i > 0 ? verboseMoves[i - 1] : null;
          const phase = detectPhase(ply, fenBefore);

          const bestPvUci = deep?.beforeEval.lines[0]?.pvUci ?? stage1Results[i].pvUci;
          const bestPvSan = uciPvToSan(fenBefore, bestPvUci, 6);

          const oppRefutationUci =
            deep?.afterEval.lines[0]?.pvUci ?? stage1Results[i + 1].pvUci;
          const playedRefutationPvSan = uciPvToSan(fenAfter, oppRefutationUci, 5);

          const alternatives: AlternativeLine[] = [];
          if (deep?.beforeEval.lines) {
            for (const line of deep.beforeEval.lines.slice(0, 3)) {
              const altUci = line.pvUci[0];
              if (!altUci) continue;
              const altMove = uciToMoveDetails(fenBefore, altUci);
              if (!altMove) continue;
              const altWhite = turnScoreToWhite(color, line.cpFromTurn, line.mateFromTurn);
              const altUser = whiteScoreToUser(userColor, altWhite.whiteCp, altWhite.whiteMate);
              alternatives.push({
                san: altMove.san,
                uci: altUci,
                from: altMove.from,
                to: altMove.to,
                evalUserCp: altUser.userCp,
                evalUserMate: altUser.userMate,
                pvSan: uciPvToSan(fenBefore, line.pvUci, 5),
              });
            }
          }

          const { motif, coachExplanation, pieceNudge } = classifyMotifAndExplanation({
            fenBefore,
            phase,
            playedSan: mv.san,
            bestSan: bestDetails.san,
            bestPiece: bestDetails.piece,
            bestFrom: bestDetails.from,
            bestCaptured: bestDetails.captured,
            bestEvalUserCp: moverBefore.userCp,
            bestEvalUserMate: moverBefore.userMate,
            afterPlayedUserCp: moverAfter.userCp,
            afterPlayedUserMate: moverAfter.userMate,
            playedRefutationPvSan,
            fenAfterPlayed: fenAfter,
            oppFirstRefutationUci: oppRefutationUci[0],
          });

          mistakes.push({
            id: mistakeId,
            gameId: record.summary.id,
            ply,
            moveNumber,
            userColor,
            fenBefore,
            precedingMove: prevMv
              ? { san: prevMv.san, from: prevMv.from, to: prevMv.to }
              : null,
            playedMove: {
              san: mv.san,
              uci: playedUci,
              from: mv.from,
              to: mv.to,
            },
            evalBeforeUserCp: moverBefore.userCp,
            evalBeforeUserMate: moverBefore.userMate,
            evalAfterPlayedUserCp: moverAfter.userCp,
            evalAfterPlayedUserMate: moverAfter.userMate,
            winProbLost: Number(winLoss.toFixed(4)),
            severity: classification,
            phase,
            motif,
            pieceNudge,
            bestMove: {
              san: bestDetails.san,
              uci: bestDetails.uci,
              from: bestDetails.from,
              to: bestDetails.to,
            },
            bestEvalUserCp: moverBefore.userCp,
            bestEvalUserMate: moverBefore.userMate,
            bestPvSan,
            alternatives,
            playedRefutationPvSan,
            coachExplanation,
          });
        }
      }

      plies.push({
        ply,
        moveNumber,
        color,
        san: mv.san,
        uci: playedUci,
        from: mv.from,
        to: mv.to,
        fenBefore,
        fenAfter,
        clock: clockByFen.get(fenAfter),
        whiteEvalCp: whiteAfterCp,
        whiteMate: whiteAfterMate,
        classification,
        mistakeId,
      });
    }

    const avg = (arr: number[]) =>
      arr.length === 0 ? 100 : Math.round((arr.reduce((a, b) => a + b, 0) / arr.length) * 10) / 10;

    const whiteAccuracy = avg(whiteAccuracies);
    const blackAccuracy = avg(blackAccuracies);
    const userAccuracy = userColor === 'w' ? whiteAccuracy : blackAccuracy;

    onProgress?.({ stage: 'complete', current: totalPlies, total: totalPlies, percent: 100 });

    return {
      gameId: record.summary.id,
      analyzedAt: new Date().toISOString(),
      engineName: 'Stockfish 18 Lite NNUE',
      whiteAccuracy,
      blackAccuracy,
      userAccuracy,
      plies,
      mistakes,
    };
  }

  /**
   * Evaluates ANY legal move the player attempts on a mistake position using real Stockfish 18 NNUE!
   * Strictly conceals the best move until the player either solves it OR exhausts maxAttempts!
   */
  async evaluateAttempt(
    mistakeId: string,
    req: AttemptMoveRequest
  ): Promise<AttemptMoveResponse> {
    const found = this.getMistakeInternalById(mistakeId);
    if (!found) {
      throw new Error(`Mistake challenge not found: ${mistakeId}`);
    }
    const { mistake } = found;
    const chess = new Chess(mistake.fenBefore);

    const rawUci = req.moveUci.trim().toLowerCase();
    const from = rawUci.slice(0, 2);
    const to = rawUci.slice(2, 4);
    const promotion = rawUci.length >= 5 ? rawUci[4] : undefined;

    let appliedMove;
    try {
      appliedMove = chess.move({ from, to, promotion });
    } catch {
      throw new Error(`Illegal move: ${req.moveUci}`);
    }
    if (!appliedMove) {
      throw new Error(`Illegal move: ${req.moveUci}`);
    }

    const normalizedUci = `${appliedMove.from}${appliedMove.to}${appliedMove.promotion ?? ''}`;

    // Case 0: Player re-played the exact mistake they made in the real game!
    if (normalizedUci === mistake.playedMove.uci) {
      return {
        outcome: 'same_as_game',
        candidateMove: {
          san: appliedMove.san,
          uci: normalizedUci,
          from: appliedMove.from,
          to: appliedMove.to,
        },
        candidateEvalUserCp: mistake.evalAfterPlayedUserCp,
        candidateEvalUserMate: mistake.evalAfterPlayedUserMate,
        candidateRefutationPvSan: [],
        feedbackHeadline: `That's ${appliedMove.san} — the move from your actual game!`,
        feedbackDetail:
          'We paused here because that move was a mistake. Try a different move on the board (this did not use up an attempt).',
        mastery: progressStore.getRecord(mistake.id),
      };
    }

    // Case 1: Exact match with Stockfish's #1 best move!
    if (normalizedUci === mistake.bestMove.uci) {
      const wasBlindFirstTry = req.attemptNumber === 1;
      const updatedMastery = progressStore.recordSuccess(mistake.id, wasBlindFirstTry);
      return {
        outcome: 'best',
        candidateMove: {
          san: appliedMove.san,
          uci: normalizedUci,
          from: appliedMove.from,
          to: appliedMove.to,
        },
        candidateEvalUserCp: mistake.bestEvalUserCp,
        candidateEvalUserMate: mistake.bestEvalUserMate,
        candidateRefutationPvSan: mistake.bestPvSan.slice(1),
        feedbackHeadline: `Stockfish #1 Move Found: ${appliedMove.san}!`,
        feedbackDetail: `Spot on! ${appliedMove.san} keeps ${formatEvalLabel(
          mistake.bestEvalUserCp,
          mistake.bestEvalUserMate
        )} instead of your game move ${mistake.playedMove.san} (${formatEvalLabel(
          mistake.evalAfterPlayedUserCp,
          mistake.evalAfterPlayedUserMate
        )}).`,
        mastery: updatedMastery,
        solution: this.toSolutionReveal(mistake),
      };
    }

    // Case 2: Live Stockfish 18 NNUE evaluation of the player's candidate move!
    const fenAfterCandidate = chess.fen();
    const oppColor: PlayerColor = mistake.userColor === 'w' ? 'b' : 'w';

    // Check if candidate move exists in pre-computed MultiPV alternatives first, otherwise evaluate live at depth 12
    const knownAlt = mistake.alternatives.find((a) => a.uci === normalizedUci);
    let candidateUserCp: number;
    let candidateUserMate: number | null;
    let candidateRefutationPvSan: string[];

    if (knownAlt) {
      candidateUserCp = knownAlt.evalUserCp;
      candidateUserMate = knownAlt.evalUserMate;
      candidateRefutationPvSan = knownAlt.pvSan.slice(1);
    } else {
      const evalAfter = await stockfishPool.evaluateFen(fenAfterCandidate, {
        depth: 12,
        multiPv: 1,
      });
      const top = evalAfter.lines[0];
      const cpFromOpp = top ? top.cpFromTurn : 0;
      const mateFromOpp = top ? top.mateFromTurn : null;
      const whiteScore = turnScoreToWhite(oppColor, cpFromOpp, mateFromOpp);
      const userScore = whiteScoreToUser(
        mistake.userColor,
        whiteScore.whiteCp,
        whiteScore.whiteMate
      );
      candidateUserCp = userScore.userCp;
      candidateUserMate = userScore.userMate;
      candidateRefutationPvSan = uciPvToSan(fenAfterCandidate, top?.pvUci ?? [], 5);
    }

    const bestWp = cpToWinProb(mistake.bestEvalUserCp);
    const candWp = cpToWinProb(candidateUserCp);
    const playedWp = cpToWinProb(mistake.evalAfterPlayedUserCp);

    // Check if candidate is a strong Stockfish-approved fix (within 4.5% win-prob of #1 AND meaningfully better than game move)
    const isStrongFix =
      bestWp - candWp <= 0.045 &&
      candWp - playedWp >= 0.045 &&
      !(mistake.bestEvalUserMate !== null && mistake.bestEvalUserMate > 0 && (candidateUserMate === null || candidateUserMate <= 0));

    if (isStrongFix) {
      const wasBlindFirstTry = req.attemptNumber === 1;
      const updatedMastery = progressStore.recordSuccess(mistake.id, wasBlindFirstTry);
      return {
        outcome: 'great',
        candidateMove: {
          san: appliedMove.san,
          uci: normalizedUci,
          from: appliedMove.from,
          to: appliedMove.to,
        },
        candidateEvalUserCp: candidateUserCp,
        candidateEvalUserMate: candidateUserMate,
        candidateRefutationPvSan,
        feedbackHeadline: `Strong Improvement: ${appliedMove.san}!`,
        feedbackDetail: `${appliedMove.san} (${formatEvalLabel(
          candidateUserCp,
          candidateUserMate
        )}) cleanly fixes your game mistake ${mistake.playedMove.san} (${formatEvalLabel(
          mistake.evalAfterPlayedUserCp,
          mistake.evalAfterPlayedUserMate
        )}). Stockfish's absolute top pick was ${mistake.bestMove.san} (${formatEvalLabel(
          mistake.bestEvalUserCp,
          mistake.bestEvalUserMate
        )}).`,
        mastery: updatedMastery,
        solution: this.toSolutionReveal(mistake),
      };
    }

    // Player's attempt failed!
    const oppPunishText = candidateRefutationPvSan[0]
      ? ` Opponent replies ${candidateRefutationPvSan.slice(0, 3).join(' ')}.`
      : '';

    // If user configured > 1 maxAttempts and still has tries left, DO NOT reveal best move yet!
    if (req.attemptNumber < req.maxAttempts) {
      const remaining = req.maxAttempts - req.attemptNumber;
      return {
        outcome: 'retry',
        candidateMove: {
          san: appliedMove.san,
          uci: normalizedUci,
          from: appliedMove.from,
          to: appliedMove.to,
        },
        candidateEvalUserCp: candidateUserCp,
        candidateEvalUserMate: candidateUserMate,
        candidateRefutationPvSan,
        feedbackHeadline: `${appliedMove.san} doesn't hold (${formatEvalLabel(
          candidateUserCp,
          candidateUserMate
        )})`,
        feedbackDetail: `Stockfish spots a flaw:${oppPunishText} You have ${remaining} ${
          remaining === 1 ? 'try' : 'tries'
        } left before the best move is revealed!`,
        mastery: progressStore.getRecord(mistake.id),
      };
    }

    // Player exhausted attempts -> FAIL! Record in Spaced Repetition Vault AND NOW reveal Stockfish's best move!
    const updatedMastery = progressStore.recordFailure(mistake.id);
    return {
      outcome: 'failed_revealed',
      candidateMove: {
        san: appliedMove.san,
        uci: normalizedUci,
        from: appliedMove.from,
        to: appliedMove.to,
      },
      candidateEvalUserCp: candidateUserCp,
      candidateEvalUserMate: candidateUserMate,
      candidateRefutationPvSan,
      feedbackHeadline: `${appliedMove.san} falls short (${formatEvalLabel(
        candidateUserCp,
        candidateUserMate
      )}) — Best was ${mistake.bestMove.san}`,
      feedbackDetail: `After ${appliedMove.san},${
        oppPunishText || ' the position stays difficult.'
      } ${mistake.coachExplanation}`,
      mastery: updatedMastery,
      solution: this.toSolutionReveal(mistake),
    };
  }

  buildGameDetailResponse(record: StoredGameRecord): GameDetailResponse {
    this.ensureLoaded();
    const cached = this.cache.get(record.summary.id);
    const enrichedSummary = this.enrichGameSummary(record);

    if (!cached) {
      return {
        summary: enrichedSummary,
        pgn: record.pgn,
        analyzed: false,
        plies: [],
        mistakes: [],
      };
    }

    return {
      summary: enrichedSummary,
      pgn: record.pgn,
      analyzed: true,
      plies: cached.plies,
      mistakes: cached.mistakes.map((m) => this.toPublicChallenge(m, record)),
      whiteAccuracy: cached.whiteAccuracy,
      blackAccuracy: cached.blackAccuracy,
      userAccuracy: cached.userAccuracy,
    };
  }

  enrichGameSummary(record: StoredGameRecord): GameSummary {
    this.ensureLoaded();
    const cached = this.cache.get(record.summary.id);
    if (!cached) {
      return {
        ...record.summary,
        analyzed: false,
      };
    }

    let blunders = 0;
    let mistakes = 0;
    let inaccuracies = 0;
    let mastered = 0;

    for (const m of cached.mistakes) {
      if (m.severity === 'blunder') blunders++;
      else if (m.severity === 'mistake') mistakes++;
      else inaccuracies++;

      if (progressStore.getRecord(m.id).status === 'mastered') {
        mastered++;
      }
    }

    return {
      ...record.summary,
      analyzed: true,
      accuracy: cached.userAccuracy,
      blundersCount: blunders,
      mistakesCount: mistakes,
      inaccuraciesCount: inaccuracies,
      totalMistakesCount: cached.mistakes.length,
      masteredMistakesCount: mastered,
    };
  }
}

export const gameAnalyzer = new GameAnalyzerService();
