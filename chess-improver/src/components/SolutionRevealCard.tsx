import React from 'react';
import {
  ArrowRight,
  CheckCircle2,
  Eye,
  Lightbulb,
  Play,
  Sparkles,
  Target,
} from 'lucide-react';
import type { AttemptMoveResponse, MistakeChallengePublic } from '../../shared/types';
import { cx, formatScore } from '../lib/chessFormat';

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
  activeLine,
  activeIndex,
  onStep,
}: {
  kind: 'best' | 'refutation';
  title: string;
  description: string;
  moves: string[];
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
                {index + 1}. {san}
              </button>
            );
          })}
        </div>
      )}
    </div>
  );
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

  const wasFailure = response.outcome === 'failed_revealed';
  const alternatives = solution.alternatives
    .filter((alt) => alt.uci !== solution.bestMove.uci)
    .slice(0, 3);

  return (
    <div
      style={{ background: wasFailure ? '#201a30' : '#102a35' }}
      className={cx(
        'premium-card overflow-hidden rounded-2xl border animate-scale-in',
        wasFailure
          ? 'border-[var(--warm)]/30'
          : 'border-[var(--cool)]/30'
      )}
    >
      <div className={cx('h-[3px] w-full', wasFailure ? 'bg-[var(--warm)]' : 'bg-[var(--cool)]')} />
      <div
        className={cx(
          'flex items-center gap-2 border-b px-4 py-2.5 text-[10px] font-bold uppercase tracking-[0.14em]',
          wasFailure
            ? 'border-[var(--warm)]/20 bg-[var(--warm-bg)] text-[var(--warm-soft)]'
            : 'border-[var(--cool)]/20 bg-[var(--cool-bg)] text-[var(--cool)]'
        )}
      >
        {wasFailure ? <Eye className="h-3.5 w-3.5" /> : <CheckCircle2 className="h-3.5 w-3.5" />}
        {wasFailure
          ? 'Unlocked only after your failed attempt'
          : 'You found a better move — full line unlocked'}
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

        <SanStepper
          kind="best"
          title="Step through the best line"
          description="Click any SAN move to replay the position on the board."
          moves={solution.bestPvSan}
          activeLine={activeLine}
          activeIndex={activeIndex}
          onStep={onStepPv}
        />

        <SanStepper
          kind="refutation"
          title={`Why ${challenge.playedMove.san} was punished`}
          description="Starts immediately after your actual game move."
          moves={solution.playedRefutationPvSan}
          activeLine={activeLine}
          activeIndex={activeIndex}
          onStep={onStepPv}
        />

        {alternatives.length > 0 && (
          <div className="rounded-xl border border-[var(--line)] bg-[var(--surface)]/75 p-3">
            <p className="mb-2 flex items-center gap-1.5 text-[10px] font-semibold uppercase tracking-[0.14em] text-[var(--ink-secondary)]">
              <Sparkles className="h-3 w-3 text-[var(--a)]" /> Other engine-approved ideas
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
