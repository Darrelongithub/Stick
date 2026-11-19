import React, { useEffect, useMemo, useRef, useState } from 'react';
import { Chess, PieceSymbol } from 'chess.js';
import {
  ArrowRight,
  BookOpen,
  Brain,
  CheckCircle2,
  ChevronDown,
  ChevronRight,
  ChevronUp,
  CircleHelp,
  Clock,
  Eye,
  EyeOff,
  Flame,
  Lightbulb,
  MousePointer2,
  RotateCcw,
  Sparkles,
  Target,
  Trophy,
} from 'lucide-react';
import type {
  AttemptMoveResponse,
  GameDetailResponse,
  MistakeChallengePublic,
  MistakeMasteryRecord,
  PlayerColor,
  PlyAnalysisSummary,
} from '../../shared/types';
import { api } from '../lib/api';
import type { AnalysisProgress } from '../lib/api';
import {
  applyUciToFen,
  classificationGlyph,
  computeMaterialBalance,
  capturedPiecesByFen,
  clocksAtFen,
  groupMoveSheet,
  cx,
  formatClock,
  formatGameDate,
  formatScore,
  MOTIF_LABELS,
  PHASE_LABELS,
  replaySanLine,
  safePieceHint,
  severityBadgeMeta,
} from '../lib/chessFormat';
import { soundEngine } from '../lib/sound';
import { ChessBoard, BoardArrow, BoardThemeName, SquareBadge } from './ChessBoard';
import { EvalBar } from './EvalBar';
import { EvalGraph } from './EvalGraph';
import { PieceSvg } from './PieceSvg';
import { SolutionRevealCard, PvLineKind } from './SolutionRevealCard';
import {
  EmptyState,
  Eyebrow,
  MasteryPill,
  Pill,
  ProgressBar,
  ProgressRing,
  SegmentedControl,
  Spinner,
  SurfaceCard,
} from './ui';

interface CoachPanelProps {
  game: GameDetailResponse;
  analysisProgress: AnalysisProgress | null;
  initialMistakeId?: string | null;
  onAnalyze: () => void;
  onRefreshOverview: () => void;
  onOpenLibrary: () => void;
  onOpenVault: () => void;
}

type SessionPhase = 'game' | 'redrill' | 'summary' | 'complete';

function PlayerStrip({
  name,
  elo,
  color,
  isUser,
  active,
  clock,
  captured,
  capturedPieceColor,
  materialDiff,
}: {
  name: string;
  elo: number | null;
  color: PlayerColor;
  isUser: boolean;
  active: boolean;
  clock: string | null;
  captured: PieceSymbol[];
  capturedPieceColor: PlayerColor;
  materialDiff: number;
}) {
  return (
    <div
      className={cx(
        'flex min-h-[46px] items-center justify-between gap-3 rounded-lg border px-2.5 py-1.5 transition',
        active
          ? 'border-[var(--a)]/35 bg-[var(--a-soft)]'
          : 'border-[var(--line)] bg-[var(--surface)]/85'
      )}
    >
      <div className="flex min-w-0 items-center gap-2.5">
        <div
          className={cx(
            'flex h-8 w-8 shrink-0 items-center justify-center rounded-full border text-xs font-bold',
            color === 'w'
              ? 'border-[var(--line-strong)] bg-[var(--surface)] text-[var(--ink)]'
              : 'border-[var(--surface-deep)] bg-[var(--surface-deep)] text-[var(--ink)]'
          )}
        >
          {name.trim().charAt(0).toUpperCase() || '?'}
        </div>
        <div className="min-w-0">
          <div className="flex items-center gap-1.5">
            <p className="truncate text-xs font-semibold text-[var(--ink-soft)]">{name}</p>
            {isUser && (
              <span className="rounded bg-[var(--a)]/15 px-1 py-0.5 text-[8px] font-bold tracking-wider text-[var(--a)]">
                YOU
              </span>
            )}
          </div>
          <p className="font-mono-tabular text-[10px] text-[var(--ink-muted)]">
            {elo ? `Elo ${elo}` : 'Unrated'}
            {materialDiff > 0 && <span className="ml-2 text-[var(--cool-soft)]">+{materialDiff}</span>}
          </p>
        </div>
        {captured.length > 0 && (
          <div className="ml-1 hidden items-center gap-0.5 sm:flex">
            {captured.map((piece, idx) => (
              <span key={`${piece}-${idx}`} className="h-4 w-4 opacity-80">
                <PieceSvg color={capturedPieceColor} piece={piece} />
              </span>
            ))}
          </div>
        )}
      </div>

      <div
        className={cx(
          'flex shrink-0 items-center gap-1.5 rounded-md border px-2 py-1 font-mono-tabular text-xs font-semibold',
          active
            ? 'border-[var(--a)]/35 bg-[var(--surface)] text-[var(--ink)]'
            : 'border-[var(--line)] bg-[var(--surface)]/70 text-[var(--ink-secondary)]'
        )}
        title="Clock at this point in the game"
      >
        <Clock className="h-3 w-3" /> {clock ?? '--:--'}
      </div>
    </div>
  );
}

function MoveSheet({
  plies,
  activePly,
  onSelectPly,
  open,
  onToggle,
}: {
  plies: PlyAnalysisSummary[];
  activePly: number | null;
  onSelectPly: (ply: PlyAnalysisSummary) => void;
  open: boolean;
  onToggle: () => void;
}) {
  const pairs = useMemo(() => groupMoveSheet(plies), [plies]);

  const renderMove = (ply?: PlyAnalysisSummary) => {
    if (!ply) return <span className="text-[var(--ink-dim)]">…</span>;
    const glyph = classificationGlyph(ply.classification);
    const active = activePly === ply.ply;
    return (
      <button
        type="button"
        onClick={() => onSelectPly(ply)}
        className={cx(
          'flex w-full items-center justify-between gap-2 rounded-md px-2 py-1 text-left font-mono-tabular text-[11px] transition',
          active
            ? 'bg-[var(--a)]/20 text-[var(--a)] ring-1 ring-[var(--a)]/40'
            : 'text-[var(--ink-soft)] hover:bg-[var(--surface)]'
        )}
        title={`Replay ${ply.san} from the actual game`}
      >
        <span>{ply.san}</span>
        {glyph && <span className={cx('text-[10px] font-bold', glyph.colorClass)}>{glyph.symbol}</span>}
      </button>
    );
  };

  return (
    <SurfaceCard className="overflow-hidden">
      <button
        type="button"
        onClick={onToggle}
        className="flex w-full items-center justify-between px-4 py-3 text-left transition hover:bg-[var(--surface)]"
      >
        <span className="flex items-center gap-2 text-xs font-semibold text-[var(--ink-soft)]">
          <BookOpen className="h-3.5 w-3.5 text-[var(--a)]" /> PGN move sheet
        </span>
        <span className="flex items-center gap-2 text-[10px] text-[var(--ink-muted)]">
          {plies.length} plies {open ? <ChevronUp className="h-3.5 w-3.5" /> : <ChevronDown className="h-3.5 w-3.5" />}
        </span>
      </button>
      {open && (
        <div className="max-h-64 overflow-y-auto border-t border-[var(--line)] px-2 py-2">
          <div className="grid grid-cols-[38px_1fr_1fr] gap-1 px-1 pb-1 text-[9px] font-semibold uppercase tracking-wider text-[var(--ink-dim)]">
            <span>#</span>
            <span>White</span>
            <span>Black</span>
          </div>
          {pairs.map((pair) => (
            <div key={pair.number} className="grid grid-cols-[38px_1fr_1fr] items-center gap-1">
              <span className="px-2 font-mono-tabular text-[10px] text-[var(--ink-dim)]">{pair.number}.</span>
              {renderMove(pair.white)}
              {renderMove(pair.black)}
            </div>
          ))}
        </div>
      )}
    </SurfaceCard>
  );
}

