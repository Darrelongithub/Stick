import React from 'react';
import { cx, MASTERY_META } from '../lib/chessFormat';
import type { MasteryState } from '../../shared/types';

export function SurfaceCard({
  children,
  className,
  style,
  animate = true,
}: {
  children: React.ReactNode;
  className?: string;
  style?: React.CSSProperties;
  animate?: boolean;
}) {
  return (
    <section
      style={style}
      className={cx(
        'premium-card rounded-2xl border',
        animate && 'animate-fade-up hover-lift',
        className
      )}
    >
      {children}
    </section>
  );
}

export function Eyebrow({
  children,
  className,
}: {
  children: React.ReactNode;
  className?: string;
}) {
  return (
    <p
      className={cx(
        'premium-kicker text-[10px] font-semibold uppercase tracking-[0.22em]',
        className
      )}
    >
      {children}
    </p>
  );
}

export function Pill({
  children,
  className,
  title,
}: {
  children: React.ReactNode;
  className?: string;
  title?: string;
}) {
  return (
    <span
      title={title}
      className={cx(
        'inline-flex items-center gap-1 rounded-full border px-2.5 py-1 text-[10px] font-semibold tracking-[0.04em] transition-colors duration-200',
        className ?? 'border-[var(--line)] bg-[var(--surface)] text-[var(--ink-soft)]'
      )}
    >
      {children}
    </span>
  );
}

export function MasteryPill({
  status,
  showDot = true,
}: {
  status: MasteryState;
  showDot?: boolean;
}) {
  const meta = MASTERY_META[status];
  return (
    <Pill className={meta.pillClass} title={meta.description}>
      {showDot && (
        <span className={cx('h-1.5 w-1.5 rounded-full animate-pulse-soft', meta.dotClass)} />
      )}
      {meta.label}
    </Pill>
  );
}

export function SegmentedControl<T extends string>({
  value,
  options,
  onChange,
  size = 'md',
  className,
  disabled = false,
}: {
  value: T;
  options: Array<{ value: T; label: string; hint?: string }>;
  onChange: (value: T) => void;
  size?: 'sm' | 'md';
  className?: string;
  disabled?: boolean;
}) {
  return (
    <div
      className={cx(
        'inline-flex items-center rounded-xl border border-[var(--line)] bg-[var(--surface)]/90 p-1 transition-opacity',
        disabled && 'pointer-events-none opacity-45',
        className
      )}
      aria-disabled={disabled}
    >
      {options.map((option) => {
        const active = option.value === value;
        return (
          <button
            key={option.value}
            type="button"
            title={option.hint}
            disabled={disabled}
            aria-pressed={active}
            onClick={() => onChange(option.value)}
            className={cx(
              'rounded-lg font-semibold transition-all duration-200',
              size === 'sm' ? 'px-2.5 py-1 text-[11px]' : 'px-3.5 py-2 text-xs',
              active
                ? 'bg-[var(--a)] text-[#0a0714] shadow-[0_5px_16px_rgba(139, 124, 255, 0.22)]'
                : 'text-[var(--ink-secondary)] hover:bg-[var(--surface)]/85 hover:text-[var(--ink)]'
            )}
          >
            {option.label}
          </button>
        );
      })}
    </div>
  );
}

type ProgressTone = 'bronze' | 'green' | 'red' | 'blue';

export function ProgressBar({
  value,
  tone = 'bronze',
  className,
  shimmer = true,
}: {
  value: number;
  tone?: ProgressTone;
  className?: string;
  shimmer?: boolean;
}) {
  const colors: Record<ProgressTone, string> = {
    bronze: 'from-[var(--a-deep)] to-[var(--a2)]',
    green: 'from-[var(--cool-deep)] to-[var(--cool)]',
    red: 'from-[var(--a)] to-[var(--warm)]',
    blue: 'from-[var(--cool-deep)] to-[var(--cool)]',
  };
  return (
    <div className={cx('h-1.5 w-full overflow-hidden rounded-full bg-[var(--surface-soft)]', className)}>
      <div
        className={cx(
          'relative h-full overflow-hidden rounded-full bg-gradient-to-r transition-[width] duration-700 ease-out',
          colors[tone]
        )}
        style={{ width: `${Math.max(0, Math.min(100, value))}%` }}
      >
        {shimmer && <span className="progress-shimmer" />}
      </div>
    </div>
  );
}

