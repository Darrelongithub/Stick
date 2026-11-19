import React, { useCallback, useEffect, useRef, useState } from 'react';
import {
  ArrowRight,
  Brain,
  CheckCircle2,
  ChevronRight,
  CircleDot,
  CircleHelp,
  Clock3,
  Compass,
  Flame,
  GraduationCap,
  MousePointer2,
  EyeOff,
  Play,
  RefreshCw,
  Server,
  Sparkles,
  Target,
  TrendingUp,
  Upload,
} from 'lucide-react';
import type { LearningPlanResponse } from '../../shared/types';
import { api } from '../lib/api';
import {
  cx,
  formatGameDate,
  MASTERY_META,
  MOTIF_LABELS,
  PHASE_LABELS,
  severityBadgeMeta,
  shortOpening,
} from '../lib/chessFormat';
import {
  EmptyState,
  Eyebrow,
  Pill,
  ProgressBar,
  ProgressRing,
  Spinner,
  StatTile,
  SurfaceCard,
} from './ui';

interface LearningPlanViewProps {
  /** Home already fetches the plan; pass it through to avoid a duplicate request. */
  initialPlan?: LearningPlanResponse | null;
  onPlanLoaded?: (plan: LearningPlanResponse) => void;
  onTrainMistake: (gameId: string, mistakeId: string) => void;
  onOpenVault: () => void;
  onOpenCoach: () => void;
  onOpenImport: () => void;
  onOpenTour: () => void;
  onRefreshOverview: () => void;
}

function formatEta(seconds: number | null): string {
  if (seconds === null) return 'calculating…';
  if (seconds < 60) return `${seconds}s`;
  const mins = Math.floor(seconds / 60);
  const secs = seconds % 60;
  return `${mins}m ${secs}s`;
}

function HowItTeaches() {
  const steps = [
    {
      icon: <EyeOffIcon />,
      title: 'Blind first',
      text: 'You see the position and your game move. Stockfish’s answer is never sent to the browser yet.',
    },
    {
      icon: <Target className="h-4 w-4" />,
      title: 'Fail to reveal',
      text: 'A wrong move gets feedback. Only the final failed attempt unlocks the best move and full line.',
    },
    {
      icon: <RefreshCw className="h-4 w-4" />,
      title: 'Recall until mastered',
      text: 'Missed positions come back first. Two clean blind recalls move a failed mistake to mastered.',
    },
  ];
  return (
    <div className="grid gap-3 md:grid-cols-3">
      {steps.map((step, idx) => (
        <div
          key={step.title}
          className="rounded-xl border border-[var(--line)] bg-[var(--surface)] p-4"
        >
          <div className="flex items-center gap-2">
            <div className="flex h-8 w-8 items-center justify-center rounded-lg border border-[var(--a)]/25 bg-[var(--a-soft)] text-[var(--a)]">
              {step.icon}
            </div>
            <span className="font-mono-tabular text-[10px] font-bold text-[var(--ink-muted)]">0{idx + 1}</span>
          </div>
          <p className="mt-3 text-sm font-semibold text-[var(--ink-soft)]">{step.title}</p>
          <p className="mt-1 text-[11px] leading-relaxed text-[var(--ink-muted)]">{step.text}</p>
        </div>
      ))}
    </div>
  );
}

function EyeOffIcon() {
  return (
    <svg viewBox="0 0 24 24" className="h-4 w-4" fill="none" stroke="currentColor" strokeWidth="1.8">
      <path d="M3 3l18 18" strokeLinecap="round" />
      <path d="M10.6 10.6a2 2 0 002.8 2.8" strokeLinecap="round" />
      <path d="M9.4 5.3A9.8 9.8 0 0112 5c5 0 9 4.5 9 7 0 .8-.5 1.9-1.4 3M6.2 6.7C3.9 8.2 3 10.3 3 12c0 2.5 4 7 9 7 1.4 0 2.7-.3 3.8-.9" strokeLinecap="round" />
    </svg>
  );
}

