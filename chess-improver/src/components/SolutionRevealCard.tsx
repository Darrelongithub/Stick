import React, { useRef, useState } from 'react';
import { Chess } from 'chess.js';
import { api } from '../lib/api';
import {
  ArrowRight,
  Eye,
  Lightbulb,
  Play,
  Sparkles,
  Target,
} from 'lucide-react';
import type { AttemptMoveResponse, MistakeChallengePublic } from '../../shared/types';
import { applyUciToFen, cx, formatScore, lineMoveLabel } from '../lib/chessFormat';

export type PvLineKind = 'best' | 'refutation' | null;

interface SolutionRevealCardProps {
  challenge: MistakeChallengePublic;
  response: AttemptMoveResponse;
  activeLine: PvLineKind;
  activeIndex: number;
  onStepPv: (kind: 'best' | 'refutation', index: number) => void;
  onPracticeBestMove: () => void;
  onContinue: () => void;
  continueLabel?: string;
  onOpenGame?: () => void;
  compact?: boolean;
}

function SanStepper({
  kind,
  title,
  description,
  moves,
  startFen,
  activeLine,
  activeIndex,
  onStep,
}: {
  kind: 'best' | 'refutation';
  title: string;
  description: string;
  moves: string[];
  startFen: string;
  activeLine: PvLineKind;
  activeIndex: number;
  onStep: (kind: 'best' | 'refutation', index: number) => void;
}) {
  const isBest = kind === 'best';
  return (
    <div className="rounded-xl border border-[var(--line)] bg-[var(--surface)]/80 p-3 shadow-[inset_0_1px_0_rgba(255,255,255,0.9)]">
      <div className="mb-2 flex items-start justify-between gap-3">
        <div className="min-w-0">
          <p className={cx('text-xs font-semibold', isBest ? 'text-[var(--cool-soft)]' : 'text-[var(--warm-soft)]')}>
            {title}
          </p>
          <p className="mt-0.5 text-[10px] leading-relaxed text-[var(--ink-muted)]">{description}</p>
        </div>
        <span
          className={cx(
            'shrink-0 rounded-full border px-2 py-0.5 text-[9px] font-bold uppercase tracking-wider',
            isBest
              ? 'border-[var(--cool)]/30 bg-[var(--cool-bg)] text-[var(--cool-soft)]'
              : 'border-[var(--warm)]/30 bg-[var(--warm)]/10 text-[var(--warm-soft)]'
          )}
        >
          {isBest ? 'Stockfish PV' : 'Punishment'}
        </span>
      </div>

      {moves.length === 0 ? (
        <p className="text-[11px] italic text-[var(--ink-muted)]">No forcing continuation in the saved line.</p>
      ) : (
        <div className="flex flex-wrap gap-1.5">
          {moves.map((san, index) => {
            const active = activeLine === kind && activeIndex === index;
            return (
              <button
                key={`${kind}-${san}-${index}`}
                type="button"
                onClick={() => onStep(kind, index)}
                className={cx(
                  'rounded-md border px-2 py-1 font-mono-tabular text-[11px] font-semibold transition',
                  active
                    ? isBest
                      ? 'border-[var(--cool)] bg-[var(--cool)]/20 text-[var(--cool-deep)]'
                      : 'border-[var(--warm)] bg-[var(--warm)]/20 text-[var(--warm-soft)]'
                    : isBest
                      ? 'border-[var(--cool)]/20 bg-[var(--cool)]/[0.05] text-[var(--cool-soft)] hover:border-[var(--cool)]/60'
                      : 'border-[var(--warm)]/20 bg-[var(--warm)]/[0.05] text-[var(--warm-soft)] hover:border-[var(--warm)]/60'
                )}
                title={`Replay through ${san}`}
              >
                {lineMoveLabel(startFen, index)} {san}
              </button>
            );
          })}
        </div>
      )}
    </div>
  );
}

