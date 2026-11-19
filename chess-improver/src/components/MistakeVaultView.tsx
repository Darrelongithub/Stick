import React, { useEffect, useMemo, useRef, useState } from 'react';
import {
  ArrowRight,
  BookOpen,
  Brain,
  CheckCircle2,
  Eye,
  EyeOff,
  Filter,
  Flame,
  Lightbulb,
  Play,
  RotateCcw,
  Search,
  Sparkles,
  Target,
  Trophy,
  X,
} from 'lucide-react';
import type {
  ArchiveOverviewResponse,
  AttemptMoveResponse,
  MistakeChallengePublic,
  PlayerColor,
} from '../../shared/types';
import { api } from '../lib/api';
import {
  applyUciToFen,
  cx,
  formatGameDate,
  formatScore,
  MOTIF_LABELS,
  PHASE_LABELS,
  replaySanLine,
  safePieceHint,
  severityBadgeMeta,
  shortOpening,
} from '../lib/chessFormat';
import { soundEngine } from '../lib/sound';
import { BoardArrow, BoardThemeName, ChessBoard, SquareBadge } from './ChessBoard';
import { EvalBar } from './EvalBar';
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

interface MistakeVaultViewProps {
  overview: ArchiveOverviewResponse | null;
  onRefreshOverview: () => void;
  onOpenGame: (gameId: string, mistakeId?: string) => void;
  onOpenLibrary?: () => void;
}

const STATUS_OPTIONS = [
  { value: 'due', label: 'Due now' },
  { value: 'all', label: 'All mistakes' },
  { value: 'needs_review', label: 'Needs review' },
  { value: 'learning', label: 'Learning' },
  { value: 'unseen', label: 'Unseen' },
  { value: 'mastered', label: 'Mastered' },
];

const SEVERITY_OPTIONS = [
  { value: 'all', label: 'All severities' },
  { value: 'blunder', label: 'Blunders' },
  { value: 'mistake', label: 'Mistakes' },
  { value: 'inaccuracy', label: 'Inaccuracies' },
];

const PHASE_OPTIONS = [
  { value: 'all', label: 'All phases' },
  { value: 'opening', label: 'Opening' },
  { value: 'middlegame', label: 'Middlegame' },
  { value: 'endgame', label: 'Endgame' },
];

function FilterSelect({
  label,
  value,
  options,
  onChange,
}: {
  label: string;
  value: string;
  options: Array<{ value: string; label: string }>;
  onChange: (value: string) => void;
}) {
  return (
    <label className="block">
      <span className="mb-1 block text-[9px] font-semibold uppercase tracking-[0.14em] text-[var(--ink-muted)]">
        {label}
      </span>
      <select
        value={value}
        onChange={(event) => onChange(event.target.value)}
        className="w-full rounded-lg border border-[var(--line)] bg-[var(--surface)] px-2.5 py-2 text-[11px] font-semibold text-[var(--ink-soft)] outline-none transition focus:border-[var(--a)]/50"
      >
        {options.map((option) => (
          <option key={option.value} value={option.value}>
            {option.label}
          </option>
        ))}
      </select>
    </label>
  );
}

function MiniPosition({ mistake }: { mistake: MistakeChallengePublic }) {
  const severity = severityBadgeMeta(mistake.severity);
  return (
    <div className="w-[92px] shrink-0">
      <ChessBoard
        fen={mistake.fenBefore}
        orientation={mistake.userColor}
        interactive={false}
        theme="slate"
        lastMove={mistake.precedingMove ? { from: mistake.precedingMove.from, to: mistake.precedingMove.to } : null}
        badge={{ square: mistake.playedMove.to, glyph: severity.glyph, bgColor: severity.squareBg }}
      />
    </div>
  );
}

function MistakeCard({
  mistake,
  onTrain,
  onOpenGame,
}: {
  mistake: MistakeChallengePublic;
  onTrain: () => void;
  onOpenGame: () => void;
}) {
  const severity = severityBadgeMeta(mistake.severity);
  return (
    <article className="group flex gap-3 rounded-2xl border border-[var(--line)] bg-[var(--surface)] p-3 animate-fade-up hover-lift hover:border-[var(--a)]/30 hover:bg-[var(--surface)]">
      <MiniPosition mistake={mistake} />
      <div className="min-w-0 flex-1">
        <div className="flex flex-wrap items-start justify-between gap-2">
          <div className="min-w-0">
            <p className="font-display text-base font-semibold text-[var(--ink)]">
              Move {mistake.moveNumber} · {mistake.playedMove.san}
            </p>
            <p className="mt-0.5 truncate text-[11px] text-[var(--ink-secondary)]">
              vs {mistake.gameOpponent} · {formatGameDate(mistake.gameDate)}
            </p>
          </div>
          <MasteryPill status={mistake.mastery.status} />
        </div>

        <p className="mt-1.5 truncate text-[11px] text-[var(--ink-secondary)]" title={mistake.openingName}>
          {shortOpening(mistake.openingName, 42)}
        </p>

        <div className="mt-2 flex flex-wrap gap-1.5">
          <Pill className={severity.pillClass}>{severity.glyph} {severity.label}</Pill>
          <Pill>{MOTIF_LABELS[mistake.motif]}</Pill>
          <Pill>{PHASE_LABELS[mistake.phase]}</Pill>
          <Pill className="border-[var(--warm)]/20 bg-[var(--warm)]/[0.06] text-[var(--warm-soft)]">
            <Flame className="h-3 w-3" /> −{Math.round(mistake.winProbLost * 100)}%
          </Pill>
        </div>

        <div className="mt-3 flex gap-2">
          <button
            type="button"
            onClick={onTrain}
            className="inline-flex flex-1 items-center justify-center gap-1.5 rounded-lg bg-[var(--a)] px-3 py-2 text-[11px] font-bold text-[#0a0714] transition hover:bg-[var(--a-hover)]"
          >
            <Target className="h-3.5 w-3.5" /> Train blind
          </button>
          <button
            type="button"
            onClick={onOpenGame}
            className="inline-flex items-center justify-center rounded-lg border border-[var(--line)] px-3 py-2 text-[11px] font-semibold text-[var(--ink-secondary)] transition hover:border-[var(--a)]/45 hover:text-[var(--ink)]"
            title="Open the full game"
          >
            <BookOpen className="h-3.5 w-3.5" />
          </button>
        </div>
      </div>
    </article>
  );
}