export const CoachPanel: React.FC<CoachPanelProps> = ({
  game,
  analysisProgress,
  initialMistakeId = null,
  onAnalyze,
  onRefreshOverview,
  onOpenLibrary,
  onOpenVault,
}) => {
  const mistakes = game.mistakes;
  const initialIndex = useMemo(() => {
    if (!initialMistakeId) return 0;
    const idx = mistakes.findIndex((m) => m.id === initialMistakeId);
    return idx >= 0 ? idx : 0;
  }, [initialMistakeId, mistakes]);

  const [phase, setPhase] = useState<SessionPhase>('game');
  const [queueIndex, setQueueIndex] = useState(initialIndex);
  const [redrillQueue, setRedrillQueue] = useState<MistakeChallengePublic[]>([]);
  const [redrillIndex, setRedrillIndex] = useState(0);
  const [roundKey, setRoundKey] = useState(0);
  const [missedIds, setMissedIds] = useState<Set<string>>(new Set());
  const [resolvedIds, setResolvedIds] = useState<Set<string>>(new Set());
  const [redrillSolvedIds, setRedrillSolvedIds] = useState<Set<string>>(new Set());
  const [masteryOverrides, setMasteryOverrides] = useState<Record<string, MistakeMasteryRecord>>({});

  const [attemptNumber, setAttemptNumber] = useState(1);
  const [maxAttempts, setMaxAttempts] = useState<1 | 2>(1);
  const [attemptResponse, setAttemptResponse] = useState<AttemptMoveResponse | null>(null);
  const [attempting, setAttempting] = useState(false);
  const [attemptError, setAttemptError] = useState<string | null>(null);
  const [hintOpen, setHintOpen] = useState(false);
  const [previewMode, setPreviewMode] = useState(false);
  const [practiceMode, setPracticeMode] = useState(false);
  const [practiceSolved, setPracticeSolved] = useState(false);
  const [practiceFeedback, setPracticeFeedback] = useState<string | null>(null);
  const [activeLine, setActiveLine] = useState<PvLineKind>(null);
  const [activeIndex, setActiveIndex] = useState(-1);

  const [orientation, setOrientation] = useState<PlayerColor>(game.summary.userColor);
  const [boardTheme, setBoardTheme] = useState<BoardThemeName>('walnut');
  const [boardFen, setBoardFen] = useState(
    mistakes[initialIndex]?.fenBefore ?? new Chess().fen()
  );
  const [lastMove, setLastMove] = useState<{ from: string; to: string } | null>(
    mistakes[initialIndex]?.precedingMove ?? null
  );
  const [arrows, setArrows] = useState<BoardArrow[]>([]);
  const [badge, setBadge] = useState<SquareBadge | null>(null);
  const [boardDetached, setBoardDetached] = useState(false);
  const [viewedPly, setViewedPly] = useState<number | null>(null);
  const [moveSheetOpen, setMoveSheetOpen] = useState(false);
  const attemptLockRef = useRef(false);

  const current: MistakeChallengePublic | null =
    phase === 'game'
      ? (mistakes[queueIndex] ?? null)
      : phase === 'redrill'
        ? (redrillQueue[redrillIndex] ?? null)
        : null;

  const challengeKey = current ? `${phase}:${roundKey}:${current.id}` : `none:${phase}`;
  const activeChallengeKey = useRef(challengeKey);
  activeChallengeKey.current = challengeKey;
  const feedbackRef = useRef<HTMLDivElement | null>(null);

  useEffect(() => {
    attemptLockRef.current = false;
    setAttempting(false);
    setAttemptNumber(1);
    setAttemptResponse(null);
    setAttemptError(null);
    setHintOpen(false);
    setPreviewMode(false);
    setPracticeMode(false);
    setPracticeSolved(false);
    setPracticeFeedback(null);
    setActiveLine(null);
    setActiveIndex(-1);
    setBoardDetached(false);
    setViewedPly(null);
    setArrows([]);
    setBadge(null);
    if (current) {
      setBoardFen(current.fenBefore);
      setLastMove(current.precedingMove ? { from: current.precedingMove.from, to: current.precedingMove.to } : null);
      setOrientation(current.userColor);
    }
    // challengeKey intentionally drives the reset when index/phase/round changes.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [challengeKey]);

  const currentMastery = current
    ? (masteryOverrides[current.id] ?? current.mastery)
    : null;
  const hasSolution = Boolean(attemptResponse?.solution);
  const solved = attemptResponse?.outcome === 'great';
  const isBlindRetest = phase === 'redrill';
  const turnColor: PlayerColor = boardFen.split(' ')[1] === 'b' ? 'b' : 'w';
  const activePly = viewedPly ?? current?.ply ?? null;
  const severityMeta = current ? severityBadgeMeta(current.severity) : null;

  const capturesByFen = useMemo(() => capturedPiecesByFen(game.pgn), [game.pgn]);
  const material = useMemo(() => computeMaterialBalance(boardFen), [boardFen]);
  const captured = capturesByFen.get(boardFen);
  const clocks = useMemo(() => clocksAtFen(game.plies, boardFen), [game.plies, boardFen]);
  const previewFen = useMemo(() => {
    const chess = new Chess();
    try {
      chess.loadPgn(game.pgn);
      return chess.fen();
    } catch {
      return chess.fen();
    }
  }, [game.pgn]);

  const resetBoardToPuzzle = () => {
    if (!current) return;
    setBoardFen(current.fenBefore);
    setLastMove(current.precedingMove ? { from: current.precedingMove.from, to: current.precedingMove.to } : null);
    setArrows([]);
    setBadge(null);
    setPreviewMode(false);
    setPracticeMode(false);
    setPracticeSolved(false);
    setPracticeFeedback(null);
    setAttemptError(null);
    setBoardDetached(false);
    setViewedPly(null);
    setActiveLine(null);
    setActiveIndex(-1);
  };

  const previewGameMove = () => {
    if (!current || !severityMeta) return;
    const applied = applyUciToFen(current.fenBefore, current.playedMove.uci);
    setBoardFen(applied.fen);
    setLastMove({ from: current.playedMove.from, to: current.playedMove.to });
    setArrows([{ from: current.playedMove.from, to: current.playedMove.to, kind: 'game_mistake' }]);
    setBadge({
      square: current.playedMove.to,
      glyph: severityMeta.glyph,
      bgColor: severityMeta.squareBg,
    });
    setPreviewMode(true);
    setBoardDetached(true);
    setPracticeMode(false);
    setActiveLine(null);
    setActiveIndex(-1);
    setViewedPly(current.ply);
    if (applied.san?.includes('x')) soundEngine.playCapture();
    else soundEngine.playMove();
  };

  const stepPv = (kind: 'best' | 'refutation', index: number) => {
    if (!current || !attemptResponse?.solution) return;
    const solution = attemptResponse.solution;
    const startFen =
      kind === 'best'
        ? current.fenBefore
        : applyUciToFen(current.fenBefore, current.playedMove.uci).fen;
    const moves = kind === 'best' ? solution.bestPvSan : solution.playedRefutationPvSan;
    const replay = replaySanLine(startFen, moves, index);

    setBoardFen(replay.fen);
    setLastMove(replay.lastMove);
    setArrows(
      replay.lastMove
        ? [{ from: replay.lastMove.from, to: replay.lastMove.to, kind: kind === 'best' ? 'best' : 'refutation' }]
        : []
    );
    setBadge(null);
    setActiveLine(kind);
    setActiveIndex(index);
    setBoardDetached(true);
    setPreviewMode(false);
    setPracticeMode(false);
    setPracticeSolved(false);
    setPracticeFeedback(null);
    soundEngine.playMove();
  };

  const startPractice = () => {
    if (!current || !attemptResponse?.solution) return;
    setPracticeMode(true);
    setPracticeSolved(false);
    setPracticeFeedback(`Now play ${attemptResponse.solution.bestMove.san} yourself on the board.`);
    setBoardFen(current.fenBefore);
    setLastMove(current.precedingMove ? { from: current.precedingMove.from, to: current.precedingMove.to } : null);
    setArrows([]);
    setBadge(null);
    setBoardDetached(false);
    setPreviewMode(false);
    setViewedPly(null);
    setActiveLine(null);
    setActiveIndex(-1);
  };

  const handlePracticeMove = (uci: string) => {
    if (!current || !attemptResponse?.solution || practiceSolved) return;
    const solution = attemptResponse.solution;
    const applied = applyUciToFen(current.fenBefore, uci);

    if (uci === solution.bestMove.uci) {
      setBoardFen(applied.fen);
      setLastMove(applied.lastMove);
      setArrows([{ from: solution.bestMove.from, to: solution.bestMove.to, kind: 'best' }]);
      setBadge({ square: solution.bestMove.to, glyph: '★', bgColor: '#4cc9f0' });
      setPracticeSolved(true);
      setPracticeFeedback(`Excellent — ${solution.bestMove.san} is now in your hands.`);
      soundEngine.playSuccess();
    } else {
      setBoardFen(current.fenBefore);
      setLastMove(null);
      setArrows([{ from: uci.slice(0, 2), to: uci.slice(2, 4), kind: 'attempt' }]);
      setBadge({ square: uci.slice(2, 4), glyph: '×', bgColor: '#ff8a78' });
      setPracticeFeedback('Not the revealed move yet. Reset your eyes and try again.');
      soundEngine.playMiss();
    }
  };

  const handleAttempt = async (uci: string) => {
    if (!current || attemptLockRef.current || hasSolution || solved || boardDetached || attempting) return;
    const submittedChallenge = challengeKey;
    attemptLockRef.current = true;
    setAttempting(true);
    setAttemptError(null);
    setPracticeFeedback(null);
    // Clear the previous candidate/refutation overlay before grading a new idea.
    setArrows([]);
    setBadge(null);
    setActiveLine(null);
    setActiveIndex(-1);
    setViewedPly(null);

    try {
      const response = await api.attemptMistake(current.id, {
        moveUci: uci,
        attemptNumber,
        maxAttempts,
        isPracticeRetry: isBlindRetest,
      });

      if (activeChallengeKey.current !== submittedChallenge) {
        if (response.outcome !== 'retry' && response.outcome !== 'same_as_game') onRefreshOverview();
        return;
      }
      setAttemptResponse(response);
      setMasteryOverrides((prev) => ({ ...prev, [current.id]: response.mastery }));

      const candidateFen = applyUciToFen(current.fenBefore, response.candidateMove.uci).fen;

      if (response.outcome === 'same_as_game') {
        setAttemptNumber((prev) => prev); // does not consume a try
        setBoardFen(current.fenBefore);
        setLastMove(current.precedingMove ? { from: current.precedingMove.from, to: current.precedingMove.to } : null);
        setArrows([{ from: response.candidateMove.from, to: response.candidateMove.to, kind: 'game_mistake' }]);
        setBadge(
          severityMeta
            ? { square: response.candidateMove.to, glyph: severityMeta.glyph, bgColor: severityMeta.squareBg }
            : null
        );
        setBoardDetached(false);
        setViewedPly(null);
        soundEngine.playMove();
      } else if (response.outcome === 'retry') {
        setAttemptNumber((prev) => Math.min(maxAttempts, prev + 1));
        setBoardFen(current.fenBefore);
        setLastMove(current.precedingMove ? { from: current.precedingMove.from, to: current.precedingMove.to } : null);
        setArrows([{ from: response.candidateMove.from, to: response.candidateMove.to, kind: 'attempt' }]);
        setBadge({ square: response.candidateMove.to, glyph: '×', bgColor: '#ff8a78' });
        setBoardDetached(false);
        setViewedPly(null);
        soundEngine.playMiss();
      } else {
        // A better move was found OR the final attempt failed. Only a final failed attempt unlocks the solution.
        setResolvedIds((prev) => new Set(prev).add(current.id));
        if (isBlindRetest && response.outcome === 'great') {
          setRedrillSolvedIds((prev) => new Set(prev).add(current.id));
        }
        if (response.outcome === 'failed_revealed') {
          setMissedIds((prev) => new Set(prev).add(current.id));
          soundEngine.playMiss();
        } else {
          soundEngine.playSuccess();
        }
        onRefreshOverview();

        if (response.outcome === 'failed_revealed' && response.solution) {
          setBoardFen(current.fenBefore);
          setLastMove(current.precedingMove ? { from: current.precedingMove.from, to: current.precedingMove.to } : null);
          setArrows([
            { from: response.solution.bestMove.from, to: response.solution.bestMove.to, kind: 'best' },
            { from: current.playedMove.from, to: current.playedMove.to, kind: 'game_mistake' },
          ]);
          setBadge({ square: response.solution.bestMove.to, glyph: '★', bgColor: '#4cc9f0' });
          setBoardDetached(false);
        } else {
          setBoardFen(candidateFen);
          setLastMove({ from: response.candidateMove.from, to: response.candidateMove.to });
          setArrows([{ from: response.candidateMove.from, to: response.candidateMove.to, kind: 'best' }]);
          setBadge({ square: response.candidateMove.to, glyph: '★', bgColor: '#4cc9f0' });
          setBoardDetached(true);
        }
        setViewedPly(null);
        setActiveLine(null);
        setActiveIndex(-1);
      }
    } catch (err) {
      if (activeChallengeKey.current === submittedChallenge) {
        setAttemptError(err instanceof Error ? err.message : 'Could not evaluate that move.');
        soundEngine.playMiss();
      }
    } finally {
      if (activeChallengeKey.current === submittedChallenge) {
        attemptLockRef.current = false;
        setAttempting(false);
      }
    }
  };

  const handleBoardMove = (uci: string) => {
    if (practiceMode) handlePracticeMove(uci);
    else void handleAttempt(uci);
  };

  const jumpToMistake = (mistake: MistakeChallengePublic) => {
    const idx = mistakes.findIndex((m) => m.id === mistake.id);
    if (idx < 0) return;
    setPhase('game');
    setQueueIndex(idx);
    setRoundKey((k) => k + 1);
    setAttemptResponse(null);
    setPracticeMode(false);
    setPreviewMode(false);
    setBoardDetached(false);
    setArrows([]);
    setBadge(null);
    setViewedPly(null);
  };

  const selectPly = (ply: PlyAnalysisSummary) => {
    if (attemptLockRef.current) return;
    setBoardFen(ply.fenAfter);
    setLastMove({ from: ply.from, to: ply.to });
    const linkedMistake = mistakes.find((m) => m.id === ply.mistakeId);
    setArrows(
      linkedMistake
        ? [{ from: ply.from, to: ply.to, kind: 'game_mistake' }]
        : []
    );
    setBadge(
      linkedMistake
        ? {
            square: ply.to,
            glyph: severityBadgeMeta(linkedMistake.severity).glyph,
            bgColor: severityBadgeMeta(linkedMistake.severity).squareBg,
          }
        : null
    );
    setPreviewMode(false);
    setPracticeMode(false);
    setBoardDetached(true);
    setViewedPly(ply.ply);
    setActiveLine(null);
    setActiveIndex(-1);
    setPracticeFeedback(null);
    soundEngine.playMove();
  };

  const clearBoardForAdvance = () => {
    setAttemptResponse(null);
    setAttemptNumber(1);
    setHintOpen(false);
    setPreviewMode(false);
    setPracticeMode(false);
    setPracticeSolved(false);
    setPracticeFeedback(null);
    setAttemptError(null);
    setActiveLine(null);
    setActiveIndex(-1);
    setArrows([]);
    setBadge(null);
    setBoardDetached(true);
    setViewedPly(null);
  };

  const advance = () => {
    clearBoardForAdvance();
    if (phase === 'game') {
      const next = queueIndex + 1;
      if (next < mistakes.length) {
        setQueueIndex(next);
        setRoundKey((k) => k + 1);
      } else {
        setPhase('summary');
        setRoundKey((k) => k + 1);
      }
    } else if (phase === 'redrill') {
      const next = redrillIndex + 1;
      if (next < redrillQueue.length) {
        setRedrillIndex(next);
        setRoundKey((k) => k + 1);
      } else {
        setPhase('complete');
        setRoundKey((k) => k + 1);
        onRefreshOverview();
      }
    }
  };

  const startRedrill = () => {
    const due = mistakes.filter((m) => missedIds.has(m.id) || !resolvedIds.has(m.id));
    if (due.length === 0) {
      setPhase('complete');
      return;
    }
    clearBoardForAdvance();
    setRedrillQueue(due);
    setRedrillIndex(0);
    setRedrillSolvedIds(new Set());
    setPhase('redrill');
    setRoundKey((k) => k + 1);
  };

  const restartGameDrill = () => {
    clearBoardForAdvance();
    setMissedIds(new Set());
    setResolvedIds(new Set());
    setRedrillSolvedIds(new Set());
    setRedrillQueue([]);
    setRedrillIndex(0);
    setQueueIndex(0);
    setPhase('game');
    setRoundKey((k) => k + 1);
  };

  const isAnalyzing = !game.analyzed || analysisProgress !== null;
  if (isAnalyzing) {
    const percent = analysisProgress?.percent ?? 0;
    return (
      <div className="mx-auto max-w-6xl">
        <div className="mb-5 flex flex-wrap items-end justify-between gap-3">
          <div>
            <Eyebrow>Live engine scan</Eyebrow>
            <h1 className="mt-1 font-display text-3xl font-semibold text-[var(--ink)]">
              {game.summary.openingName}
            </h1>
            <p className="mt-1 text-sm text-[var(--ink-muted)]">
              {game.summary.white} vs {game.summary.black} · {formatGameDate(game.summary.date)} · {game.summary.moveCount} moves
            </p>
          </div>
          <button
            type="button"
            onClick={onOpenLibrary}
            className="rounded-lg border border-[var(--line)] bg-[var(--surface)]/70 px-3 py-2 text-xs font-semibold text-[var(--ink-soft)] transition hover:border-[var(--a)]/50"
          >
            Choose another game
          </button>
        </div>

        <div className="grid gap-6 rounded-3xl border border-[var(--line)] bg-[var(--surface)]/85 p-5 lg:grid-cols-[minmax(0,460px)_1fr] lg:p-8">
          <div className="relative mx-auto w-full max-w-[420px]">
            <ChessBoard fen={previewFen} orientation={game.summary.userColor} interactive={false} theme="walnut" />
            <div className="absolute inset-0 rounded-xl bg-gradient-to-t from-[var(--a)]/75 via-transparent to-transparent" />
            <div className="absolute bottom-4 left-4 right-4 rounded-xl border border-[var(--a)]/30 bg-[var(--surface)]/90 px-4 py-3 backdrop-blur">
              <p className="flex items-center gap-2 text-xs font-bold text-[var(--a)]">
                <Brain className="h-4 w-4" /> Stockfish 18 Lite NNUE
              </p>
              <p className="mt-1 font-mono-tabular text-[10px] text-[var(--ink-muted)]">
                2 persistent UCI workers · depth 10 sweep · depth 12 MultiPV mistake check
              </p>
            </div>
          </div>

          <div className="flex flex-col justify-center">
            <div className="mb-5 inline-flex w-fit items-center gap-2 rounded-full border border-[var(--a)]/25 bg-[var(--a-soft)] px-3 py-1.5 text-[10px] font-bold uppercase tracking-[0.16em] text-[var(--a)]">
              {analysisProgress ? <Spinner className="h-3 w-3" /> : <Sparkles className="h-3.5 w-3.5" />}
              {analysisProgress ? 'Engine is thinking' : 'Ready to analyze'}
            </div>
            <h2 className="font-display text-3xl font-semibold leading-tight text-[var(--ink)] sm:text-4xl">
              Finding every move worth learning from.
            </h2>
            <p className="mt-3 max-w-lg text-sm leading-relaxed text-[var(--ink-secondary)]">
              Stockfish evaluates every position, verifies candidate mistakes with MultiPV, then builds blind challenges.
              Best moves are kept server-side and never sent before you fail.
            </p>

            <div className="mt-7 rounded-2xl border border-[var(--line)] bg-[var(--surface)]/70 p-4">
              <div className="mb-2 flex items-center justify-between text-xs">
                <span className="font-semibold text-[var(--ink-soft)]">
                  {analysisProgress?.stage ?? 'Scanning game moves with Stockfish 18 NNUE'}
                </span>
                <span className="font-mono-tabular font-bold text-[var(--a)]">{percent}%</span>
              </div>
              <ProgressBar value={percent} tone="bronze" />
              <p className="mt-2 font-mono-tabular text-[10px] text-[var(--ink-muted)]">
                {analysisProgress
                  ? `${analysisProgress.current} / ${analysisProgress.total} positions`
                  : 'A typical archive game takes about one second.'}
              </p>
            </div>

            {!analysisProgress && (
              <button
                type="button"
                onClick={onAnalyze}
                className="mt-6 inline-flex w-fit items-center gap-2 rounded-xl bg-[var(--a)] px-5 py-3 text-sm font-bold text-[#0a0714] transition hover:bg-[var(--a-hover)]"
              >
                Analyze with Stockfish 18 <ArrowRight className="h-4 w-4" />
              </button>
            )}
          </div>
        </div>
      </div>
    );
  }

  if (mistakes.length === 0) {
    return (
      <div className="mx-auto max-w-4xl">
        <EmptyState
          icon={<Trophy className="h-6 w-6" />}
          title="Stockfish found no costly mistakes here."
          detail={`This game scored ${game.userAccuracy?.toFixed(1) ?? '—'}% accuracy for you. Choose another game from the archive or paste a fresh PGN to keep drilling.`}
          action={
            <div className="flex flex-wrap justify-center gap-2">
              <button
                type="button"
                onClick={onOpenLibrary}
                className="rounded-lg bg-[var(--a)] px-4 py-2.5 text-xs font-bold text-[#0a0714]"
              >
                Browse archive
              </button>
              <button
                type="button"
                onClick={onOpenVault}
                className="rounded-lg border border-[var(--line)] px-4 py-2.5 text-xs font-semibold text-[var(--ink-soft)]"
              >
                Open Mistake Vault
              </button>
            </div>
          }
        />
      </div>
    );
  }

  const bottomColor = orientation;
  const topColor: PlayerColor = bottomColor === 'w' ? 'b' : 'w';
  const bottomIsUser = bottomColor === game.summary.userColor;
  const userColor = game.summary.userColor;
  const opponentColor: PlayerColor = userColor === 'w' ? 'b' : 'w';

  const infoForColor = (color: PlayerColor) => ({
    name: color === 'w' ? game.summary.white : game.summary.black,
    elo: color === 'w' ? game.summary.whiteElo : game.summary.blackElo,
    isUser: color === userColor,
    clock: clocks[color] ? formatClock(clocks[color]!) : null,
    captured: color === 'w' ? (captured?.white ?? []) : (captured?.black ?? []),
    capturedPieceColor: color === 'w' ? ('b' as PlayerColor) : ('w' as PlayerColor),
    materialDiff: color === 'w' ? material.whiteDiff : -material.whiteDiff,
    active: turnColor === color,
  });

  const topInfo = infoForColor(topColor);
  const bottomInfo = infoForColor(bottomColor);
  const boardInteractive =
    Boolean(current) &&
    !attempting &&
    !boardDetached &&
    (practiceMode ? !practiceSolved : !hasSolution && !solved);

  return (
    <div className="mx-auto max-w-[1280px] view-shell">
      <header className="premium-card relative mb-5 flex flex-wrap items-end justify-between gap-4 overflow-hidden rounded-2xl border border-[var(--line)] p-5 animate-fade-up">
        <div className="absolute inset-x-0 top-0 h-[3px] bg-gradient-to-r from-[var(--a-deep)] via-[var(--a2)] to-[var(--a-deep)]" />
        <div className="min-w-0">
          <div className="flex items-center gap-2">
            <span className="h-px w-5 bg-[var(--a)]" />
            <Eyebrow>
            {phase === 'redrill'
              ? 'Blind re-drill · no peeking'
              : phase === 'summary'
                ? 'Game round complete'
                : phase === 'complete'
                  ? 'Learning session complete'
                  : 'Coach session'}
            </Eyebrow>
          </div>
          <h1 className="mt-1 truncate font-display text-2xl font-semibold text-[var(--ink)] sm:text-3xl">
            {game.summary.openingName}
          </h1>
          <p className="mt-1 flex flex-wrap items-center gap-x-2 gap-y-1 text-xs text-[var(--ink-muted)]">
            <span>{game.summary.white} vs {game.summary.black}</span>
            <span className="text-[var(--ink-dim)]">·</span>
            <span>{formatGameDate(game.summary.date)}</span>
            <span className="text-[var(--ink-dim)]">·</span>
            <span>{game.summary.result}</span>
            <span className="text-[var(--ink-dim)]">·</span>
            <span className="font-mono-tabular text-[var(--a)]">
              {game.userAccuracy?.toFixed(1) ?? '—'}% accuracy
            </span>
          </p>
        </div>
        <div className="flex flex-wrap items-center gap-2">
          <Pill className="border-[var(--cool)]/25 bg-[var(--cool-bg)] text-[var(--cool)]">
            <Brain className="h-3 w-3" /> Stockfish 18 NNUE
          </Pill>
          <button
            type="button"
            onClick={onOpenLibrary}
            className="rounded-lg border border-[var(--line)] bg-[var(--surface)]/70 px-3 py-2 text-xs font-semibold text-[var(--ink-soft)] transition hover:border-[var(--a)]/50 hover:text-[var(--ink)]"
          >
            Choose game
          </button>
          <button
            type="button"
            onClick={onOpenVault}
            className="rounded-lg bg-[var(--a)] px-3 py-2 text-xs font-bold text-[#0a0714] transition hover:bg-[var(--a-hover)]"
          >
            Mistake Vault
          </button>
        </div>
      </header>

      <div className="grid items-start gap-6 lg:grid-cols-[minmax(0,1fr)_minmax(340px,430px)]">
        <div className="min-w-0 lg:sticky lg:top-24">
          <div className="mx-auto w-full max-w-[650px]">
            <div className="mb-3 flex flex-wrap items-center justify-between gap-2">
              <div className="flex items-center gap-2">
                <span className="text-[10px] font-semibold uppercase tracking-[0.16em] text-[var(--ink-secondary)]">
                  Board palette
                </span>
                <SegmentedControl<BoardThemeName>
                  value={boardTheme}
                  onChange={setBoardTheme}
                  size="sm"
                  options={[
                    { value: 'walnut', label: 'Violet' },
                    { value: 'slate', label: 'Midnight' },
                    { value: 'emerald', label: 'Linen' },
                  ]}
                />
              </div>
              <div className="flex items-center gap-1.5">
                <button
                  type="button"
                  onClick={() => setOrientation((prev) => (prev === 'w' ? 'b' : 'w'))}
                  className="inline-flex h-8 items-center gap-1 rounded-lg border border-[var(--line)] px-2.5 text-[11px] font-semibold text-[var(--ink-secondary)] transition hover:border-[var(--a)]/45 hover:text-[var(--ink)]"
                  title="Flip board"
                >
                  <RotateCcw className="h-3.5 w-3.5" /> Flip
                </button>
                <button
                  type="button"
                  onClick={resetBoardToPuzzle}
                  disabled={!current || attempting}
                  className="inline-flex h-8 items-center gap-1 rounded-lg border border-[var(--line)] px-2.5 text-[11px] font-semibold text-[var(--ink-secondary)] transition hover:border-[var(--a)]/45 hover:text-[var(--ink)] disabled:opacity-40"
                  title="Return to the blind puzzle position"
                >
                  <Target className="h-3.5 w-3.5" /> Puzzle
                </button>
              </div>
            </div>

            <div
              data-tour="coach-guide"
              className="mb-3 flex flex-wrap items-center gap-x-3 gap-y-1 rounded-xl border border-[var(--a)]/20 bg-[var(--a-soft)] px-3 py-2 animate-fade-up"
            >
              <span className="inline-flex items-center gap-1.5 text-[10px] font-bold uppercase tracking-[0.14em] text-[var(--a)]">
                <CircleHelp className="h-3.5 w-3.5" /> How to play
              </span>
              <span className="inline-flex items-center gap-1 text-[11px] text-[var(--ink-soft)]">
                <span className="font-mono-tabular text-[var(--a)]">1</span> Find a better move
              </span>
              <ChevronRight className="hidden h-3 w-3 text-[var(--ink-dim)] sm:block" />
              <span className="inline-flex items-center gap-1 text-[11px] text-[var(--ink-soft)]">
                <MousePointer2 className="h-3 w-3 text-[var(--a)]" /> Click or drag a piece
              </span>
              <ChevronRight className="hidden h-3 w-3 text-[var(--ink-dim)] sm:block" />
              <span className="inline-flex items-center gap-1 text-[11px] text-[var(--ink-soft)]">
                <EyeOff className="h-3 w-3 text-[var(--a)]" /> Answer after final miss only
              </span>
            </div>

            {current && <div className="coach-mobile-context lg:hidden">
              <span>Move {current.moveNumber} · {current.userColor === 'w' ? 'White' : 'Black'} to move</span>
              <strong>Find a better move than {current.playedMove.san}</strong>
              <small>Use the board below; your game move does not use a try.</small>
            </div>}
            <div className="flex gap-2.5">
              <div className="flex w-9 shrink-0 flex-col py-[52px]">
                <EvalBar
                  scoreCp={current?.evalBeforeUserCp ?? 0}
                  scoreMate={current?.evalBeforeUserMate ?? null}
                  userColor={userColor}
                  orientation={orientation}
                  label={hasSolution ? 'Best position' : 'Before your move'}
                  spoilerLocked={!hasSolution}
                  className="h-full"
                />
              </div>

              <div data-tour="coach-board" className="min-w-0 flex-1 space-y-1.5">
                <PlayerStrip {...topInfo} color={topColor} />
                <ChessBoard
                  fen={boardFen}
                  orientation={orientation}
                  interactive={boardInteractive}
                  allowedTurnColor={current?.userColor}
                  theme={boardTheme}
                  lastMove={lastMove}
                  arrows={arrows}
                  badge={badge}
                  nudgeSquare={null}
                  hintActive={hintOpen && !isBlindRetest && !hasSolution && !solved}
                  onMoveAttempt={handleBoardMove}
                />
                <PlayerStrip {...bottomInfo} color={bottomColor} />
              </div>
            </div>

            {(attemptResponse || attemptError) && <div className="coach-mobile-feedback lg:hidden" role="status">
              <strong>{attemptError ?? attemptResponse?.feedbackHeadline}</strong>
              <button type="button" onClick={() => feedbackRef.current?.scrollIntoView({ behavior: 'smooth', block: 'start' })}>View feedback ↓</button>
            </div>}
            <div className="mt-3 flex flex-wrap items-center justify-between gap-2 rounded-xl border border-[var(--line)] bg-[var(--surface)]/85 px-3 py-2">
              <p className="text-[11px] text-[var(--ink-secondary)]">
                {solved ? (
                  <span className="flex items-center gap-1.5 text-[var(--cool)]"><CheckCircle2 className="h-3 w-3" /> Solved · continue when ready</span>
                ) : boardDetached ? (
                  <span className="flex items-center gap-1.5 text-[var(--a)]">
                    <Eye className="h-3 w-3" /> Viewing a replay — return to puzzle to attempt a move
                  </span>
                ) : practiceMode ? (
                  <span className="flex items-center gap-1.5 text-[var(--cool-soft)]">
                    <Target className="h-3 w-3" /> Practice mode · play the revealed move yourself
                  </span>
                ) : hasSolution ? (
                  <span className="flex items-center gap-1.5 text-[var(--cool-soft)]">
                    <CheckCircle2 className="h-3 w-3" /> Line unlocked
                  </span>
                ) : (
                  <span className="flex items-center gap-1.5">
                    <EyeOff className="h-3 w-3 text-[var(--a)]" /> Best move hidden · click or drag a piece
                  </span>
                )}
              </p>
              {attempting && (
                <span className="flex items-center gap-1.5 text-[11px] text-[var(--a)]">
                  <Spinner className="h-3 w-3" /> Stockfish grading…
                </span>
              )}
            </div>
          </div>
        </div>

        <div ref={feedbackRef} className="min-w-0 scroll-mt-28 space-y-4">
          {current && severityMeta && currentMastery ? (
            <>
              <SurfaceCard className="p-4">
                <div className="flex items-start justify-between gap-3">
                  <div>
                    <Eyebrow>
                      {phase === 'redrill'
                        ? `Blind retest ${redrillIndex + 1} of ${redrillQueue.length}`
                        : `Mistake ${queueIndex + 1} of ${mistakes.length}`}
                    </Eyebrow>
                    <h2 className="mt-1 font-display text-2xl font-semibold leading-tight text-[var(--ink)]">
                      Move {current.moveNumber}: find a better move
                    </h2>
                  </div>
                  <MasteryPill status={currentMastery.status} />
                </div>

                <p className="mt-2 text-sm leading-relaxed text-[var(--ink-secondary)]">
                  You played <span className="font-mono-tabular font-bold text-[var(--warm-soft)]">{current.playedMove.san}</span> as {current.userColor === 'w' ? 'White' : 'Black'} in the game. Stockfish flagged it. The better move stays hidden until you fail.
                </p>

                <div className="mt-3 flex flex-wrap gap-1.5">
                  <Pill className={severityMeta.pillClass}>{severityMeta.glyph} {severityMeta.label}</Pill>
                  <Pill>{MOTIF_LABELS[current.motif]}</Pill>
                  <Pill>{PHASE_LABELS[current.phase]}</Pill>
                  <Pill className="border-[var(--warm)]/25 bg-[var(--warm-bg)] text-[var(--warm-soft)]">
                    <Flame className="h-3 w-3" /> −{Math.round(current.winProbLost * 100)}% win chance
                  </Pill>
                </div>

                {!hasSolution && !solved && (
                  <>
                    <div className="mt-4 grid grid-cols-2 gap-2">
                      <button
                        type="button"
                        onClick={previewGameMove}
                        disabled={isBlindRetest || attempting}
                        className="inline-flex items-center justify-center gap-1.5 rounded-lg border border-[var(--line)] bg-[var(--surface)] px-3 py-2.5 text-[11px] font-semibold text-[var(--ink-soft)] transition hover:border-[var(--warm)]/45 hover:text-[var(--ink)] disabled:cursor-not-allowed disabled:opacity-40"
                      >
                        <Eye className="h-3.5 w-3.5" /> Preview My Game Move
                      </button>
                      <button
                        type="button"
                        onClick={() => setHintOpen((v) => !v)}
                        disabled={isBlindRetest}
                        className="inline-flex items-center justify-center gap-1.5 rounded-lg border border-[var(--a)]/25 bg-[var(--a-soft)] px-3 py-2.5 text-[11px] font-semibold text-[var(--a)] transition hover:bg-[var(--a)]/15 disabled:cursor-not-allowed disabled:opacity-40"
                      >
                        <Lightbulb className="h-3.5 w-3.5" /> Scan Hint
                      </button>
                    </div>

                    {hintOpen && !isBlindRetest && (
                      <div className="mt-2 rounded-lg border border-[var(--a)]/20 bg-[var(--a-soft)] px-3 py-2.5 text-[11px] leading-relaxed text-[var(--a)]">
                        <span className="font-bold uppercase tracking-wider text-[var(--a)]">Theme-only hint · </span>
                        {safePieceHint(current.pieceNudge)}
                      </div>
                    )}

                    <div className="mt-4 flex items-center justify-between gap-3 border-t border-[var(--line)] pt-3">
                      <div>
                        <p className="text-[10px] font-semibold uppercase tracking-[0.14em] text-[var(--ink-secondary)]">
                          Tries before reveal
                        </p>
                        <p className="mt-0.5 text-[10px] text-[var(--ink-muted)]">
                          {attemptNumber > 1 || (attemptResponse && attemptResponse.outcome !== 'same_as_game')
                            ? 'Locked for this drill'
                            : isBlindRetest
                              ? 'Blind retest — no hints'
                              : '1 = strict · 2 = one extra guess'}
                        </p>
                      </div>
                      <SegmentedControl<'1' | '2'>
                        value={String(maxAttempts) as '1' | '2'}
                        onChange={(v) => {
                          const limit = v === '2' ? 2 : 1;
                          setMaxAttempts(limit);
                          setAttemptNumber((n) => Math.min(n, limit));
                        }}
                        size="sm"
                        disabled={attempting || attemptNumber > 1 || Boolean(attemptResponse && attemptResponse.outcome !== 'same_as_game')}
                        options={[
                          { value: '1', label: '1 try' },
                          { value: '2', label: '2 tries' },
                        ]}
                      />
                    </div>
                  </>
                )}
              </SurfaceCard>

              {attemptError && (
                <div className="rounded-xl border border-[var(--warm)]/30 bg-[var(--warm-bg)] px-3 py-2.5 text-[11px] text-[var(--warm-soft)]">
                  {attemptError}
                </div>
              )}

              {attemptResponse && !attemptResponse.solution && (
                <div
                  className={cx(
                    'rounded-2xl border p-4 animate-scale-in',
                    attemptResponse.outcome === 'same_as_game'
                      ? 'border-[var(--amber)]/25 bg-[var(--surface-soft)]/90'
                      : 'border-[var(--warm)]/25 bg-[var(--a-soft-2)]/90'
                  )}
                >
                  <div className="flex items-start gap-2.5">
                    <div className="mt-0.5 flex h-7 w-7 shrink-0 items-center justify-center rounded-lg bg-[var(--warm)]/10 text-[var(--warm-soft)]">
                      <EyeOff className="h-4 w-4" />
                    </div>
                    <div className="min-w-0">
                      <p className="text-sm font-bold text-[var(--ink)]">{attemptResponse.feedbackHeadline}</p>
                      <p className="mt-1 text-[11px] leading-relaxed text-[var(--ink-secondary)]">
                        {attemptResponse.feedbackDetail}
                      </p>
                      <div className="mt-2 flex flex-wrap gap-1.5">
                        <Pill className="border-[var(--line)] bg-[var(--surface)] text-[var(--ink-soft)]">
                          {attemptResponse.candidateMove.san} · {formatScore(attemptResponse.candidateEvalUserCp, attemptResponse.candidateEvalUserMate)}
                        </Pill>
                        <Pill className="border-[var(--cool)]/20 bg-[var(--cool)]/[0.05] text-[var(--cool)]">
                          {solved ? 'Solved · engine line stays hidden' : 'Answer still hidden'}
                        </Pill>
                      </div>
                    </div>
                  </div>
                </div>
              )}

              {solved && (
                <button type="button" onClick={advance} className="inline-flex w-full items-center justify-center gap-1.5 rounded-xl bg-[var(--a)] px-4 py-3 text-sm font-bold text-[#0a0714]">
                  Continue <ArrowRight className="h-4 w-4" />
                </button>
              )}

              {practiceMode && (
                <div className="rounded-2xl border border-[var(--cool)]/25 bg-[var(--cool-bg)]/90 p-3.5">
                  <p className="flex items-center gap-1.5 text-xs font-bold text-[var(--cool)]">
                    <Target className="h-3.5 w-3.5" /> Practice on board
                  </p>
                  <p className="mt-1 text-[11px] leading-relaxed text-[var(--cool-soft)]">
                    {practiceFeedback ?? 'Play the revealed move yourself.'}
                  </p>
                  {practiceSolved && (
                    <button
                      type="button"
                      onClick={advance}
                      className="mt-3 inline-flex w-full items-center justify-center gap-1.5 rounded-lg bg-[var(--cool)]/15 px-3 py-2 text-xs font-bold text-[var(--cool-soft)] transition hover:bg-[var(--cool)]/25"
                    >
                      Continue <ArrowRight className="h-3.5 w-3.5" />
                    </button>
                  )}
                </div>
              )}

              {attemptResponse?.solution && (
                <SolutionRevealCard
                  challenge={current}
                  response={attemptResponse}
                  activeLine={activeLine}
                  activeIndex={activeIndex}
                  onStepPv={stepPv}
                  onPracticeBestMove={startPractice}
                  onContinue={advance}
                  continueLabel={
                    phase === 'redrill'
                      ? redrillIndex + 1 < redrillQueue.length
                        ? 'Next Blind Retest'
                        : 'Finish Session'
                      : queueIndex + 1 < mistakes.length
                        ? 'Next Mistake'
                        : 'Finish Game Round'
                  }
                  compact
                />
              )}
            </>
          ) : phase === 'summary' ? (
            <SurfaceCard className="p-6 text-center">
              <div className="mx-auto flex h-12 w-12 items-center justify-center rounded-full border border-[var(--a)]/30 bg-[var(--a-soft)] text-[var(--a)]">
                <Trophy className="h-6 w-6" />
              </div>
              <Eyebrow className="mt-4">Active recall round</Eyebrow>
              <h2 className="mt-1 font-display text-2xl font-semibold text-[var(--ink)]">
                Game round complete
              </h2>
              <p className="mt-2 text-sm leading-relaxed text-[var(--ink-muted)]">
                You worked through {resolvedIds.size} of {mistakes.length} mistakes. Missed positions now enter a fresh blind re-drill so the answer has to be recalled, not remembered from the reveal.
              </p>
              <div className="my-5 flex justify-center">
                <ProgressRing
                  value={mistakes.length ? (resolvedIds.size / mistakes.length) * 100 : 100}
                  size={92}
                  label={`${resolvedIds.size}/${mistakes.length}`}
                  subLabel="resolved"
                  color="#8b7cff"
                />
              </div>
              <div className="grid grid-cols-2 gap-2 text-left">
                <div className="rounded-lg border border-[var(--warm)]/20 bg-[var(--warm)]/[0.06] p-3">
                  <p className="text-[10px] uppercase tracking-wider text-[var(--a-deep)]">Need review</p>
                  <p className="mt-1 font-display text-xl font-semibold text-[var(--warm-soft)]">{missedIds.size}</p>
                </div>
                <div className="rounded-lg border border-[var(--cool)]/20 bg-[var(--cool-bg)] p-3">
                  <p className="text-[10px] uppercase tracking-wider text-[var(--cool-soft)]">Clean recalls</p>
                  <p className="mt-1 font-display text-xl font-semibold text-[var(--cool)]">
                    {Math.max(0, resolvedIds.size - missedIds.size)}
                  </p>
                </div>
              </div>
              <button
                type="button"
                onClick={startRedrill}
                className="mt-5 inline-flex w-full items-center justify-center gap-2 rounded-xl bg-[var(--a)] px-4 py-3 text-sm font-bold text-[#0a0714] transition hover:bg-[var(--a-hover)]"
              >
                Start Blind Re-drill <ArrowRight className="h-4 w-4" />
              </button>
              <div className="mt-2 grid grid-cols-2 gap-2">
                <button
                  type="button"
                  onClick={onOpenVault}
                  className="rounded-lg border border-[var(--line)] px-3 py-2.5 text-xs font-semibold text-[var(--ink-soft)]"
                >
                  Mistake Vault
                </button>
                <button
                  type="button"
                  onClick={restartGameDrill}
                  className="rounded-lg border border-[var(--line)] px-3 py-2.5 text-xs font-semibold text-[var(--ink-soft)]"
                >
                  Restart game
                </button>
              </div>
            </SurfaceCard>
          ) : (
            <SurfaceCard className="p-6 text-center">
              <div className="mx-auto flex h-12 w-12 items-center justify-center rounded-full border border-[var(--cool)]/30 bg-[var(--cool-bg)] text-[var(--cool)]">
                <CheckCircle2 className="h-6 w-6" />
              </div>
              <Eyebrow className="mt-4">Spaced repetition updated</Eyebrow>
              <h2 className="mt-1 font-display text-2xl font-semibold text-[var(--ink)]">
                Session complete
              </h2>
              <p className="mt-2 text-sm leading-relaxed text-[var(--ink-muted)]">
                {redrillSolvedIds.size > 0
                  ? `${redrillSolvedIds.size} missed ${redrillSolvedIds.size === 1 ? 'position' : 'positions'} were recalled cleanly in the blind retest.`
                  : 'Every unresolved position is saved in your cross-game review queue.'}
              </p>
              <div className="mt-5 flex justify-center">
                <ProgressRing value={100} size={84} label="✓" subLabel="saved" color="#4cc9f0" />
              </div>
              <div className="mt-5 grid grid-cols-2 gap-2">
                <button
                  type="button"
                  onClick={onOpenVault}
                  className="rounded-lg bg-[var(--a)] px-3 py-2.5 text-xs font-bold text-[#0a0714]"
                >
                  Train all due
                </button>
                <button
                  type="button"
                  onClick={onOpenLibrary}
                  className="rounded-lg border border-[var(--line)] px-3 py-2.5 text-xs font-semibold text-[var(--ink-soft)]"
                >
                  Next game
                </button>
              </div>
              <button
                type="button"
                onClick={restartGameDrill}
                className="mt-2 w-full rounded-lg px-3 py-2 text-[11px] font-semibold text-[var(--ink-secondary)] transition hover:text-[var(--a)]"
              >
                Replay this game’s drills
              </button>
            </SurfaceCard>
          )}

          {!solved && (boardDetached || previewMode || activeLine || practiceMode) && current && (
            <button
              type="button"
              onClick={resetBoardToPuzzle}
              className="inline-flex w-full items-center justify-center gap-1.5 rounded-xl border border-[var(--a)]/25 bg-[var(--a-soft)] px-3 py-2.5 text-xs font-bold text-[var(--a)] transition hover:bg-[var(--a)]/15"
            >
              <RotateCcw className="h-3.5 w-3.5" /> Return to blind puzzle
            </button>
          )}

          <SurfaceCard className="p-3">
            <div className="mb-2 flex items-center justify-between gap-2">
              <Eyebrow>Stockfish evaluation</Eyebrow>
              <span className="text-[10px] text-[var(--ink-muted)]">White perspective · pins are spoiler-free</span>
            </div>
            <EvalGraph
              plies={game.plies}
              mistakes={mistakes}
              activePly={activePly}
              onSelectMistake={jumpToMistake}
              onSelectPly={selectPly}
            />
          </SurfaceCard>

          <MoveSheet
            plies={game.plies}
            activePly={activePly}
            onSelectPly={selectPly}
            open={moveSheetOpen}
            onToggle={() => setMoveSheetOpen((v) => !v)}
          />
        </div>
      </div>
    </div>
  );
};