function ExplanationChat({ challenge, solution }: { challenge: MistakeChallengePublic; solution: NonNullable<AttemptMoveResponse['solution']> }) {
  const [question, setQuestion] = useState('');
  const [messages, setMessages] = useState<Array<{ question: string; answer: string; source: string }>>([]);
  const [busy, setBusy] = useState(false);
  const lock = useRef(false);

  const answerFor = (intent: string) => {
    const best = solution.bestMove.san;
    const played = challenge.playedMove.san;
    const bestScore = formatScore(solution.bestEvalUserCp, solution.bestEvalUserMate);
    const playedScore = formatScore(challenge.evalAfterPlayedUserCp, challenge.evalAfterPlayedUserMate);
    let fact = '';
    try {
      const board = new Chess(challenge.fenBefore);
      const move = board.move({ from: solution.bestMove.from, to: solution.bestMove.to, promotion: solution.bestMove.uci[4] });
      if (board.isCheckmate()) fact = ' It gives checkmate.';
      else if (move.captured) fact = ` It captures a ${ { p: 'pawn', n: 'knight', b: 'bishop', r: 'rook', q: 'queen', k: 'king' }[move.captured] }.${board.isCheck() ? ' It also gives check.' : ''}`;
      else if (board.isCheck()) fact = ' It gives check.';
    } catch { /* Keep the explanation limited to the stored engine evaluation. */ }
    // Only replay legal saved moves; older caches may contain truncated or
    // damaged SAN lines even when the challenge position itself is valid.
    let line = '';
    try {
      const replay = new Chess(challenge.fenBefore);
      const verified: string[] = [];
      for (const san of solution.bestPvSan.slice(0, 4)) {
        const move = replay.move(san);
        if (!move || (verified.length === 0 && `${move.from}${move.to}${move.promotion ?? ''}` !== solution.bestMove.uci)) break;
        verified.push(move.san);
      }
      line = verified.map((san, i) => `${lineMoveLabel(challenge.fenBefore, i)} ${san}`).join(' ');
    } catch { /* An invalid saved continuation is not presented as a fact. */ }

    if (intent === 'LINE') return line ? `One line Stockfish considered is ${line}. It is a possible continuation, not a prediction.` : 'No continuation was saved for this position.';
    if (intent === 'COMPARE') return `Your game move ${played} was evaluated at ${playedScore}; Stockfish’s leading move ${best} was evaluated at ${bestScore}, from your side’s perspective.${fact} These scores compare positions, not a guaranteed outcome.`;
    if (intent === 'EVAL') return `From your side’s perspective, ${best} is ${bestScore} and your game move ${played} is ${playedScore}. Positive pawn scores favor you; mate scores indicate a forced mating line. Evaluations can change with deeper analysis.`;
    if (intent === 'WHY') return `Stockfish preferred ${best} because it evaluated the resulting position more favorably than your game move ${played}: ${bestScore} versus ${playedScore}, from your side’s perspective.${fact}${line ? ` One possible line is ${line}.` : ''} The engine line shows what it considered; it does not prove a single verbal reason.`;
    return 'I can explain the score, compare your game move, or show the saved engine line. Try asking “Why is this move best?”';
  };

  const submit = async (text: string) => {
    const trimmed = text.trim();
    if (!trimmed || lock.current) return;
    lock.current = true; setBusy(true);
    try {
      const result = await api.explanationIntent(trimmed);
      setMessages(previous => [...previous, { question: trimmed, answer: answerFor(result.intent), source: result.source === 'gemini' ? 'Gemini topic · Stockfish facts' : 'Local topic · Stockfish facts' }].slice(-6));
      setQuestion('');
    } catch {
      setMessages(previous => [...previous, { question: trimmed, answer: answerFor(/score|eval|advantage/i.test(trimmed) ? 'EVAL' : /line|continue|next|repl(?:y|ies)|variation/i.test(trimmed) ? 'LINE' : /instead|game move|my move|difference|compare|wrong/i.test(trimmed) ? 'COMPARE' : /why|best|explain|what|how/i.test(trimmed) ? 'WHY' : 'OTHER'), source: 'Local fallback · Stockfish facts' }].slice(-6));
      setQuestion('');
    } finally { lock.current = false; setBusy(false); }
  };

  return <section className="rounded-xl border border-[var(--a)]/25 bg-[var(--surface)]/80 p-3" aria-label="Ask about the revealed move">
    <h3 className="text-xs font-bold text-[var(--ink-soft)]">Darrel, ask about this move</h3>
    <p className="mt-1 text-[11px] text-[var(--ink-muted)]">After a reveal, ask a follow-up. Gemini selects a topic when configured; the answer uses only the saved Stockfish evaluation and line.</p>
    <div className="mt-2 flex flex-wrap gap-1.5">
      {['Why is this move best?', 'Show me the line', 'Compare my move'].map(text => <button key={text} type="button" disabled={busy} onClick={() => void submit(text)} className="rounded-lg border border-[var(--line)] px-2 py-1.5 text-[10px] text-[var(--a2)] disabled:opacity-50">{text}</button>)}
    </div>
    <div aria-live="polite" className="mt-2 max-h-52 space-y-2 overflow-y-auto">{messages.map((message, i) => <div key={i} className="rounded-lg bg-[var(--surface-soft)] p-2 text-[11px] leading-relaxed text-[var(--ink-soft)]"><p className="font-semibold">You: {message.question}</p><p className="mt-1">{message.answer}</p><p className="mt-1 text-[10px] text-[var(--ink-muted)]">{message.source}</p></div>)}</div>
    <form className="mt-2 flex gap-2" onSubmit={event => { event.preventDefault(); void submit(question); }}>
      <input aria-label="Question about this move" maxLength={800} value={question} onChange={event => setQuestion(event.target.value)} placeholder="Why is that move best?" className="min-w-0 flex-1 rounded-lg border border-[var(--line)] bg-[var(--surface)] px-2 py-2 text-xs text-[var(--ink)]" />
      <button type="submit" disabled={busy || !question.trim()} className="rounded-lg bg-[var(--a)] px-3 py-2 text-xs font-bold text-[#0a0714] disabled:opacity-50">{busy ? 'Thinking…' : 'Ask'}</button>
    </form>
  </section>;
}