function VaultTrainerModal({
  challenge,
  index,
  total,
  onClose,
  onComplete,
  onOpenGame,
  onMasteryChanged,
}: {
  challenge: MistakeChallengePublic;
  index: number;
  total: number;
  onClose: () => void;
  onComplete: () => void;
  onOpenGame: () => void;
  onMasteryChanged: () => void;
}) {
  const severity = severityBadgeMeta(challenge.severity);
  const [maxAttempts, setMaxAttempts] = useState<1 | 2>(1);
  const [attemptNumber, setAttemptNumber] = useState(1);
  const [response, setResponse] = useState<AttemptMoveResponse | null>(null);
  const [attempting, setAttempting] = useState(false);
  const [attemptError, setAttemptError] = useState<string | null>(null);
  const [hintOpen, setHintOpen] = useState(false);
  const [previewMode, setPreviewMode] = useState(false);
  const [practiceMode, setPracticeMode] = useState(false);
  const [practiceSolved, setPracticeSolved] = useState(false);
  const [practiceFeedback, setPracticeFeedback] = useState<string | null>(null);
  const [activeLine, setActiveLine] = useState<PvLineKind>(null);
  const [activeIndex, setActiveIndex] = useState(-1);
  const [orientation, setOrientation] = useState<PlayerColor>(challenge.userColor);
  const [theme, setTheme] = useState<BoardThemeName>('walnut');
  const [boardFen, setBoardFen] = useState(challenge.fenBefore);
  const [lastMove, setLastMove] = useState<{ from: string; to: string } | null>(
    challenge.precedingMove ? { from: challenge.precedingMove.from, to: challenge.precedingMove.to } : null
  );
  const [arrows, setArrows] = useState<BoardArrow[]>([]);
  const [badge, setBadge] = useState<SquareBadge | null>(null);
  const [boardDetached, setBoardDetached] = useState(false);
  const attemptLockRef = useRef(false);
  const dialogRef = useRef<HTMLDivElement | null>(null);
  const closeRef = useRef(onClose);
  const attemptingRef = useRef(attempting);
  closeRef.current = onClose;
  attemptingRef.current = attempting;

  useEffect(() => {
    const previousFocus = document.activeElement instanceof HTMLElement ? document.activeElement : null;
    dialogRef.current?.querySelector<HTMLElement>('[aria-label="Close vault trainer"]')?.focus();
    return () => { if (previousFocus?.isConnected) previousFocus.focus(); };
  }, []);

  useEffect(() => {
    const previousOverflow = document.body.style.overflow;
    document.body.style.overflow = 'hidden';
    const onKeyDown = (event: KeyboardEvent) => {
      if (event.key === 'Escape' && !attemptingRef.current) closeRef.current();
      if (event.key === 'Tab' && dialogRef.current) {
        const focusable = [...dialogRef.current.querySelectorAll<HTMLElement>('button:not(:disabled):not([tabindex="-1"]), input:not(:disabled), select:not(:disabled), textarea:not(:disabled), a[href]')].filter(el => el.getClientRects().length > 0);
        if (!focusable.length) { event.preventDefault(); return; }
        const first = focusable[0], last = focusable[focusable.length - 1];
        if (event.shiftKey && (document.activeElement === first || !dialogRef.current.contains(document.activeElement))) { event.preventDefault(); last.focus(); }
        else if (!event.shiftKey && document.activeElement === last) { event.preventDefault(); first.focus(); }
      }
    };
    window.addEventListener('keydown', onKeyDown);
    return () => {
      document.body.style.overflow = previousOverflow;
      window.removeEventListener('keydown', onKeyDown);
    };
  }, []);

  const hasSolution = Boolean(response?.solution);
  const solved = response?.outcome === 'great';
  const boardInteractive =
    !attempting &&
    !boardDetached &&
    (practiceMode ? !practiceSolved : !hasSolution && !solved);

  const resetBoard = () => {
    setBoardFen(challenge.fenBefore);
    setLastMove(
      challenge.precedingMove ? { from: challenge.precedingMove.from, to: challenge.precedingMove.to } : null
    );
    setArrows([]);
    setBadge(null);
    setPreviewMode(false);
    setPracticeMode(false);
    setPracticeSolved(false);
    setPracticeFeedback(null);
    setActiveLine(null);
    setActiveIndex(-1);
    setBoardDetached(false);
  };

  const previewGameMove = () => {
    const applied = applyUciToFen(challenge.fenBefore, challenge.playedMove.uci);
    setBoardFen(applied.fen);
    setLastMove({ from: challenge.playedMove.from, to: challenge.playedMove.to });
    setArrows([{ from: challenge.playedMove.from, to: challenge.playedMove.to, kind: 'game_mistake' }]);
    setBadge({ square: challenge.playedMove.to, glyph: severity.glyph, bgColor: severity.squareBg });
    setPreviewMode(true);
    setPracticeMode(false);
    setBoardDetached(true);
    setActiveLine(null);
    setActiveIndex(-1);
    if (applied.san?.includes('x')) soundEngine.playCapture();
    else soundEngine.playMove();
  };

  const stepPv = (kind: 'best' | 'refutation', indexToPlay: number) => {
    if (!response?.solution) return;
    const solution = response.solution;
    const startFen =
      kind === 'best'
        ? challenge.fenBefore
        : applyUciToFen(challenge.fenBefore, challenge.playedMove.uci).fen;
    const moves = kind === 'best' ? solution.bestPvSan : solution.playedRefutationPvSan;
    const replay = replaySanLine(startFen, moves, indexToPlay);
    setBoardFen(replay.fen);
    setLastMove(replay.lastMove);
    setArrows(
      replay.lastMove
        ? [{ from: replay.lastMove.from, to: replay.lastMove.to, kind: kind === 'best' ? 'best' : 'refutation' }]
        : []
    );
    setBadge(null);
    setActiveLine(kind);
    setActiveIndex(indexToPlay);
    setBoardDetached(true);
    setPreviewMode(false);
    setPracticeMode(false);
    soundEngine.playMove();
  };

  const startPractice = () => {
    if (!response?.solution) return;
    setPracticeMode(true);
    setPracticeSolved(false);
    setPracticeFeedback(`Play ${response.solution.bestMove.san} on the board.`);
    setBoardFen(challenge.fenBefore);
    setLastMove(
      challenge.precedingMove ? { from: challenge.precedingMove.from, to: challenge.precedingMove.to } : null
    );
    setArrows([]);
    setBadge(null);
    setBoardDetached(false);
    setPreviewMode(false);
    setActiveLine(null);
    setActiveIndex(-1);
  };

  const handlePracticeMove = (uci: string) => {
    if (!response?.solution || practiceSolved) return;
    const solution = response.solution;
    const applied = applyUciToFen(challenge.fenBefore, uci);
    if (uci === solution.bestMove.uci) {
      setBoardFen(applied.fen);
      setLastMove(applied.lastMove);
      setArrows([{ from: solution.bestMove.from, to: solution.bestMove.to, kind: 'best' }]);
      setBadge({ square: solution.bestMove.to, glyph: '★', bgColor: '#4cc9f0' });
      setPracticeSolved(true);
      setPracticeFeedback(`Nice — ${solution.bestMove.san} recalled cleanly.`);
      soundEngine.playSuccess();
    } else {
      setBoardFen(challenge.fenBefore);
      setLastMove(null);
      setArrows([{ from: uci.slice(0, 2), to: uci.slice(2, 4), kind: 'attempt' }]);
      setBadge({ square: uci.slice(2, 4), glyph: '×', bgColor: '#ff8a78' });
      setPracticeFeedback('Not that move. Try the revealed best move again.');
      soundEngine.playMiss();
    }
  };

  const handleAttempt = async (uci: string) => {
    if (attemptLockRef.current || hasSolution || solved || boardDetached || attempting) return;
    attemptLockRef.current = true;
    setAttempting(true);
    setAttemptError(null);
    setPracticeFeedback(null);
    setArrows([]);
    setBadge(null);
    setActiveLine(null);
    setActiveIndex(-1);

    try {
      const result = await api.attemptMistake(challenge.id, {
        moveUci: uci,
        attemptNumber,
        maxAttempts,
        isPracticeRetry: true,
      });
      setResponse(result);
      const candidateFen = applyUciToFen(challenge.fenBefore, result.candidateMove.uci).fen;

      if (result.outcome === 'same_as_game') {
        setBoardFen(challenge.fenBefore);
        setLastMove(
          challenge.precedingMove ? { from: challenge.precedingMove.from, to: challenge.precedingMove.to } : null
        );
        setArrows([{ from: result.candidateMove.from, to: result.candidateMove.to, kind: 'game_mistake' }]);
        setBadge({ square: result.candidateMove.to, glyph: severity.glyph, bgColor: severity.squareBg });
        setBoardDetached(false);
        soundEngine.playMove();
      } else if (result.outcome === 'retry') {
        setAttemptNumber((prev) => Math.min(maxAttempts, prev + 1));
        setBoardFen(challenge.fenBefore);
        setLastMove(
          challenge.precedingMove ? { from: challenge.precedingMove.from, to: challenge.precedingMove.to } : null
        );
        setArrows([{ from: result.candidateMove.from, to: result.candidateMove.to, kind: 'attempt' }]);
        setBadge({ square: result.candidateMove.to, glyph: '×', bgColor: '#ff8a78' });
        setBoardDetached(false);
        soundEngine.playMiss();
      } else {
        if (result.outcome === 'failed_revealed') soundEngine.playMiss();
        else soundEngine.playSuccess();
        onMasteryChanged();

        if (result.outcome === 'failed_revealed' && result.solution) {
          setBoardFen(challenge.fenBefore);
          setLastMove(
            challenge.precedingMove ? { from: challenge.precedingMove.from, to: challenge.precedingMove.to } : null
          );
          setArrows([
            { from: result.solution.bestMove.from, to: result.solution.bestMove.to, kind: 'best' },
            { from: challenge.playedMove.from, to: challenge.playedMove.to, kind: 'game_mistake' },
          ]);
          setBadge({ square: result.solution.bestMove.to, glyph: '★', bgColor: '#4cc9f0' });
          setBoardDetached(false);
        } else {
          setBoardFen(candidateFen);
          setLastMove({ from: result.candidateMove.from, to: result.candidateMove.to });
          setArrows([{ from: result.candidateMove.from, to: result.candidateMove.to, kind: 'best' }]);
          setBadge({ square: result.candidateMove.to, glyph: '★', bgColor: '#4cc9f0' });
          setBoardDetached(true);
        }
        setActiveLine(null);
        setActiveIndex(-1);
      }
    } catch (err) {
      setAttemptError(err instanceof Error ? err.message : 'Could not grade that move.');
      soundEngine.playMiss();
    } finally {
      attemptLockRef.current = false;
      setAttempting(false);
    }
  };

  const handleBoardMove = (uci: string) => {
    if (practiceMode) handlePracticeMove(uci);
    else void handleAttempt(uci);
  };

  return (
    <div className="fixed inset-0 z-[90] flex items-center justify-center bg-[var(--surface-deep)]/55 p-2 backdrop-blur-md sm:p-5 animate-fade-in">
      <div ref={dialogRef} role="dialog" aria-modal="true" aria-label="Vault blind drill" className="premium-card relative flex max-h-[94vh] w-full max-w-6xl flex-col overflow-hidden rounded-3xl border border-[var(--line)] animate-scale-in">
        <div className="absolute inset-x-0 top-0 h-[3px] bg-gradient-to-r from-[var(--a-deep)] via-[var(--a2)] to-[var(--a-deep)]" />
        <header className="flex items-center justify-between gap-3 border-b border-[var(--line)] bg-[var(--surface)]/85 px-4 py-3 sm:px-6">
          <div className="min-w-0">
            <Eyebrow>Spaced repetition · blind drill {index + 1} of {total}</Eyebrow>
            <p className="mt-0.5 truncate font-display text-lg font-semibold text-[var(--ink)]">
              Move {challenge.moveNumber} vs {challenge.gameOpponent}
            </p>
          </div>
          <div className="flex items-center gap-2">
            <MasteryPill status={response?.mastery.status ?? challenge.mastery.status} />
            <button
              type="button"
              onClick={onClose}
              disabled={attempting}
              className="flex h-8 w-8 items-center justify-center rounded-full border border-[var(--line)] text-[var(--ink-secondary)] transition hover:border-[var(--warm)]/50 hover:text-[var(--warm-soft)]"
              aria-label="Close vault trainer"
            >
              <X className="h-4 w-4" />
            </button>
          </div>
        </header>

        <div className="grid min-h-0 flex-1 gap-5 overflow-y-auto p-4 sm:p-6 lg:grid-cols-[minmax(0,1fr)_400px]">
          <div className="mx-auto w-full max-w-[570px]">
            <div className="mb-3 flex flex-wrap items-center justify-between gap-2">
              <SegmentedControl<BoardThemeName>
                value={theme}
                onChange={setTheme}
                size="sm"
                options={[
                  { value: 'walnut', label: 'Violet' },
                  { value: 'slate', label: 'Midnight' },
                  { value: 'emerald', label: 'Linen' },
                ]}
              />
              <div className="flex gap-1.5">
                <button
                  type="button"
                  onClick={() => setOrientation((prev) => (prev === 'w' ? 'b' : 'w'))}
                  className="inline-flex h-8 items-center gap-1 rounded-lg border border-[var(--line)] px-2.5 text-[11px] font-semibold text-[var(--ink-secondary)] hover:border-[var(--a)]/45"
                >
                  <RotateCcw className="h-3.5 w-3.5" /> Flip
                </button>
                <button
                  type="button"
                  onClick={resetBoard}
                  disabled={attempting}
                  className="inline-flex h-8 items-center gap-1 rounded-lg border border-[var(--line)] px-2.5 text-[11px] font-semibold text-[var(--ink-secondary)] hover:border-[var(--a)]/45"
                >
                  <Target className="h-3.5 w-3.5" /> Puzzle
                </button>
              </div>
            </div>

            <div className="flex gap-2.5">
              <div className="flex w-9 shrink-0 flex-col py-11">
                <EvalBar
                  scoreCp={challenge.evalBeforeUserCp}
                  scoreMate={challenge.evalBeforeUserMate}
                  userColor={challenge.userColor}
                  orientation={orientation}
                  label="Pre-move eval"
                  spoilerLocked={!hasSolution}
                  className="h-full"
                />
              </div>
              <div className="min-w-0 flex-1">
                <div className="mb-1.5 flex items-center justify-between rounded-lg border border-[var(--line)] bg-[var(--surface)]/85 px-2.5 py-1.5">
                  <span className="truncate text-[11px] font-semibold text-[var(--ink-soft)]">
                    {orientation === challenge.userColor ? 'Opponent' : 'You'} · {challenge.gameDate}
                  </span>
                  <span className="text-[10px] text-[var(--ink-muted)]">{challenge.timeClass}</span>
                </div>
                <ChessBoard
                  fen={boardFen}
                  orientation={orientation}
                  interactive={boardInteractive}
                  allowedTurnColor={challenge.userColor}
                  theme={theme}
                  lastMove={lastMove}
                  arrows={arrows}
                  badge={badge}
                  nudgeSquare={null}
                  hintActive={hintOpen && !hasSolution && !solved}
                  onMoveAttempt={handleBoardMove}
                />
                <div className="mt-1.5 flex items-center justify-between rounded-lg border border-[var(--line)] bg-[var(--surface)]/85 px-2.5 py-1.5">
                  <span className="text-[11px] font-semibold text-[var(--ink-soft)]">
                    {boardFen.split(' ')[1] === challenge.userColor ? 'Your turn' : 'Opponent to move'}
                  </span>
                  <span className="flex items-center gap-1 text-[10px] text-[var(--a)]">
                    {hasSolution ? <CheckCircle2 className="h-3 w-3" /> : <EyeOff className="h-3 w-3" />}
                    {hasSolution ? 'Line unlocked' : 'Answer hidden'}
                  </span>
                </div>
              </div>
            </div>

            <div className="mt-3 rounded-xl border border-[var(--line)] bg-[var(--surface)] px-3 py-2 text-[11px] text-[var(--ink-secondary)]">
              {solved
                ? 'Solved. Continue when you are ready.'
                : boardDetached
                ? 'Viewing a replay. Return to puzzle to attempt another move.'
                : practiceMode
                  ? 'Practice mode: reproduce the revealed move by hand.'
                  : hasSolution
                    ? 'The line is unlocked. Step through it, then practice it on the board.'
                    : 'Click or drag a piece. The best move is revealed only after you fail.'}
            </div>
          </div>

          <aside className="min-w-0 space-y-3">
            <SurfaceCard className="p-4">
              <div className="flex items-start justify-between gap-3">
                <div>
                  <Eyebrow>Blind challenge</Eyebrow>
                  <h2 className="mt-1 font-display text-xl font-semibold text-[var(--ink)]">
                    Find a better move
                  </h2>
                </div>
                <Pill className={severity.pillClass}>{severity.glyph} {severity.label}</Pill>
              </div>
              <p className="mt-2 text-[12px] leading-relaxed text-[var(--ink-secondary)]">
                You played <span className="font-mono-tabular font-bold text-[var(--warm-soft)]">{challenge.playedMove.san}</span>. Stockfish marked it as a {challenge.severity}. {hasSolution ? 'The engine line is unlocked after your final failed attempt.' : 'The engine line remains hidden.'}
              </p>
              <div className="mt-2 flex flex-wrap gap-1.5">
                <Pill>{MOTIF_LABELS[challenge.motif]}</Pill>
                <Pill>{PHASE_LABELS[challenge.phase]}</Pill>
                <Pill className="border-[var(--warm)]/20 bg-[var(--warm)]/[0.06] text-[var(--warm-soft)]">
                  −{Math.round(challenge.winProbLost * 100)}% win chance
                </Pill>
              </div>

              {!hasSolution && !solved && (
                <>
                  <div className="mt-3 grid grid-cols-2 gap-2">
                    <button
                      type="button"
                      onClick={previewGameMove}
                      disabled={attempting}
                      className="inline-flex items-center justify-center gap-1.5 rounded-lg border border-[var(--line)] px-2.5 py-2 text-[11px] font-semibold text-[var(--ink-soft)] hover:border-[var(--warm)]/45"
                    >
                      <Eye className="h-3.5 w-3.5" /> Game move
                    </button>
                    <button
                      type="button"
                      onClick={() => setHintOpen((v) => !v)}
                      className="inline-flex items-center justify-center gap-1.5 rounded-lg border border-[var(--a)]/25 bg-[var(--a-soft)] px-2.5 py-2 text-[11px] font-semibold text-[var(--a)]"
                    >
                      <Lightbulb className="h-3.5 w-3.5" /> Scan hint
                    </button>
                  </div>
                  {hintOpen && (
                    <p className="mt-2 rounded-lg border border-[var(--a)]/20 bg-[var(--a-soft)] px-3 py-2 text-[11px] leading-relaxed text-[var(--a)]">
                      <span className="font-bold uppercase tracking-wider text-[var(--a)]">Theme only · </span>
                      {safePieceHint(challenge.pieceNudge)}
                    </p>
                  )}
                  <div className="mt-3 flex items-center justify-between border-t border-[var(--line)] pt-3">
                    <span className="text-[10px] font-semibold uppercase tracking-[0.14em] text-[var(--ink-secondary)]">
                      {attemptNumber > 1 || (response && response.outcome !== 'same_as_game') ? 'Tries locked' : 'Tries before reveal'}
                    </span>
                    <SegmentedControl<'1' | '2'>
                      value={String(maxAttempts) as '1' | '2'}
                      onChange={(v) => {
                        const limit = v === '2' ? 2 : 1;
                        setMaxAttempts(limit);
                        setAttemptNumber((n) => Math.min(n, limit));
                      }}
                      size="sm"
                      disabled={attempting || attemptNumber > 1 || Boolean(response && response.outcome !== 'same_as_game')}
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
              <div className="rounded-xl border border-[var(--warm)]/30 bg-[var(--warm-bg)] px-3 py-2 text-[11px] text-[var(--warm-soft)]">
                {attemptError}
              </div>
            )}

            {response && !response.solution && (
              <div className="rounded-2xl border border-[var(--warm)]/25 bg-[var(--a-soft-2)]/90 p-3.5">
                <p className="text-xs font-bold text-[var(--ink)]">{response.feedbackHeadline}</p>
                <p className="mt-1 text-[11px] leading-relaxed text-[var(--ink-secondary)]">{response.feedbackDetail}</p>
                <div className="mt-2 flex flex-wrap gap-1.5">
                  <Pill>{response.candidateMove.san} · {formatScore(response.candidateEvalUserCp, response.candidateEvalUserMate)}</Pill>
                  <Pill className="border-[var(--cool)]/20 bg-[var(--cool)]/[0.05] text-[var(--cool)]">{solved ? 'Solved · engine line stays hidden' : 'Answer still hidden'}</Pill>
                </div>
              </div>
            )}

            {solved && (
              <button type="button" onClick={onComplete} className="inline-flex w-full items-center justify-center gap-1.5 rounded-xl bg-[var(--a)] px-4 py-3 text-sm font-bold text-[#0a0714]">
                Continue <ArrowRight className="h-4 w-4" />
              </button>
            )}

            {practiceMode && (
              <div className="rounded-2xl border border-[var(--cool)]/25 bg-[var(--cool-bg)]/90 p-3.5">
                <p className="flex items-center gap-1.5 text-xs font-bold text-[var(--cool)]">
                  <Play className="h-3.5 w-3.5" /> Practice mode
                </p>
                <p className="mt-1 text-[11px] text-[var(--cool-soft)]">{practiceFeedback}</p>
                {practiceSolved && (
                  <button
                    type="button"
                    onClick={onComplete}
                    className="mt-3 inline-flex w-full items-center justify-center gap-1.5 rounded-lg bg-[var(--cool)]/15 px-3 py-2 text-xs font-bold text-[var(--cool-soft)]"
                  >
                    Continue <ArrowRight className="h-3.5 w-3.5" />
                  </button>
                )}
              </div>
            )}

            {response?.solution && (
              <SolutionRevealCard
                challenge={challenge}
                response={response}
                activeLine={activeLine}
                activeIndex={activeIndex}
                onStepPv={stepPv}
                onPracticeBestMove={startPractice}
                onContinue={onComplete}
                continueLabel={index + 1 < total ? 'Next Blind Drill' : 'Finish Queue'}
                onOpenGame={onOpenGame}
                compact
              />
            )}

            {!solved && (boardDetached || activeLine || practiceMode || previewMode) && (
              <button
                type="button"
                onClick={resetBoard}
                disabled={attempting}
                className="inline-flex w-full items-center justify-center gap-1.5 rounded-xl border border-[var(--a)]/25 bg-[var(--a-soft)] px-3 py-2.5 text-xs font-bold text-[var(--a)]"
              >
                <RotateCcw className="h-3.5 w-3.5" /> Return to blind puzzle
              </button>
            )}

            {attempting && (
              <div className="flex items-center justify-center gap-2 text-xs text-[var(--a)]">
                <Spinner className="h-3.5 w-3.5" /> Stockfish grading your candidate…
              </div>
            )}
          </aside>
        </div>
      </div>
    </div>
  );
}

