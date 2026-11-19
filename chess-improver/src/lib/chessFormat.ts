import { Chess, PieceSymbol } from 'chess.js';
import type {
  ArchiveOverviewResponse,
  GamePhase,
  MasteryState,
  MistakeMotif,
  MistakeSeverity,
  MoveClassification,
  PlayerColor,
  PlyAnalysisSummary,
} from '../../shared/types';

export const MOTIF_LABELS: Record<MistakeMotif, string> = {
  missed_mate: 'Missed Checkmate',
  allowed_mate: 'Allowed Checkmate',
  material_loss: 'Hanging Piece',
  missed_tactic: 'Missed Tactic',
  king_safety: 'King Safety',
  opening_principle: 'Opening Principle',
  endgame_technique: 'Endgame Technique',
  positional_slip: 'Positional Slip',
};

export const PHASE_LABELS: Record<GamePhase, string> = {
  opening: 'Opening',
  middlegame: 'Middlegame',
  endgame: 'Endgame',
};

export const MASTERY_META: Record<
  MasteryState,
  { label: string; description: string; pillClass: string; dotClass: string; rank: number }
> = {
  unseen: {
    label: 'Unseen',
    description: 'Not drilled yet',
    pillClass: 'border-[var(--line)] bg-[var(--surface-deep)]/[0.05] text-[var(--ink-secondary)]',
    dotClass: 'bg-[var(--surface-deep)]',
    rank: 2,
  },
  needs_review: {
    label: 'Needs Review',
    description: 'Missed — due first',
    pillClass: 'border-[var(--warm)]/35 bg-[var(--warm)]/10 text-[var(--warm-soft)]',
    dotClass: 'bg-[var(--warm)]',
    rank: 0,
  },
  learning: {
    label: 'Learning',
    description: 'Keep practicing clean blind recalls',
    pillClass: 'border-[var(--amber)]/35 bg-[var(--amber)]/10 text-[var(--amber)]',
    dotClass: 'bg-[var(--amber)]',
    rank: 1,
  },
  mastered: {
    label: 'Mastered',
    description: 'Recalled cleanly',
    pillClass: 'border-[var(--cool)]/35 bg-[var(--cool-bg)] text-[var(--cool)]',
    dotClass: 'bg-[var(--cool)]',
    rank: 3,
  },
};

export function cx(...parts: Array<string | false | null | undefined>): string {
  return parts.filter(Boolean).join(' ');
}

export function formatScore(cp: number, mate: number | null): string {
  if (mate !== null) {
    if (mate === 0) return '#';
    return mate > 0 ? `+M${mate}` : `-M${Math.abs(mate)}`;
  }
  const val = cp / 100;
  if (Math.abs(val) >= 10) {
    return `${val >= 0 ? '+' : ''}${val.toFixed(1)}`;
  }
  return `${val >= 0 ? '+' : ''}${val.toFixed(2)}`;
}

/** Chess.com-style winning probability curve, clamped so a huge score still leaves a sliver. */
export function evalToWinFraction(cp: number, mate: number | null): number {
  if (mate !== null) {
    if (mate > 0) return 0.985;
    if (mate < 0) return 0.015;
    return cp >= 0 ? 0.985 : 0.015;
  }
  const clamped = Math.max(-4000, Math.min(4000, cp));
  return 1 / (1 + Math.exp(-0.00368208 * clamped));
}

export function formatClock(clk?: string): string | null {
  if (!clk) return null;
  // Turn 0:00:58.7 -> 0:58, or 0:09:45.2 -> 9:45
  const parts = clk.split(':');
  if (parts.length === 3) {
    const hrs = parseInt(parts[0], 10);
    const mins = parseInt(parts[1], 10);
    const secsFloat = parseFloat(parts[2]);
    if (hrs > 0) {
      return `${hrs}:${String(mins).padStart(2, '0')}:${String(Math.floor(secsFloat)).padStart(2, '0')}`;
    }
    if (mins === 0 && secsFloat < 20) {
      return `0:${secsFloat.toFixed(1).padStart(4, '0')}`;
    }
    return `${mins}:${String(Math.floor(secsFloat)).padStart(2, '0')}`;
  }
  return clk;
}