export const LearningPlanView: React.FC<LearningPlanViewProps> = ({
  initialPlan = null,
  onPlanLoaded,
  onTrainMistake,
  onOpenVault,
  onOpenCoach,
  onOpenImport,
  onOpenTour,
  onRefreshOverview,
}) => {
  const [plan, setPlan] = useState<LearningPlanResponse | null>(initialPlan);
  const [loading, setLoading] = useState(!initialPlan);
  const [error, setError] = useState<string | null>(null);
  const [starting, setStarting] = useState(false);
  const previousRunning = useRef(initialPlan?.analyzeAll.running ?? false);
  const seededPlanAt = useRef<string | null>(initialPlan?.generatedAt ?? null);
  const refreshRef = useRef(onRefreshOverview);
  const planLoadedRef = useRef(onPlanLoaded);
  planLoadedRef.current = onPlanLoaded;
  const loadRequestRef = useRef(0);
  useEffect(() => () => { loadRequestRef.current++; }, []);

  useEffect(() => {
    refreshRef.current = onRefreshOverview;
  }, [onRefreshOverview]);

  const load = useCallback(async () => {
    const request = ++loadRequestRef.current;
    try {
      const data = await api.learningPlan();
      if (request !== loadRequestRef.current) return;
      setPlan(data);
      planLoadedRef.current?.(data);
      setError(null);
      if (previousRunning.current && !data.analyzeAll.running) {
        refreshRef.current();
      }
      previousRunning.current = data.analyzeAll.running;
    } catch (err) {
      if (request === loadRequestRef.current) setError(err instanceof Error ? err.message : 'Could not load your learning plan.');
    } finally {
      if (request === loadRequestRef.current) setLoading(false);
    }
  }, []);

  // Home passes its already-loaded plan. Only the initial standalone case
  // fetches; polling exists solely while a full-archive scan is running.
  useEffect(() => {
    if (initialPlan && seededPlanAt.current !== initialPlan.generatedAt) {
      seededPlanAt.current = initialPlan.generatedAt;
      loadRequestRef.current++;
      previousRunning.current = initialPlan.analyzeAll.running;
      setPlan(initialPlan);
      setLoading(false);
      return;
    }
    if (!initialPlan && !plan && loading && !error) void load();
  }, [initialPlan, load, plan, loading, error]);

  useEffect(() => {
    if (!plan?.analyzeAll.running) return;
    let cancelled = false;
    let timer: number;
    const poll = async () => {
      await load();
      if (!cancelled) timer = window.setTimeout(poll, 4000);
    };
    timer = window.setTimeout(poll, 4000);
    return () => { cancelled = true; window.clearTimeout(timer); };
  }, [plan?.analyzeAll.running, load]);

  const startFullAnalysis = async () => {
    setStarting(true);
    setError(null);
    try {
      const response = await api.startAnalyzeAll();
      previousRunning.current = response.status.running;
      await load();
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Could not start full-archive analysis.');
    } finally {
      setStarting(false);
    }
  };

  if (loading && !plan) {
    return (
      <div className="flex min-h-[55vh] items-center justify-center gap-3 text-sm text-[var(--ink-muted)]">
        <Spinner className="text-[var(--a)]" /> Building your Stockfish curriculum…
      </div>
    );
  }

  if (!plan) {
    return (
      <EmptyState
        icon={<Brain className="h-6 w-6" />}
        title="Learning plan unavailable"
        detail={error ?? 'Start the chess server again to rebuild your curriculum.'}
        action={<button type="button" onClick={() => { setLoading(true); void load(); }} className="rounded-lg bg-[var(--a)] px-4 py-2.5 text-xs font-bold text-[#0a0714]">Retry</button>}
      />
    );
  }

  const job = plan.analyzeAll;
  const totalDrillable = plan.totalSupportedGames + plan.totalCustomGames;
  const allAnalyzed = totalDrillable > 0 && plan.analyzedGames >= totalDrillable;
  const masteryPct = plan.totalMistakes > 0 ? (plan.masteredCount / plan.totalMistakes) * 100 : 0;
  const firstDue = plan.recommendedDrills[0];
  const howToSteps = [
    {
      number: '01',
      title: 'Pick a drill',
      detail: 'Start Here ranks your next blind mistake.',
      icon: <Compass className="h-4 w-4" />,
    },
    {
      number: '02',
      title: 'Move a piece',
      detail: 'Click a piece then a square, or drag it.',
      icon: <MousePointer2 className="h-4 w-4" />,
    },
    {
      number: '03',
      title: 'Fail, then learn',
      detail: 'The answer appears only after your final failed try.',
      icon: <EyeOff className="h-4 w-4" />,
    },
    {
      number: '04',
      title: 'Add a game',
      detail: 'Paste a PGN any time; Stockfish runs locally.',
      icon: <Upload className="h-4 w-4" />,
    },
  ];

  return (
    <div className="mx-auto max-w-[1280px] space-y-5 view-shell">
      <section className="premium-card relative overflow-hidden rounded-3xl border border-[var(--line)] p-6 animate-fade-up sm:p-8">
        <div className="absolute inset-x-0 top-0 h-[3px] bg-gradient-to-r from-[var(--a-deep)] via-[var(--a2)] to-[var(--a-deep)]" />
        <div className="pointer-events-none absolute -right-24 -top-28 h-80 w-80 rounded-full bg-[var(--a)]/[0.07] blur-3xl" />
        <div className="pointer-events-none absolute -bottom-32 left-1/3 h-72 w-72 rounded-full bg-[var(--cool)]/[0.05] blur-3xl" />
        <div className="relative flex flex-wrap items-start justify-between gap-5">
          <div className="max-w-2xl">
            <div className="flex items-center gap-2">
              <span className="h-px w-6 bg-[var(--a)]" />
              <Eyebrow>Your complete local curriculum</Eyebrow>
            </div>
            <h1 className="mt-2 font-display text-3xl font-semibold leading-tight text-[var(--ink)] sm:text-4xl">
              What you’re supposed to learn, in the right order.
            </h1>
            <p className="mt-3 text-sm leading-relaxed text-[var(--ink-secondary)]">
              All <span className="font-semibold text-[var(--a)]">{plan.totalArchiveGames.toLocaleString()} games</span> from{' '}
              <code className="rounded bg-[var(--surface)] px-1.5 py-0.5 font-mono-tabular text-[11px] text-[var(--a)]">darrelnxt-2026-.zip</code>{' '}
              are loaded. {plan.totalSupportedGames.toLocaleString()} standard-rules games are engine-drillable;{' '}
              {plan.totalChess960Games} Chess960 games are listed but not drilled. Chess knowledge never comes from an external API; Gemini only selects a topic; the coach uses local Stockfish knowledge.
            </p>
          </div>
          <div className="flex flex-col items-end gap-2">
            <button
              type="button"
              onClick={onOpenTour}
              className="inline-flex items-center gap-1.5 rounded-full border border-[var(--a)]/25 bg-[var(--a-soft)] px-3 py-1.5 text-[10px] font-bold uppercase tracking-[0.14em] text-[var(--a)] transition hover:bg-[var(--a-soft)] tap-scale"
              title="Replay the guided tour"
            >
              <CircleHelp className="h-3.5 w-3.5" /> How to use · 60 sec
            </button>
            <div className="flex items-center gap-2 rounded-full border border-[var(--cool)]/25 bg-[var(--cool-bg)] px-3 py-1.5 text-[10px] font-bold uppercase tracking-[0.14em] text-[var(--cool)]">
              <Server className="h-3.5 w-3.5" /> Stockfish 18 · local
            </div>
            {allAnalyzed && (
              <div className="flex items-center gap-1.5 rounded-full border border-[var(--a)]/25 bg-[var(--a-soft)] px-3 py-1.5 text-[10px] font-bold uppercase tracking-[0.14em] text-[var(--a)]">
                <CheckCircle2 className="h-3.5 w-3.5" /> All drillable games analyzed
              </div>
            )}
          </div>
        </div>

        <div className="relative mt-6 grid gap-3 sm:grid-cols-2 xl:grid-cols-5">
          <StatTile label="Games analyzed" value={`${plan.analyzedGames.toLocaleString()}/${totalDrillable.toLocaleString()}`} sub={`${plan.totalCustomGames} pasted PGNs`} icon={<Brain className="h-4 w-4" />} />
          <StatTile label="Verified mistakes" value={plan.totalMistakes.toLocaleString()} sub={`${plan.counts.bySeverity.blunder} blunders`} icon={<Flame className="h-4 w-4" />} accent="#ff6b57" />
          <StatTile label="Due now" value={plan.dueCount.toLocaleString()} sub="Needs review → learning → unseen" icon={<Target className="h-4 w-4" />} accent="#ffb340" />
          <StatTile label="Mastered" value={plan.masteredCount.toLocaleString()} sub={`${Math.round(masteryPct)}% of discovered`} icon={<GraduationCap className="h-4 w-4" />} accent="#4cc9f0" />
          <StatTile label="First-try recall" value={`${plan.firstTrySolveRate}%`} sub="Blind solves only" icon={<TrendingUp className="h-4 w-4" />} accent="#4cc9f0" />
        </div>

        <div className="relative mt-5 flex flex-wrap gap-2">
          {firstDue && (
            <button
              type="button"
              data-tour="start-training"
              onClick={() => onTrainMistake(firstDue.gameId, firstDue.mistakeId)}
              className="inline-flex items-center gap-2 rounded-xl bg-[var(--a)] px-4 py-3 text-sm font-bold text-[#0a0714] transition hover:bg-[var(--a-hover)] hover-lift tap-scale animate-ring-glow"
            >
              <Play className="h-4 w-4" /> Train first due mistake
            </button>
          )}
          <button
            type="button"
            onClick={onOpenVault}
            className="inline-flex items-center gap-2 rounded-xl border border-[var(--line)] bg-[var(--surface)]/70 px-4 py-3 text-sm font-semibold text-[var(--ink-soft)] transition hover:border-[var(--a)]/45 hover:bg-[var(--a-soft)] hover:text-[var(--a)] hover-lift tap-scale"
          >
            Open Mistake Vault <ChevronRight className="h-4 w-4" />
          </button>
          <button
            type="button"
            onClick={onOpenCoach}
            className="inline-flex items-center gap-2 rounded-xl border border-[var(--line)] bg-[var(--surface)]/70 px-4 py-3 text-sm font-semibold text-[var(--ink-soft)] transition hover:border-[var(--a)]/45 hover:bg-[var(--a-soft)] hover:text-[var(--a)] hover-lift tap-scale"
          >
            Game coach
          </button>
          <button
            type="button"
            onClick={onOpenImport}
            className="inline-flex items-center gap-2 rounded-xl border border-[var(--line)] bg-[var(--surface)]/70 px-4 py-3 text-sm font-semibold text-[var(--ink-soft)] transition hover:border-[var(--a)]/45 hover:bg-[var(--a-soft)] hover:text-[var(--a)] hover-lift tap-scale"
          >
            <Upload className="h-4 w-4" /> Paste PGN
          </button>
        </div>

        <div data-tour="quick-guide" className="relative mt-5 grid gap-2 rounded-2xl border border-[var(--line)] bg-[var(--surface)] p-2 sm:grid-cols-2 xl:grid-cols-4">
          {howToSteps.map((step, idx) => (
            <div
              key={step.number}
              className="flex items-center gap-3 rounded-xl border border-transparent px-3 py-2.5 transition-colors duration-200 hover:border-[var(--a)]/20 hover:bg-[var(--surface)] animate-fade-up"
              style={{ animationDelay: `${120 + idx * 70}ms` }}
            >
              <div className="flex h-8 w-8 shrink-0 items-center justify-center rounded-lg border border-[var(--a)]/25 bg-[var(--a-soft)] text-[var(--a)]">
                {step.icon}
              </div>
              <div className="min-w-0">
                <p className="text-[9px] font-bold uppercase tracking-[0.18em] text-[var(--ink-muted)]">
                  Step {step.number}
                </p>
                <p className="text-xs font-semibold text-[var(--ink)]">{step.title}</p>
                <p className="mt-0.5 text-[10px] leading-snug text-[var(--ink-secondary)]">{step.detail}</p>
              </div>
            </div>
          ))}
        </div>
      </section>

      {error && (
        <div className="rounded-xl border border-[var(--warm)]/30 bg-[var(--warm-bg)] px-4 py-3 text-xs text-[var(--warm-soft)]">
          {error}
        </div>
      )}

      {(job.running || !allAnalyzed) && (
        <SurfaceCard className="p-5">
          <div className="flex flex-wrap items-start justify-between gap-4">
            <div>
              <Eyebrow>Full-archive engine scan</Eyebrow>
              <h2 className="mt-1 font-display text-xl font-semibold text-[var(--ink)]">
                {job.running ? 'Stockfish is analyzing every supported game' : 'Analyze the rest of your archive'}
              </h2>
              <p className="mt-1 max-w-2xl text-xs leading-relaxed text-[var(--ink-muted)]">
                {job.running
                  ? job.message
                  : 'The app is already usable. Run the full local scan once to put every mistake into the cross-game learning queue.'}
              </p>
            </div>
            <button
              type="button"
              onClick={() => void startFullAnalysis()}
              disabled={job.running || starting}
              className="inline-flex items-center gap-2 rounded-lg bg-[var(--a)] px-4 py-2.5 text-xs font-bold text-[#0a0714] transition hover:bg-[var(--a-hover)] disabled:opacity-50"
            >
              {job.running ? <Spinner className="h-3.5 w-3.5" /> : <Brain className="h-3.5 w-3.5" />}
              {job.running ? 'Analyzing…' : allAnalyzed ? 'Re-scan cache' : 'Analyze all games'}
            </button>
          </div>

          {job.running && (
            <div className="mt-4 rounded-xl border border-[var(--line)] bg-[var(--surface)] p-3">
              <div className="mb-2 flex flex-wrap items-center justify-between gap-2 text-xs">
                <span className="font-semibold text-[var(--ink-soft)]">{job.message}</span>
                <span className="font-mono-tabular font-bold text-[var(--a)]">{job.percent}%</span>
              </div>
              <ProgressBar value={job.percent} tone="bronze" />
              <div className="mt-2 flex flex-wrap gap-x-4 gap-y-1 font-mono-tabular text-[10px] text-[var(--ink-muted)]">
                <span>{job.processed}/{job.total} games</span>
                <span>{job.analyzed} newly analyzed</span>
                <span>{job.totalMistakes.toLocaleString()} mistakes found</span>
                <span className="flex items-center gap-1"><Clock3 className="h-3 w-3" /> ETA {formatEta(job.etaSeconds)}</span>
                {job.failed > 0 && <span className="text-[var(--warm-soft)]">{job.failed} failed</span>}
              </div>
            </div>
          )}
        </SurfaceCard>
      )}

      <div className="grid items-start gap-5 xl:grid-cols-[minmax(0,1.65fr)_minmax(300px,0.8fr)]">
        <SurfaceCard className="overflow-hidden">
          <div className="flex flex-wrap items-center justify-between gap-2 border-b border-[var(--line)] px-4 py-3">
            <div>
              <Eyebrow>Start here · blind drills</Eyebrow>
              <h2 className="mt-1 font-display text-xl font-semibold text-[var(--ink)]">
                Your next {Math.min(12, plan.recommendedDrills.length)} positions
              </h2>
            </div>
            <Pill>{plan.dueCount.toLocaleString()} due</Pill>
          </div>

          {plan.recommendedDrills.length === 0 ? (
            <div className="p-4">
              <EmptyState
                icon={<Sparkles className="h-6 w-6" />}
                title={plan.totalMistakes > 0 ? 'All discovered drills mastered' : 'No drills yet'}
                detail={plan.totalMistakes > 0 ? 'There are no positions due right now. You can revisit mastered drills in the vault.' : 'Analyze a game to turn Stockfish-verified mistakes into blind challenges.'}
                action={plan.totalMistakes > 0 ? (
                  <button type="button" onClick={onOpenVault} className="rounded-lg bg-[var(--a)] px-4 py-2.5 text-xs font-bold text-[#0a0714]">Open vault</button>
                ) : (
                  <button type="button" onClick={onOpenCoach} className="rounded-lg bg-[var(--a)] px-4 py-2.5 text-xs font-bold text-[#0a0714]">Choose a game</button>
                )}
              />
            </div>
          ) : (
            <div className="divide-y divide-[var(--line-strong)]/[0.06]">
              {plan.recommendedDrills.slice(0, 12).map((drill) => {
                const severity = severityBadgeMeta(drill.severity);
                const mastery = MASTERY_META[drill.mastery.status];
                return (
                  <div
                    key={drill.mistakeId}
                    className="flex flex-wrap items-center gap-3 px-4 py-3 transition hover:bg-[var(--surface)]"
                  >
                    <div className="flex h-9 w-9 shrink-0 items-center justify-center rounded-lg border border-[var(--a)]/25 bg-[var(--a-soft)] font-mono-tabular text-xs font-bold text-[var(--a)]">
                      {String(drill.rank).padStart(2, '0')}
                    </div>
                    <div className="min-w-[210px] flex-1">
                      <div className="flex flex-wrap items-center gap-2">
                        <p className="text-sm font-semibold text-[var(--ink-soft)]">
                          Move {drill.moveNumber} · <span className="font-mono-tabular text-[var(--warm-soft)]">{drill.playedMoveSan}</span>
                        </p>
                        <Pill className={severity.pillClass}>{severity.glyph} {severity.label}</Pill>
                        <Pill className={mastery.pillClass}>{mastery.label}</Pill>
                      </div>
                      <p className="mt-1 truncate text-[11px] text-[var(--ink-secondary)]">
                        vs {drill.opponent} · {formatGameDate(drill.gameDate)} · {shortOpening(drill.openingName, 38)}
                      </p>
                    </div>
                    <div className="min-w-[170px] flex-1">
                      <p className="text-[11px] font-semibold text-[var(--ink-soft)]">{drill.focus}</p>
                      <p className="mt-0.5 text-[10px] text-[var(--ink-muted)]">{drill.reason}</p>
                    </div>
                    <div className="flex shrink-0 items-center gap-2">
                      <span className="font-mono-tabular text-[11px] font-bold text-[var(--warm-soft)]">
                        −{Math.round(drill.winProbLost * 100)}%
                      </span>
                      <button
                        type="button"
                        onClick={() => onTrainMistake(drill.gameId, drill.mistakeId)}
                        className="inline-flex items-center gap-1 rounded-lg border border-[var(--a)]/30 bg-[var(--a-soft)] px-2.5 py-2 text-[11px] font-bold text-[var(--a)] transition hover:bg-[var(--a)]/18"
                      >
                        Train <ArrowRight className="h-3 w-3" />
                      </button>
                    </div>
                  </div>
                );
              })}
            </div>
          )}
        </SurfaceCard>

        <div className="space-y-5">
          <SurfaceCard className="p-4">
            <div className="flex items-center gap-3">
              <ProgressRing value={masteryPct} size={72} label={`${Math.round(masteryPct)}%`} subLabel="mastered" color="#4cc9f0" />
              <div>
                <Eyebrow>Mastery mix</Eyebrow>
                <p className="mt-1 font-display text-xl font-semibold text-[var(--ink)]">
                  {plan.masteredCount.toLocaleString()} / {plan.totalMistakes.toLocaleString()}
                </p>
                <p className="mt-0.5 text-[11px] text-[var(--ink-secondary)]">clean blind recalls</p>
              </div>
            </div>
            <div className="mt-4 space-y-2">
              {(Object.keys(MASTERY_META) as Array<keyof typeof MASTERY_META>).map((status) => {
                const meta = MASTERY_META[status];
                const value = plan.counts.byMastery[status];
                return (
                  <div key={status}>
                    <div className="mb-0.5 flex justify-between text-[10px]">
                      <span className="text-[var(--ink-secondary)]">{meta.label}</span>
                      <span className="font-mono-tabular text-[var(--ink-muted)]">{value}</span>
                    </div>
                    <ProgressBar
                      value={plan.totalMistakes ? (value / plan.totalMistakes) * 100 : 0}
                      tone={status === 'mastered' ? 'green' : status === 'needs_review' ? 'red' : 'bronze'}
                    />
                  </div>
                );
              })}
            </div>
          </SurfaceCard>

          <SurfaceCard className="p-4">
            <Eyebrow>Weakness profile</Eyebrow>
            <div className="mt-3 space-y-2.5">
              {plan.counts.byMotif.slice(0, 6).map((row) => (
                <div key={row.motif}>
                  <div className="mb-1 flex items-center justify-between gap-2 text-[10px]">
                    <span className="truncate text-[var(--ink-secondary)]">{row.label}</span>
                    <span className="font-mono-tabular text-[var(--ink-muted)]">
                      {row.mastered}/{row.count}
                    </span>
                  </div>
                  <ProgressBar value={row.count ? (1 - row.mastered / row.count) * 100 : 0} tone="red" />
                </div>
              ))}
              {plan.counts.byMotif.length === 0 && (
                <p className="py-6 text-center text-[11px] text-[var(--ink-muted)]">Analyze games to reveal patterns.</p>
              )}
            </div>
            <div className="mt-4 border-t border-[var(--line)] pt-3">
              <p className="mb-2 text-[9px] font-semibold uppercase tracking-[0.14em] text-[var(--ink-muted)]">By phase</p>
              <div className="flex flex-wrap gap-1.5">
                {(Object.keys(PHASE_LABELS) as Array<keyof typeof PHASE_LABELS>).map((phase) => (
                  <Pill key={phase}>
                    <CircleDot className="h-3 w-3" /> {PHASE_LABELS[phase]} {plan.counts.byPhase[phase]}
                  </Pill>
                ))}
              </div>
            </div>
          </SurfaceCard>

          <SurfaceCard className="p-4">
            <div className="flex items-center gap-2">
              <Sparkles className="h-4 w-4 text-[var(--a)]" />
              <h3 className="font-display text-lg font-semibold text-[var(--ink)]">Gemini is only the coach</h3>
            </div>
            <p className="mt-2 text-[12px] leading-relaxed text-[var(--ink-secondary)]">
              <span className="font-semibold text-[var(--a)]">Stockfish stays the source of truth.</span> Set{' '}
              <code className="rounded bg-[var(--surface)] px-1 py-0.5 font-mono-tabular text-[10px]">GEMINI_API_KEY</code> in{' '}
              <code className="rounded bg-[var(--surface)] px-1 py-0.5 font-mono-tabular text-[10px]">chess-improver/.env</code> or the server environment to let Gemini select a topic for a local, spoiler-free response.
              The key never reaches the browser; without it, a deterministic local coach answers instead.
            </p>
            <div className="mt-3 flex items-center gap-1.5 rounded-lg border border-[var(--a)]/20 bg-[var(--a-soft)] px-2.5 py-2 text-[10px] font-semibold text-[var(--a2)]">
              <CheckCircle2 className="h-3.5 w-3.5" /> Best moves stay server-side until a drill is failed.
            </div>
          </SurfaceCard>
        </div>
      </div>

      <SurfaceCard className="p-5">
        <div className="mb-3 flex flex-wrap items-center justify-between gap-2">
          <div>
            <Eyebrow>Active recall loop</Eyebrow>
            <h2 className="mt-1 font-display text-xl font-semibold text-[var(--ink)]">How it teaches you</h2>
          </div>
          <Pill><Sparkles className="h-3 w-3" /> Spoiler-safe by design</Pill>
        </div>
        <HowItTeaches />
      </SurfaceCard>
    </div>
  );
};