export function ProgressRing({
  value,
  size = 72,
  stroke = 7,
  color = '#8b7cff',
  label,
  subLabel,
}: {
  value: number;
  size?: number;
  stroke?: number;
  color?: string;
  label?: string;
  subLabel?: string;
}) {
  const radius = (size - stroke) / 2;
  const circumference = 2 * Math.PI * radius;
  const clamped = Math.max(0, Math.min(100, value));
  return (
    <div className="relative shrink-0 animate-scale-in" style={{ width: size, height: size }}>
      <svg viewBox={`0 0 ${size} ${size}`} className="h-full w-full -rotate-90">
        <circle
          cx={size / 2}
          cy={size / 2}
          r={radius}
          fill="none"
          stroke="rgba(255, 255, 255, 0.10)"
          strokeWidth={stroke}
        />
        <circle
          cx={size / 2}
          cy={size / 2}
          r={radius}
          fill="none"
          stroke={color}
          strokeWidth={stroke}
          strokeLinecap="round"
          strokeDasharray={circumference}
          strokeDashoffset={circumference * (1 - clamped / 100)}
          style={{ transition: 'stroke-dashoffset 700ms cubic-bezier(0.16,1,0.3,1)' }}
        />
      </svg>
      <div className="absolute inset-0 flex flex-col items-center justify-center leading-none">
        <span className="font-mono-tabular text-sm font-bold text-[var(--ink)]">
          {label ?? `${Math.round(clamped)}%`}
        </span>
        {subLabel && (
          <span className="mt-1 text-[8px] font-semibold uppercase tracking-widest text-[var(--ink-muted)]">
            {subLabel}
          </span>
        )}
      </div>
    </div>
  );
}

export function StatTile({
  label,
  value,
  sub,
  icon,
  accent = '#8b7cff',
  className,
  style,
}: {
  label: string;
  value: React.ReactNode;
  sub?: string;
  icon?: React.ReactNode;
  accent?: string;
  className?: string;
  style?: React.CSSProperties;
}) {
  return (
    <div
      style={style}
      className={cx(
        'premium-tile relative overflow-hidden rounded-xl border px-4 py-3 animate-fade-up hover-lift',
        className
      )}
    >
      <div
        className="absolute -right-5 -top-8 h-20 w-20 rounded-full blur-2xl"
        style={{ background: accent, opacity: 0.11 }}
      />
      <div className="relative flex items-start justify-between gap-3">
        <div className="min-w-0">
          <p className="text-[10px] font-semibold uppercase tracking-[0.16em] text-[var(--ink-muted)]">
            {label}
          </p>
          <p className="mt-1 font-display text-2xl font-semibold leading-none text-[var(--ink)]">
            {value}
          </p>
          {sub && <p className="mt-1.5 truncate text-[11px] text-[var(--ink-muted)]">{sub}</p>}
        </div>
        {icon && (
          <div
            className="flex h-8 w-8 shrink-0 items-center justify-center rounded-lg border animate-float"
            style={{ color: accent, borderColor: `${accent}33`, background: `${accent}0f` }}
          >
            {icon}
          </div>
        )}
      </div>
    </div>
  );
}

export function Spinner({ className }: { className?: string }) {
  return (
    <span
      className={cx(
        'inline-block h-4 w-4 animate-spin rounded-full border-2 border-current border-t-transparent',
        className
      )}
    />
  );
}

export function EmptyState({
  title,
  detail,
  icon,
  action,
}: {
  title: string;
  detail: string;
  icon?: React.ReactNode;
  action?: React.ReactNode;
}) {
  return (
    <div className="flex flex-col items-center justify-center rounded-2xl border border-dashed border-[var(--line-strong)] bg-[var(--surface)]/85 px-6 py-12 text-center animate-fade-up">
      {icon && (
        <div className="mb-4 flex h-12 w-12 items-center justify-center rounded-full border border-[var(--a)]/25 bg-[var(--a-soft)] text-[var(--a)] animate-ring-glow">
          {icon}
        </div>
      )}
      <h3 className="font-display text-xl font-semibold text-[var(--ink)]">{title}</h3>
      <p className="mt-2 max-w-md text-sm leading-relaxed text-[var(--ink-secondary)]">{detail}</p>
      {action && <div className="mt-5 animate-fade-in">{action}</div>}
    </div>
  );
}