export function formatGameDate(dotDate: string): string {
  const match = dotDate.match(/^(\d{4})[.-](\d{2})[.-](\d{2})/);
  if (!match) return dotDate;
  const months = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec'];
  const month = months[Math.max(0, Math.min(11, parseInt(match[2], 10) - 1))];
  return `${month} ${parseInt(match[3], 10)}, ${match[1]}`;
}

export function shortOpening(name: string, max = 34): string {
  if (name.length <= max) return name;
  return `${name.slice(0, max - 1).trimEnd()}…`;
}

/** Overview win/loss/draw totals describe finished archive games only. */
export function archiveWinRate(record: Pick<ArchiveOverviewResponse, 'wins' | 'losses' | 'draws'>): number | null {
  const total = record.wins + record.losses + record.draws;
  return total ? 100 * record.wins / total : null;
}

/** Never combine ratings from different time controls into one trajectory. */
export function preferredRatingSeries(rows: ArchiveOverviewResponse['eloTimeline']) {
  const choices = [ ['rapidElo', 'Rapid'], ['blitzElo', 'Blitz'], ['bulletElo', 'Bullet'] ] as const;
  const selected = choices.find(([key]) => rows.some(row => row[key] !== null));
  return { label: selected?.[1] ?? null, points: selected ? rows.flatMap((row, index) => {
    const value = row[selected[0]];
    return value === null ? [] : [{ month: row.month, value, index }];
  }) : [] };
}

export function computeMaterialBalance(fen: string): { whiteDiff: number } {
  const values: Record<string, number> = { p: 1, n: 3, b: 3, r: 5, q: 9, k: 0 };
  let whiteDiff = 0;
  for (const ch of fen.split(' ')[0]) {
    const value = values[ch.toLowerCase()];
    if (value !== undefined) whiteDiff += ch === ch.toUpperCase() ? value : -value;
  }
  return { whiteDiff };
}

/** Captures require history: a FEN alone cannot distinguish odds or promotions. */
export function capturedPiecesByFen(pgn: string): Map<string, { white: PieceSymbol[]; black: PieceSymbol[] }> {
  const result = new Map<string, { white: PieceSymbol[]; black: PieceSymbol[] }>();
  try {
    const chess = new Chess();
    chess.loadPgn(pgn);
    const moves = chess.history({ verbose: true });
    const white: PieceSymbol[] = [], black: PieceSymbol[] = [];
    if (moves[0]) result.set(moves[0].before, { white: [], black: [] });
    for (const move of moves) {
      if (move.captured) (move.color === 'w' ? white : black).push(move.captured);
      result.set(move.after, { white: [...white], black: [...black] });
    }
  } catch { /* Hide capture history if a game cannot be replayed. */ }
  return result;
}

/** Clock comments describe the time remaining after each recorded move. */
export function clocksAtFen(plies: PlyAnalysisSummary[], fen: string): { w: string | null; b: string | null } {
  const clocks: { w: string | null; b: string | null } = { w: null, b: null };
  const positionIndex = plies.findIndex(ply => ply.fenAfter === fen);
  if (positionIndex < 0) return clocks;
  const seen = new Set<PlayerColor>();
  for (let i = positionIndex; i >= 0 && seen.size < 2; i--) {
    const ply = plies[i];
    if (!seen.has(ply.color)) {
      clocks[ply.color] = ply.clock ?? null;
      seen.add(ply.color);
    }
  }
  return clocks;
}

/** Group by actual move number and color, including Black-to-move FEN starts. */
export function groupMoveSheet(plies: PlyAnalysisSummary[]): Array<{ number: number; white?: PlyAnalysisSummary; black?: PlyAnalysisSummary }> {
  const groups = new Map<number, { number: number; white?: PlyAnalysisSummary; black?: PlyAnalysisSummary }>();
  for (const ply of plies) {
    let group = groups.get(ply.moveNumber);
    if (!group) { group = { number: ply.moveNumber }; groups.set(ply.moveNumber, group); }
    if (ply.color === 'w') group.white = ply;
    else group.black = ply;
  }
  return [...groups.values()];
}

