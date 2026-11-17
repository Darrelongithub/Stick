import { Chess, PieceSymbol } from 'chess.js';
import type {
  GamePhase,
  MasteryState,
  MistakeMotif,
  MistakeSeverity,
  MoveClassification,
  PlayerColor,
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
    description: 'One clean recall away',
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

export function computeMaterialBalance(fen: string): {
  whiteDiff: number;
  capturedByWhite: PieceSymbol[];
  capturedByBlack: PieceSymbol[];
} {
  const startCounts: Record<PieceSymbol, number> = { p: 8, n: 2, b: 2, r: 2, q: 1, k: 1 };
  const whiteLeft: Record<PieceSymbol, number> = { p: 0, n: 0, b: 0, r: 0, q: 0, k: 0 };
  const blackLeft: Record<PieceSymbol, number> = { p: 0, n: 0, b: 0, r: 0, q: 0, k: 0 };

  const board = fen.split(' ')[0];
  for (const ch of board) {
    const lower = ch.toLowerCase() as PieceSymbol;
    if (!(lower in startCounts)) continue;
    if (ch === ch.toUpperCase()) whiteLeft[lower]++;
    else blackLeft[lower]++;
  }

  const values: Record<PieceSymbol, number> = { p: 1, n: 3, b: 3, r: 5, q: 9, k: 0 };
  let whitePts = 0;
  let blackPts = 0;
  const order: PieceSymbol[] = ['q', 'r', 'b', 'n', 'p'];
  const capturedByWhite: PieceSymbol[] = [];
  const capturedByBlack: PieceSymbol[] = [];

  for (const p of order) {
    whitePts += whiteLeft[p] * values[p];
    blackPts += blackLeft[p] * values[p];
    const missingBlack = Math.max(0, startCounts[p] - blackLeft[p]);
    const missingWhite = Math.max(0, startCounts[p] - whiteLeft[p]);
    for (let i = 0; i < missingBlack; i++) capturedByWhite.push(p);
    for (let i = 0; i < missingWhite; i++) capturedByBlack.push(p);
  }

  return {
    whiteDiff: whitePts - blackPts,
    capturedByWhite,
    capturedByBlack,
  };
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
 * Defense-in-depth against legacy seeded hints. A hint may name a theme or piece,
 * but it must never expose an origin square, castling instruction, or the move.
 */
export function safePieceHint(rawHint: string): string {
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