export const MistakeVaultView: React.FC<MistakeVaultViewProps> = ({
  overview,
  onRefreshOverview,
  onOpenGame,
  onOpenLibrary,
}) => {
  const [status, setStatus] = useState('due');
  const [severity, setSeverity] = useState('all');
  const [motif, setMotif] = useState('all');
  const [phase, setPhase] = useState('all');
  const [search, setSearch] = useState('');
  const [data, setData] = useState<{ total: number; mistakes: MistakeChallengePublic[] }>({
    total: 0,
    mistakes: [],
  });
  const [loading, setLoading] = useState(true);
  const [loadError, setLoadError] = useState<string | null>(null);
  const [refreshKey, setRefreshKey] = useState(0);
  const [visible, setVisible] = useState(12);
  const [queue, setQueue] = useState<MistakeChallengePublic[]>([]);
  const [queueIndex, setQueueIndex] = useState(0);
  const [queueBusy, setQueueBusy] = useState(false);
  const queueRequestRef = useRef(0);
  useEffect(() => () => { queueRequestRef.current++; }, []);

  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    setLoadError(null);
    api
      .mistakes({ status, severity, motif, phase })
      .then((result) => {
        if (!cancelled) {
          setData(result);
          setVisible(12);
        }
      })
      .catch((err) => {
        if (!cancelled) setLoadError(err instanceof Error ? err.message : 'Could not load mistakes.');
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [status, severity, motif, phase, refreshKey]);

  const filtered = useMemo(() => {
    const q = search.trim().toLowerCase();
    if (!q) return data.mistakes;
    return data.mistakes.filter((m) => {
      const haystack =
        `${m.gameOpponent} ${m.openingName} ${m.gameDate} ${m.playedMove.san} ${MOTIF_LABELS[m.motif]} ${PHASE_LABELS[m.phase]} ${m.severity} ${m.moveNumber}`.toLowerCase();
      return haystack.includes(q);
    });
  }, [data.mistakes, search]);

  const stats = overview?.mistakeStats;
  const dueCount = stats ? stats.needsReview + stats.learning + stats.unseen : 0;
  const masteryPct = stats && stats.totalDiscovered > 0 ? (stats.mastered / stats.totalDiscovered) * 100 : 0;

  const startQueue = (items: MistakeChallengePublic[]) => {
    if (items.length === 0) return;
    queueRequestRef.current++;
    setQueueBusy(false);
    setQueue(items);
    setQueueIndex(0);
  };

  const startDueQueue = async () => {
    const request = ++queueRequestRef.current;
    setQueueBusy(true);
    setLoadError(null);
    try {
      const result = await api.mistakes({ status: 'due' });
      if (request !== queueRequestRef.current) return;
      if (result.mistakes.length) startQueue(result.mistakes);
      else setLoadError('No drills are due now. Refresh the overview to update the count.');
    } catch (err) {
      if (request === queueRequestRef.current) setLoadError(err instanceof Error ? err.message : 'Could not build the review queue.');
    } finally {
      if (request === queueRequestRef.current) setQueueBusy(false);
    }
  };

  const completeCurrent = () => {
    if (queueIndex + 1 < queue.length) {
      setQueueIndex((idx) => idx + 1);
    } else {
      setQueue([]);
      setQueueIndex(0);
    }
    setRefreshKey((key) => key + 1);
    onRefreshOverview();
  };

  const closeQueue = () => {
    setQueue([]);
    setQueueIndex(0);
    setRefreshKey((key) => key + 1);
    onRefreshOverview();
  };

  const openGameFromVault = (gameId: string, mistakeId: string) => {
    setQueue([]);
    setQueueIndex(0);
    onOpenGame(gameId, mistakeId);
  };

  const resetFilters = () => {
    setStatus('due');
    setSeverity('all');
    setMotif('all');
    setPhase('all');
    setSearch('');
  };

  const activeChallenge = queue[queueIndex] ?? null;

  return (
    <div className="mx-auto max-w-[1280px] space-y-5 view-shell">
      <header className="premium-card relative flex flex-wrap items-end justify-between gap-4 overflow-hidden rounded-2xl border border-[var(--line)] p-5 animate-fade-up">
        <div className="absolute inset-x-0 top-0 h-[3px] bg-gradient-to-r from-[var(--a-deep)] via-[var(--a2)] to-[var(--a-deep)]" />
        <div>
          <div className="flex items-center gap-2">
            <span className="h-px w-5 bg-[var(--a)]" />
            <Eyebrow>Cross-game spaced repetition</Eyebrow>
          </div>
          <h1 className="mt-1 font-display text-3xl font-semibold text-[var(--ink)] sm:text-4xl">
            Mistake Vault
          </h1>
          <p className="mt-1 max-w-2xl text-sm text-[var(--ink-muted)]">
            Every Stockfish-verified mistake from every analyzed game. Due positions come first, then learning, then unseen — and answers stay hidden until a drill is failed.
          </p>
        </div>
        <button
          type="button"
          data-tour="vault-train"
          onClick={() => void startDueQueue()}
          disabled={queueBusy || dueCount === 0}
          className="inline-flex items-center gap-2 rounded-xl bg-[var(--a)] px-4 py-3 text-sm font-bold text-[#0a0714] transition hover:bg-[var(--a-hover)] hover-lift tap-scale disabled:opacity-50"
        >
          {queueBusy ? <Spinner /> : <Target className="h-4 w-4" />}
          Train {dueCount} due
        </button>
      </header>

      <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-4">
        <SurfaceCard className="flex items-center gap-4 p-4">
          <ProgressRing value={masteryPct} size={68} label={`${Math.round(masteryPct)}%`} subLabel="mastered" color="#4cc9f0" />
          <div>
            <Eyebrow>Mastery</Eyebrow>
            <p className="mt-1 font-display text-2xl font-semibold text-[var(--ink)]">
              {stats?.mastered ?? 0}<span className="text-base text-[var(--ink-muted)]"> / {stats?.totalDiscovered ?? 0}</span>
            </p>
            <p className="mt-1 text-[11px] text-[var(--ink-secondary)]">clean blind recalls</p>
          </div>
        </SurfaceCard>

        <SurfaceCard className="p-4">
          <Eyebrow>First-try solve rate</Eyebrow>
          <div className="mt-2 flex items-end justify-between">
            <p className="font-display text-3xl font-semibold text-[var(--ink)]">{stats?.firstTrySolveRate ?? 0}%</p>
            <Brain className="h-5 w-5 text-[var(--a)]" />
          </div>
          <ProgressBar className="mt-3" value={stats?.firstTrySolveRate ?? 0} tone="bronze" />
          <p className="mt-2 text-[11px] text-[var(--ink-secondary)]">Only solved-first-try drills count.</p>
        </SurfaceCard>

        <SurfaceCard className="p-4">
          <Eyebrow>Due queue</Eyebrow>
          <div className="mt-2 flex items-end justify-between">
            <p className="font-display text-3xl font-semibold text-[var(--warm-soft)]">{dueCount}</p>
            <Flame className="h-5 w-5 text-[var(--warm)]" />
          </div>
          <div className="mt-2 flex flex-wrap gap-1.5">
            <Pill className="border-[var(--warm)]/25 bg-[var(--warm)]/[0.06] text-[var(--warm-soft)]">{stats?.needsReview ?? 0} review</Pill>
            <Pill className="border-[var(--amber)]/25 bg-[var(--amber)]/[0.06] text-[var(--amber)]">{stats?.learning ?? 0} learning</Pill>
            <Pill>{stats?.unseen ?? 0} unseen</Pill>
          </div>
        </SurfaceCard>

        <SurfaceCard className="p-4">
          <Eyebrow>Weakest motifs</Eyebrow>
          <div className="mt-2 space-y-2">
            {(stats?.byMotif ?? []).slice(0, 3).map((row) => (
              <div key={row.motif}>
                <div className="mb-1 flex items-center justify-between text-[10px]">
                  <span className="truncate text-[var(--ink-secondary)]">{row.label}</span>
                  <span className="font-mono-tabular text-[var(--ink-secondary)]">{row.count}</span>
                </div>
                <ProgressBar value={row.count ? (row.mastered / row.count) * 100 : 0} tone="green" />
              </div>
            ))}
            {(stats?.byMotif.length ?? 0) === 0 && (
              <p className="text-[11px] text-[var(--ink-muted)]">Analyze more games to reveal patterns.</p>
            )}
          </div>
        </SurfaceCard>
      </div>

      <SurfaceCard className="p-4">
        <div className="flex flex-wrap items-center justify-between gap-3">
          <div className="flex items-center gap-2">
            <Filter className="h-4 w-4 text-[var(--a)]" />
            <h2 className="font-display text-lg font-semibold text-[var(--ink)]">Review queue</h2>
            <Pill>{data.total} positions</Pill>
          </div>
          <button
            type="button"
            onClick={resetFilters}
            className="text-[11px] font-semibold text-[var(--ink-secondary)] transition hover:text-[var(--a)]"
          >
            Reset filters
          </button>
        </div>

        <div className="mt-3 grid gap-2 sm:grid-cols-2 lg:grid-cols-5">
          <FilterSelect label="Mastery" value={status} options={STATUS_OPTIONS} onChange={setStatus} />
          <FilterSelect label="Severity" value={severity} options={SEVERITY_OPTIONS} onChange={setSeverity} />
          <FilterSelect
            label="Motif"
            value={motif}
            options={[
              { value: 'all', label: 'All motifs' },
              ...Object.entries(MOTIF_LABELS).map(([value, label]) => ({ value, label })),
            ]}
            onChange={setMotif}
          />
          <FilterSelect label="Phase" value={phase} options={PHASE_OPTIONS} onChange={setPhase} />
          <label className="block">
            <span className="mb-1 block text-[9px] font-semibold uppercase tracking-[0.14em] text-[var(--ink-muted)]">
              Search
            </span>
            <div className="relative">
              <Search className="pointer-events-none absolute left-2.5 top-2.5 h-3.5 w-3.5 text-[var(--ink-muted)]" />
              <input
                value={search}
                onChange={(event) => setSearch(event.target.value)}
                placeholder="Opponent, opening…"
                className="w-full rounded-lg border border-[var(--line)] bg-[var(--surface)] py-2 pl-8 pr-2 text-[11px] text-[var(--ink-soft)] outline-none placeholder:text-[var(--ink-dim)] focus:border-[var(--a)]/50"
              />
            </div>
          </label>
        </div>
      </SurfaceCard>

      {loadError && (
        <div className="rounded-xl border border-[var(--warm)]/30 bg-[var(--warm-bg)] px-4 py-3 text-xs text-[var(--warm-soft)]">
          {loadError}
        </div>
      )}

      {loading ? (
        <div className="flex items-center justify-center gap-2 rounded-2xl border border-[var(--line)] bg-[var(--surface)]/60 py-16 text-sm text-[var(--ink-muted)]">
          <Spinner /> Loading spaced-repetition queue…
        </div>
      ) : loadError ? null : filtered.length === 0 ? (
        <EmptyState
          icon={status === 'due' ? <Trophy className="h-6 w-6" /> : <Sparkles className="h-6 w-6" />}
          title={status === 'due' && dueCount === 0 ? 'Nothing is due right now.' : 'No mistakes match these filters.'}
          detail={
            status === 'due' && dueCount === 0
              ? 'There are no discovered positions due. Analyze another game or paste a PGN to add fresh positions.'
              : 'Try widening the mastery, motif, severity, phase, or search filters.'
          }
          action={
            <div className="flex flex-wrap justify-center gap-2">
              {onOpenLibrary && (
                <button
                  type="button"
                  onClick={onOpenLibrary}
                  className="rounded-lg bg-[var(--a)] px-4 py-2.5 text-xs font-bold text-[#0a0714]"
                >
                  Analyze another game
                </button>
              )}
              <button
                type="button"
                onClick={resetFilters}
                className="rounded-lg border border-[var(--line)] px-4 py-2.5 text-xs font-semibold text-[var(--ink-soft)]"
              >
                Reset filters
              </button>
            </div>
          }
        />
      ) : (
        <>
          <div className="flex flex-wrap items-center justify-between gap-2">
            <p className="text-xs text-[var(--ink-secondary)]">
              Showing {Math.min(visible, filtered.length)} of {filtered.length} · sorted by review priority
            </p>
            <button
              type="button"
              onClick={() => startQueue(filtered)}
              className="inline-flex items-center gap-1.5 rounded-lg border border-[var(--a)]/30 bg-[var(--a-soft)] px-3 py-2 text-[11px] font-bold text-[var(--a)] transition hover:bg-[var(--a)]/15"
            >
              <Play className="h-3.5 w-3.5" /> Train filtered queue
            </button>
          </div>

          <div data-tour="vault-queue" className="grid gap-3 md:grid-cols-2 xl:grid-cols-3">
            {filtered.slice(0, visible).map((mistake) => (
              <MistakeCard
                key={mistake.id}
                mistake={mistake}
                onTrain={() => startQueue([mistake])}
                onOpenGame={() => openGameFromVault(mistake.gameId, mistake.id)}
              />
            ))}
          </div>

          {visible < filtered.length && (
            <div className="flex justify-center">
              <button
                type="button"
                onClick={() => setVisible((count) => count + 12)}
                className="rounded-lg border border-[var(--line)] px-4 py-2.5 text-xs font-semibold text-[var(--ink-soft)] transition hover:border-[var(--a)]/45"
              >
                Load 12 more
              </button>
            </div>
          )}
        </>
      )}

      {activeChallenge && (
        <VaultTrainerModal
          key={`${activeChallenge.id}:${queueIndex}`}
          challenge={activeChallenge}
          index={queueIndex}
          total={queue.length}
          onClose={closeQueue}
          onComplete={completeCurrent}
          onOpenGame={() => openGameFromVault(activeChallenge.gameId, activeChallenge.id)}
          onMasteryChanged={onRefreshOverview}
        />
      )}
    </div>
  );
};