export const SolutionRevealCard: React.FC<SolutionRevealCardProps> = ({
  challenge,
  response,
  activeLine,
  activeIndex,
  onStepPv,
  onPracticeBestMove,
  onContinue,
  continueLabel = 'Next Mistake',
  onOpenGame,
  compact = false,
}) => {
  const solution = response.solution;
  if (!solution) return null;

  const alternatives = solution.alternatives
    .filter((alt) => alt.uci !== solution.bestMove.uci)
    .slice(0, 3);

  return (
    <div
      style={{ background: '#201a30' }}
      className="premium-card overflow-hidden rounded-2xl border border-[var(--warm)]/30 animate-scale-in"
    >
      <div className="h-[3px] w-full bg-[var(--warm)]" />
      <div className="flex items-center gap-2 border-b border-[var(--warm)]/20 bg-[var(--warm-bg)] px-4 py-2.5 text-[10px] font-bold uppercase tracking-[0.14em] text-[var(--warm-soft)]">
        <Eye className="h-3.5 w-3.5" /> Unlocked only after your failed attempt
      </div>

      <div className={cx('space-y-3', compact ? 'p-3' : 'p-4')}>
        <div className="flex items-start justify-between gap-4">
          <div>
            <p className="premium-kicker text-[10px] font-semibold uppercase tracking-[0.16em]">
              Stockfish 18 NNUE best move
            </p>
            <div className="mt-1 flex items-baseline gap-2.5">
              <span className="font-display text-3xl font-semibold text-[var(--ink)]">
                {solution.bestMove.san}
              </span>
              <span className="font-mono-tabular text-sm font-bold text-[var(--cool-soft)]">
                {formatScore(solution.bestEvalUserCp, solution.bestEvalUserMate)}
              </span>
            </div>
          </div>
          <div className="flex h-10 w-10 shrink-0 items-center justify-center rounded-xl border border-[var(--a-deep)] bg-[var(--a)] text-[#0a0714]">
            <Target className="h-5 w-5" />
          </div>
        </div>

        <p className="rounded-lg border border-[var(--line)] bg-[var(--surface)]/80 px-3 py-2.5 text-[12px] leading-relaxed text-[var(--ink-soft)]">
          <Lightbulb className="mr-1.5 inline h-3.5 w-3.5 align-[-2px] text-[var(--a)]" />
          {solution.coachExplanation}
        </p>

        <div className="grid grid-cols-3 gap-2">
          {[
            { label: 'Before', cp: challenge.evalBeforeUserCp, mate: challenge.evalBeforeUserMate },
            { label: 'Your game move', cp: challenge.evalAfterPlayedUserCp, mate: challenge.evalAfterPlayedUserMate },
            { label: 'Best line', cp: solution.bestEvalUserCp, mate: solution.bestEvalUserMate },
          ].map((item, idx) => (
            <div
              key={item.label}
              className={cx(
                'rounded-lg border px-2 py-2 text-center',
                idx === 2
                  ? 'border-[var(--cool)]/25 bg-[var(--cool-bg)]'
                  : 'border-[var(--line)] bg-[var(--surface)]/75'
              )}
            >
              <p className="text-[8px] font-semibold uppercase tracking-wider text-[var(--ink-muted)]">
                {item.label}
              </p>
              <p
                className={cx(
                  'mt-1 font-mono-tabular text-xs font-bold',
                  idx === 2 ? 'text-[var(--cool-soft)]' : idx === 1 ? 'text-[var(--warm-soft)]' : 'text-[var(--ink-soft)]'
                )}
              >
                {formatScore(item.cp, item.mate)}
              </p>
            </div>
          ))}
        </div>

        <ExplanationChat key={challenge.id} challenge={challenge} solution={solution} />

        <SanStepper
          kind="best"
          title="Step through the best line"
          description="Click any SAN move to replay the position on the board."
          moves={solution.bestPvSan}
          startFen={challenge.fenBefore}
          activeLine={activeLine}
          activeIndex={activeIndex}
          onStep={onStepPv}
        />

        <SanStepper
          kind="refutation"
          title={`Why ${challenge.playedMove.san} was punished`}
          description="Starts immediately after your actual game move."
          moves={solution.playedRefutationPvSan}
          startFen={applyUciToFen(challenge.fenBefore, challenge.playedMove.uci).fen}
          activeLine={activeLine}
          activeIndex={activeIndex}
          onStep={onStepPv}
        />

        {alternatives.length > 0 && (
          <div className="rounded-xl border border-[var(--line)] bg-[var(--surface)]/75 p-3">
            <p className="mb-2 flex items-center gap-1.5 text-[10px] font-semibold uppercase tracking-[0.14em] text-[var(--ink-secondary)]">
              <Sparkles className="h-3 w-3 text-[var(--a)]" /> Other engine lines
            </p>
            <div className="space-y-1.5">
              {alternatives.map((alt) => (
                <div key={alt.uci} className="flex items-center justify-between gap-3 text-xs">
                  <span className="font-mono-tabular font-semibold text-[var(--ink-soft)]">{alt.san}</span>
                  <span className="font-mono-tabular text-[11px] text-[var(--ink-muted)]">
                    {formatScore(alt.evalUserCp, alt.evalUserMate)}
                  </span>
                </div>
              ))}
            </div>
          </div>
        )}

        <div className="flex flex-wrap gap-2 pt-1">
          <button
            type="button"
            onClick={onPracticeBestMove}
            className="inline-flex flex-1 items-center justify-center gap-1.5 rounded-lg bg-[var(--a)] px-3 py-2.5 text-xs font-bold text-[#0a0714] transition hover:bg-[var(--a-hover)]"
          >
            <Play className="h-3.5 w-3.5" /> Practice Best Move on Board
          </button>
          {onOpenGame && (
            <button
              type="button"
              onClick={onOpenGame}
              className="inline-flex items-center justify-center rounded-lg border border-[var(--line)] bg-[var(--surface)]/70 px-3 py-2.5 text-xs font-semibold text-[var(--ink-soft)] transition hover:border-[var(--a)]/50 hover:text-[var(--ink)]"
            >
              Full Game
            </button>
          )}
        </div>

        <button
          type="button"
          onClick={onContinue}
          className="inline-flex w-full items-center justify-center gap-1.5 rounded-lg border border-[var(--cool)]/25 bg-[var(--cool-bg)] px-3 py-2.5 text-xs font-bold text-[var(--cool-soft)] transition hover:bg-[var(--cool)]/15"
        >
          {continueLabel} <ArrowRight className="h-3.5 w-3.5" />
        </button>
      </div>
    </div>
  );
};