/** PGN move label for a line starting at an arbitrary FEN, including Black. */
export function lineMoveLabel(startFen: string, index: number): string {
  const fields = startFen.split(' ');
  const startNumber = Number(fields[5]) || 1;
  const startBlack = fields[1] === 'b' ? 1 : 0;
  const absolute = startBlack + index;
  return `${startNumber + Math.floor(absolute / 2)}${absolute % 2 ? '...' : '.'}`;
}

export function replaySanLine(
  startFen: string,
  sanMoves: string[],
  upToIndex: number
): { fen: string; lastMove: { from: string; to: string } | null } {
  const chess = new Chess(startFen);
  let lastMove: { from: string; to: string } | null = null;
  for (let i = 0; i <= upToIndex && i < sanMoves.length; i++) {
    try {
      const m = chess.move(sanMoves[i]);
      if (!m) break;
      lastMove = { from: m.from, to: m.to };
    } catch {
      break;
    }
  }
  return { fen: chess.fen(), lastMove };
}

export function applyUciToFen(
  startFen: string,
  uci: string
): {
  fen: string;
  san: string | null;
  lastMove: { from: string; to: string } | null;
} {
  const chess = new Chess(startFen);
  try {
    const move = chess.move({
      from: uci.slice(0, 2),
      to: uci.slice(2, 4),
      promotion: uci.length >= 5 ? uci[4] : undefined,
    });
    return {
      fen: chess.fen(),
      san: move.san,
      lastMove: { from: move.from, to: move.to },
    };
  } catch {
    return { fen: startFen, san: null, lastMove: null };
  }
}

export function sanToMoveDetails(
  fen: string,
  san: string
): { from: string; to: string; san: string; uci: string } | null {
  if (!san) return null;
  const chess = new Chess(fen);
  try {
    const m = chess.move(san);
    return {
      from: m.from,
      to: m.to,
      san: m.san,
      uci: `${m.from}${m.to}${m.promotion ?? ''}`,
    };
  } catch {
    return null;
  }
}

/**
 * Defense-in-depth against legacy seeded hints: never expose a piece, square,
 * castling instruction, or move while a drill is blind.
 */
export function safePieceHint(_rawHint: string): string {
  return 'Scan checks, captures and threats in that order. The best move stays hidden until you finish the drill.';
}

export function severityBadgeMeta(severity: MistakeSeverity) {
  switch (severity) {
    case 'blunder':
      return {
        glyph: '??',
        label: 'Blunder',
        pillClass: 'bg-[var(--warm)]/15 text-[var(--warm-soft)] border-[var(--warm)]/35',
        squareBg: '#ff6b57',
      };
    case 'mistake':
      return {
        glyph: '?',
        label: 'Mistake',
        pillClass: 'bg-[var(--amber)]/15 text-[var(--amber)] border-[var(--amber)]/35',
        squareBg: '#ffb340',
      };
    case 'inaccuracy':
      return {
        glyph: '?!',
        label: 'Inaccuracy',
        pillClass: 'bg-[var(--amber)]/15 text-[var(--amber)] border-[var(--amber)]/35',
        squareBg: '#ffb340',
      };
  }
}

export function classificationGlyph(cls: MoveClassification): {
  symbol: string;
  colorClass: string;
} | null {
  switch (cls) {
    case 'blunder':
      return { symbol: '??', colorClass: 'text-[var(--warm-soft)]' };
    case 'mistake':
      return { symbol: '?', colorClass: 'text-[var(--amber)]' };
    case 'inaccuracy':
      return { symbol: '?!', colorClass: 'text-[var(--amber)]' };
    case 'best':
      return { symbol: '★', colorClass: 'text-[var(--cool)]' };
    default:
      return null;
  }
}

export function whiteEvalFromUserEval(
  userColor: PlayerColor,
  userCp: number,
  userMate: number | null
): { whiteCp: number; whiteMate: number | null } {
  if (userColor === 'w') {
    return { whiteCp: userCp, whiteMate: userMate };
  }
  return {
    whiteCp: -userCp,
    whiteMate: userMate === null ? null : -userMate,
  };
}
