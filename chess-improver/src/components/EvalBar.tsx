import React from 'react';
import type { PlayerColor } from '../../shared/types';
import {
  cx,
  evalToWinFraction,
  formatScore,
  whiteEvalFromUserEval,
} from '../lib/chessFormat';

interface EvalBarProps {
  /** Evaluation from the user's perspective: positive = good for the learner. */
  scoreCp: number;
  scoreMate: number | null;
  userColor: PlayerColor;
  orientation: PlayerColor;
  label?: string;
  spoilerLocked?: boolean;
  className?: string;
}

export const EvalBar: React.FC<EvalBarProps> = ({
  scoreCp,
  scoreMate,
  userColor,
  orientation,
  label,
  spoilerLocked = false,
  className,
}) => {
  const { whiteCp, whiteMate } = whiteEvalFromUserEval(userColor, scoreCp, scoreMate);
  const whiteFraction = evalToWinFraction(whiteCp, whiteMate);
  const bottomFraction = orientation === 'w' ? whiteFraction : 1 - whiteFraction;

  const bottomIsWhite = orientation === 'w';
  const topColor = bottomIsWhite ? '#0c0a13' : '#f3f1f8';
  const bottomColor = bottomIsWhite ? '#f3f1f8' : '#0c0a13';
  const fillPercent = Math.max(3, Math.min(97, bottomFraction * 100));

  return (
    <div className={cx('flex h-full min-h-0 flex-col items-center gap-2', className)}>
      <div className="relative min-h-0 w-[22px] flex-1 overflow-hidden rounded-full border border-[var(--line)] shadow-[inset_0_0_14px_rgba(0, 0, 0, 0.135)]">
        <div className="absolute inset-0" style={{ backgroundColor: topColor }} />
        <div
          className="absolute bottom-0 left-0 right-0 transition-[height] duration-700 ease-out"
          style={{
            height: `${fillPercent}%`,
            backgroundColor: bottomColor,
            boxShadow: bottomIsWhite
              ? 'inset 0 10px 18px rgba(255,255,255,0.28)'
              : 'inset 0 10px 18px rgba(255,255,255,0.04)',
          }}
        />
        <div className="pointer-events-none absolute left-0 right-0 top-1/2 h-px bg-[var(--surface-deep)]/20" />
        <div className="pointer-events-none absolute inset-0 bg-gradient-to-r from-[var(--a)]/10 via-transparent to-[var(--a2)]/10" />
        {spoilerLocked && (
          <div className="pointer-events-none absolute inset-0 flex items-center justify-center">
            <span className="rotate-180 text-[8px] font-bold tracking-[0.18em] text-[var(--ink)] drop-shadow-[0_1px_2px_rgba(0, 0, 0, 0.7)] [writing-mode:vertical-rl]">
              PRE-MOVE
            </span>
          </div>
        )}
      </div>

      <div className="flex flex-col items-center gap-1">
        <span className="rounded-md border border-[var(--line)] bg-[var(--surface)] px-1.5 py-0.5 font-mono-tabular text-[10px] font-bold text-[var(--ink)]">
          {formatScore(scoreCp, scoreMate)}
        </span>
        {label && (
          <span className="max-w-[72px] text-center text-[8px] font-semibold uppercase tracking-[0.12em] leading-tight text-[var(--ink-muted)]">
            {label}
          </span>
        )}
      </div>
    </div>
  );
};
