import React, { useEffect, useMemo, useState } from 'react';
import {
  ArrowRight,
  BarChart3,
  BookOpen,
  Brain,
  CheckCircle2,
  ChevronLeft,
  ChevronRight,
  Clock,
  Flame,
  Library,
  RefreshCw,
  Search,
  Sparkles,
  Target,
  TrendingUp,
  Trophy,
  Upload,
} from 'lucide-react';
import type { ArchiveOverviewResponse, GameSummary, TimeClass } from '../../shared/types';
import { api } from '../lib/api';
import type { GameListResponse } from '../lib/api';
import { cx, formatGameDate, shortOpening } from '../lib/chessFormat';
import {
  EmptyState,
  Eyebrow,
  Pill,
  ProgressBar,
  ProgressRing,
  SegmentedControl,
  Spinner,
  StatTile,
  SurfaceCard,
} from './ui';

interface LibraryInsightsViewProps {
  overview: ArchiveOverviewResponse | null;
  onOpenGame: (id: string) => void;
  onOpenImport: () => void;
  onRefreshOverview: () => void;
}

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

function ResultPill({ game }: { game: GameSummary }) {
  const meta =
    game.userOutcome === 'win'
      ? { label: 'Win', cls: 'border-[var(--cool)]/30 bg-[var(--cool-bg)] text-[var(--cool)]' }
      : game.userOutcome === 'loss'
        ? { label: 'Loss', cls: 'border-[var(--warm)]/30 bg-[var(--warm)]/10 text-[var(--warm-soft)]' }
        : { label: 'Draw', cls: 'border-[var(--amber)]/30 bg-[var(--amber)]/10 text-[var(--amber)]' };
  return <Pill className={meta.cls}>{meta.label} · {game.result}</Pill>;
}

function GameCard({ game, onOpen }: { game: GameSummary; onOpen: () => void }) {
  const masteredPct =
    game.totalMistakesCount && game.totalMistakesCount > 0
      ? ((game.masteredMistakesCount ?? 0) / game.totalMistakesCount) * 100
      : 0;
  const unsupported = game.analyzable === false;

  return (
    <article className="flex flex-col rounded-2xl border border-[var(--line)] bg-[var(--surface)]/75 p-4 animate-fade-up hover-lift hover:border-[var(--a)]/30 hover:bg-[var(--surface)]">
      <div className="flex items-start justify-between gap-3">
        <div className="min-w-0">
          <p className="truncate font-display text-base font-semibold text-[var(--ink)]">
            {game.white} <span className="text-[var(--ink-muted)]">vs</span> {game.black}
          </p>
          <p className="mt-0.5 truncate text-[11px] text-[var(--ink-secondary)]" title={game.openingName}>
            {shortOpening(game.openingName, 44)}
          </p>
        </div>
        <ResultPill game={game} />
      </div>

      <div className="mt-3 flex flex-wrap gap-1.5">
        <Pill>
          {game.userColor === 'w' ? '⚪' : '⚫'} You were {game.userColor === 'w' ? 'White' : 'Black'}
        </Pill>
        <Pill><Clock className="h-3 w-3" /> {game.timeClass}</Pill>
        {game.userElo && <Pill>Elo {game.userElo}</Pill>}
        <Pill>{formatGameDate(game.date)}</Pill>
        {game.source === 'custom' && (
          <Pill className="border-[var(--cool)]/25 bg-[var(--cool-bg)] text-[var(--cool)]">Pasted PGN</Pill>
        )}
        {unsupported && (
          <Pill className="border-[var(--a)]/25 bg-[var(--a)]/[0.07] text-[var(--a-deep)]">
            {game.variant ?? 'Variant'} · listed only
          </Pill>
        )}
      </div>

      <div className="mt-3 grid grid-cols-4 gap-2">
        <div className="rounded-lg border border-[var(--line)] bg-[var(--surface)] p-2 text-center">
          <p className="text-[8px] uppercase tracking-wider text-[var(--ink-muted)]">Moves</p>
          <p className="mt-0.5 font-mono-tabular text-xs font-bold text-[var(--ink-soft)]">{game.moveCount}</p>
        </div>
        <div className="rounded-lg border border-[var(--line)] bg-[var(--surface)] p-2 text-center">
          <p className="text-[8px] uppercase tracking-wider text-[var(--ink-muted)]">Accuracy</p>
          <p className="mt-0.5 font-mono-tabular text-xs font-bold text-[var(--ink-soft)]">
            {game.accuracy != null ? `${game.accuracy.toFixed(1)}%` : '—'}
          </p>
        </div>
        <div className="rounded-lg border border-[var(--warm)]/15 bg-[var(--warm)]/[0.04] p-2 text-center">
          <p className="text-[8px] uppercase tracking-wider text-[var(--a-deep)]">Mistakes</p>
          <p className="mt-0.5 font-mono-tabular text-xs font-bold text-[var(--warm-soft)]">
            {game.totalMistakesCount ?? '—'}
          </p>
        </div>
        <div className="rounded-lg border border-[var(--cool)]/15 bg-[var(--cool)]/[0.04] p-2 text-center">
          <p className="text-[8px] uppercase tracking-wider text-[var(--cool-soft)]">Mastered</p>
          <p className="mt-0.5 font-mono-tabular text-xs font-bold text-[var(--cool)]">
            {game.masteredMistakesCount ?? 0}
          </p>
        </div>
      </div>

      {game.analyzed && game.totalMistakesCount != null && (
        <div className="mt-3">
          <div className="mb-1 flex items-center justify-between text-[9px] text-[var(--ink-muted)]">
            <span>Mistake mastery</span>
            <span>{Math.round(masteredPct)}%</span>
          </div>
          <ProgressBar value={masteredPct} tone={masteredPct >= 100 ? 'green' : 'bronze'} />
        </div>
      )}

      <button
        type="button"
        onClick={onOpen}
        disabled={unsupported}
        className={cx(
          'mt-4 inline-flex w-full items-center justify-center gap-1.5 rounded-lg px-3 py-2.5 text-xs font-bold transition',
          unsupported
            ? 'cursor-not-allowed border border-[var(--line)] bg-[var(--surface-deep)]/[0.03] text-[var(--ink-muted)]'
            : game.analyzed
              ? 'bg-[var(--a)] text-[#0a0714] hover:bg-[var(--a-hover)]'
              : 'border border-[var(--a)]/35 bg-[var(--a-soft)] text-[var(--a)] hover:bg-[var(--a)]/15'
        )}
        title={
          unsupported
            ? 'Chess960 castling is not replayable by the bundled standard chess.js engine'
            : undefined
        }
      >
        {unsupported ? (
          <><BookOpen className="h-3.5 w-3.5" /> Listed only · Chess960</>
        ) : game.analyzed ? (
          <><Target className="h-3.5 w-3.5" /> Train mistakes</>
        ) : (
          <><Brain className="h-3.5 w-3.5" /> Analyze with Stockfish</>
        )}
        {!unsupported && <ArrowRight className="h-3.5 w-3.5" />}
      </button>
    </article>
  );
}

function RatingChart({ overview }: { overview: ArchiveOverviewResponse }) {
  const timeline = overview.eloTimeline;
  const series = [
    { key: 'rapidElo' as const, label: 'Rapid', color: '#8b7cff' },
    { key: 'blitzElo' as const, label: 'Blitz', color: '#4cc9f0' },
    { key: 'bulletElo' as const, label: 'Bullet', color: '#8b7cff' },
  ];

  const allValues = timeline.flatMap((row) =>
    series.map((s) => row[s.key]).filter((v): v is number => typeof v === 'number')
  );
  const min = allValues.length ? Math.min(...allValues) - 60 : 0;
  const max = allValues.length ? Math.max(...allValues) + 60 : 1200;
  const range = Math.max(1, max - min);
  const left = 42;
  const right = 690;
  const top = 18;
  const bottom = 155;

  const xFor = (idx: number) =>
    timeline.length <= 1 ? left : left + (idx / (timeline.length - 1)) * (right - left);
  const yFor = (value: number) => bottom - ((value - min) / range) * (bottom - top);

  const paths = series.map((s) => {
    let path = '';
    timeline.forEach((row, idx) => {
      const value = row[s.key];
      if (value === null) return;
      path += `${path ? ' L' : 'M'} ${xFor(idx).toFixed(1)} ${yFor(value).toFixed(1)}`;
    });
    return { ...s, path };
  });

  return (
    <SurfaceCard className="p-4">
      <div className="mb-2 flex flex-wrap items-start justify-between gap-2">
        <div>
          <Eyebrow>Rating trajectory</Eyebrow>
          <h3 className="mt-1 font-display text-lg font-semibold text-[var(--ink)]">
            Ten months of play
          </h3>
        </div>
        <div className="flex flex-wrap gap-2">
          {series.map((s) => (
            <span key={s.key} className="flex items-center gap-1.5 text-[10px] text-[var(--ink-muted)]">
              <span className="h-2 w-2 rounded-full" style={{ backgroundColor: s.color }} /> {s.label}
            </span>
          ))}
        </div>
      </div>

      {timeline.length === 0 ? (
        <p className="py-12 text-center text-xs text-[var(--ink-muted)]">No rating timeline available.</p>
      ) : (
        <svg viewBox="0 0 720 185" className="h-52 w-full" role="img" aria-label="Rating trajectory by month">
          {[0, 0.25, 0.5, 0.75, 1].map((ratio) => {
            const y = bottom - ratio * (bottom - top);
            const value = Math.round(min + ratio * range);
            return (
              <g key={ratio}>
                <line x1={left} y1={y} x2={right} y2={y} stroke="rgba(255, 255, 255, 0.07)" />
                <text x="5" y={y + 3} fill="#807b92" fontSize="9" fontFamily="var(--font-mono)">
                  {value}
                </text>
              </g>
            );
          })}
          {paths.map((p) => (
            <path key={p.key} d={p.path} fill="none" stroke={p.color} strokeWidth="2.6" strokeLinecap="round" strokeLinejoin="round" />
          ))}
          {timeline.map((row, idx) => {
            if (idx % 2 !== 0 && idx !== timeline.length - 1) return null;
            return (
              <text
                key={row.month}
                x={xFor(idx)}
                y="176"
                textAnchor="middle"
                fill="#8f8ba0"
                fontSize="9"
                fontFamily="var(--font-mono)"
              >
                {row.month.slice(5)}
              </text>
            );
          })}
        </svg>
      )}
    </SurfaceCard>
  );
}

function InsightsView({
  overview,
  onOpenImport,
}: {
  overview: ArchiveOverviewResponse | null;
  onOpenImport: () => void;
}) {
  if (!overview) {
    return (
      <div className="flex justify-center py-20">
        <Spinner className="text-[var(--a)]" /> <span className="ml-2 text-sm text-[var(--ink-muted)]">Loading insights…</span>
      </div>
    );
  }

  const totalGames = overview.totalArchiveGames + overview.totalCustomGames;
  const winRate = totalGames ? (overview.wins / totalGames) * 100 : 0;
  const stats = overview.mistakeStats;
  const phaseTotal = Math.max(1, stats.byPhase.opening + stats.byPhase.middlegame + stats.byPhase.endgame);
  const timeClasses: TimeClass[] = ['rapid', 'blitz', 'bullet', 'classical'];

  return (
    <div className="space-y-5">
      <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-5">
        <StatTile
          label="Archive games"
          value={overview.totalArchiveGames.toLocaleString()}
          sub={`${overview.totalSupportedGames.toLocaleString()} drillable · ${overview.totalChess960Games} Chess960 · ${overview.totalCustomGames} pasted`}
          icon={<Library className="h-4 w-4" />}
        />
        <StatTile label="Record" value={`${overview.wins}–${overview.losses}–${overview.draws}`} sub={`${winRate.toFixed(1)}% win rate`} icon={<Trophy className="h-4 w-4" />} accent="#4cc9f0" />
        <StatTile label="Analyzed" value={overview.analyzedGamesCount} sub="Stockfish-verified games" icon={<Brain className="h-4 w-4" />} accent="#4cc9f0" />
        <StatTile label="Mistakes found" value={stats.totalDiscovered} sub={`${stats.blunders} blunders · ${stats.mistakes} mistakes`} icon={<Flame className="h-4 w-4" />} accent="#ff6b57" />
        <StatTile label="First-try recall" value={`${stats.firstTrySolveRate}%`} sub={`${stats.mastered} mastered`} icon={<Target className="h-4 w-4" />} accent="#8b7cff" />
      </div>

      <div className="grid gap-5 xl:grid-cols-[minmax(0,1.45fr)_minmax(320px,0.8fr)]">
        <RatingChart overview={overview} />

        <SurfaceCard className="p-4">
          <Eyebrow>Mastery distribution</Eyebrow>
          <div className="mt-3 flex items-center gap-4">
            <ProgressRing
              value={stats.totalDiscovered ? (stats.mastered / stats.totalDiscovered) * 100 : 0}
              size={92}
              label={`${stats.mastered}`}
              subLabel="mastered"
              color="#4cc9f0"
            />
            <div className="min-w-0 flex-1 space-y-2">
              {[
                { label: 'Needs review', value: stats.needsReview, tone: 'red' as const, color: '#ff6b57' },
                { label: 'Learning', value: stats.learning, tone: 'bronze' as const, color: '#ffb340' },
                { label: 'Unseen', value: stats.unseen, tone: 'blue' as const, color: '#4cc9f0' },
                { label: 'Mastered', value: stats.mastered, tone: 'green' as const, color: '#4cc9f0' },
              ].map((row) => (
                <div key={row.label}>
                  <div className="mb-0.5 flex justify-between text-[10px]">
                    <span className="text-[var(--ink-secondary)]">{row.label}</span>
                    <span className="font-mono-tabular" style={{ color: row.color }}>{row.value}</span>
                  </div>
                  <ProgressBar value={stats.totalDiscovered ? (row.value / stats.totalDiscovered) * 100 : 0} tone={row.tone} />
                </div>
              ))}
            </div>
          </div>
          <button
            type="button"
            onClick={onOpenImport}
            className="mt-4 inline-flex w-full items-center justify-center gap-1.5 rounded-lg border border-[var(--a)]/25 bg-[var(--a-soft)] px-3 py-2.5 text-xs font-bold text-[var(--a)] transition hover:bg-[var(--a)]/15"
          >
            <Upload className="h-3.5 w-3.5" /> Add a new PGN
          </button>
        </SurfaceCard>
      </div>

      <div className="grid gap-5 lg:grid-cols-2">
        <SurfaceCard className="p-4">
          <div className="flex items-center justify-between">
            <Eyebrow>Most-played openings</Eyebrow>
            <BookOpen className="h-4 w-4 text-[var(--a)]" />
          </div>
          <div className="mt-4 space-y-3">
            {overview.topOpenings.map((opening, idx) => (
              <div key={opening.name}>
                <div className="mb-1 flex items-center justify-between gap-3 text-[11px]">
                  <span className="truncate text-[var(--ink-soft)]">
                    <span className="mr-2 font-mono-tabular text-[var(--ink-muted)]">{String(idx + 1).padStart(2, '0')}</span>
                    {shortOpening(opening.name, 46)}
                  </span>
                  <span className="shrink-0 font-mono-tabular text-[var(--ink-muted)]">
                    {opening.games} games · {opening.winRate}% W
                  </span>
                </div>
                <ProgressBar value={opening.winRate} tone={opening.winRate >= 50 ? 'green' : 'bronze'} />
              </div>
            ))}
          </div>
        </SurfaceCard>

        <SurfaceCard className="p-4">
          <div className="flex items-center justify-between">
            <Eyebrow>Weakness profile</Eyebrow>
            <BarChart3 className="h-4 w-4 text-[var(--warm)]" />
          </div>
          <div className="mt-4 space-y-2.5">
            {stats.byMotif.slice(0, 6).map((row) => (
              <div key={row.motif}>
                <div className="mb-1 flex items-center justify-between gap-3 text-[11px]">
                  <span className="truncate text-[var(--ink-soft)]">{row.label}</span>
                  <span className="font-mono-tabular text-[var(--ink-muted)]">
                    {row.mastered}/{row.count} mastered
                  </span>
                </div>
                <ProgressBar value={row.count ? (1 - row.mastered / row.count) * 100 : 0} tone="red" />
              </div>
            ))}
            {stats.byMotif.length === 0 && (
              <p className="py-8 text-center text-xs text-[var(--ink-muted)]">Analyze games to reveal recurring motifs.</p>
            )}
          </div>
          <div className="mt-4 border-t border-[var(--line)] pt-3">
            <p className="mb-2 text-[10px] font-semibold uppercase tracking-[0.14em] text-[var(--ink-muted)]">Mistakes by phase</p>
            <div className="flex h-3 overflow-hidden rounded-full bg-[var(--surface-soft)]">
              {(['opening', 'middlegame', 'endgame'] as const).map((phase, idx) => {
                const colors = ['#ffb340', '#ff6b57', '#4cc9f0'];
                return (
                  <div
                    key={phase}
                    style={{ width: `${(stats.byPhase[phase] / phaseTotal) * 100}%`, backgroundColor: colors[idx] }}
                    title={`${phase}: ${stats.byPhase[phase]}`}
                  />
                );
              })}
            </div>
            <div className="mt-2 flex justify-between text-[10px] text-[var(--ink-secondary)]">
              <span>Opening {stats.byPhase.opening}</span>
              <span>Middlegame {stats.byPhase.middlegame}</span>
              <span>Endgame {stats.byPhase.endgame}</span>
            </div>
          </div>
        </SurfaceCard>
      </div>

      <SurfaceCard className="p-4">
        <Eyebrow>Performance by time control</Eyebrow>
        <div className="mt-3 grid gap-3 sm:grid-cols-2 xl:grid-cols-4">
          {timeClasses.map((tc) => {
            const row = overview.byTimeClass[tc];
            const rate = row.games ? (row.wins / row.games) * 100 : 0;
            return (
              <div key={tc} className="rounded-xl border border-[var(--line)] bg-[var(--surface)] p-3">
                <div className="flex items-center justify-between">
                  <p className="text-xs font-bold capitalize text-[var(--ink-soft)]">{tc}</p>
                  <Pill>{row.games} games</Pill>
                </div>
                <p className="mt-2 font-display text-2xl font-semibold text-[var(--ink)]">{rate.toFixed(0)}%</p>
                <p className="mt-0.5 text-[10px] text-[var(--ink-secondary)]">
                  {row.wins}W · {row.losses}L · peak {row.peakElo ?? '—'}
                </p>
                <ProgressBar className="mt-2.5" value={rate} tone={rate >= 50 ? 'green' : 'red'} />
              </div>
            );
          })}
        </div>
      </SurfaceCard>
    </div>
  );
}

export const LibraryInsightsView: React.FC<LibraryInsightsViewProps> = ({
  overview,
  onOpenGame,
  onOpenImport,
  onRefreshOverview,
}) => {
  const [mode, setMode] = useState<'library' | 'insights'>('library');
  const [source, setSource] = useState('all');
  const [analyzed, setAnalyzed] = useState('all');
  const [timeClass, setTimeClass] = useState('all');
  const [outcome, setOutcome] = useState('all');
  const [color, setColor] = useState('all');
  const [month, setMonth] = useState('all');
  const [searchInput, setSearchInput] = useState('');
  const [debouncedSearch, setDebouncedSearch] = useState('');
  const [page, setPage] = useState(1);
  const [refreshKey, setRefreshKey] = useState(0);
  const [data, setData] = useState<GameListResponse>({ total: 0, page: 1, limit: 30, months: [], games: [] });
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    const timer = window.setTimeout(() => setDebouncedSearch(searchInput.trim()), 250);
    return () => window.clearTimeout(timer);
  }, [searchInput]);

  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    setError(null);
    api
      .games({
        source,
        analyzed,
        timeClass,
        outcome,
        color,
        month,
        search: debouncedSearch,
        page,
        limit: 30,
      })
      .then((result) => {
        if (!cancelled) setData(result);
      })
      .catch((err) => {
        if (!cancelled) setError(err instanceof Error ? err.message : 'Could not load game library.');
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [source, analyzed, timeClass, outcome, color, month, debouncedSearch, page, refreshKey]);

  const totalPages = Math.max(1, Math.ceil(data.total / data.limit));
  useEffect(() => {
    if (page > totalPages) setPage(1);
  }, [page, totalPages]);

  const setFilter = (setter: (value: string) => void, value: string) => {
    setter(value);
    setPage(1);
  };

  const refresh = () => {
    setRefreshKey((key) => key + 1);
    onRefreshOverview();
  };

  const monthOptions = useMemo(
    () => [
      { value: 'all', label: 'All months' },
      ...data.months.map((m) => ({ value: m, label: m })),
    ],
    [data.months]
  );

  return (
    <div className="mx-auto max-w-[1280px] space-y-5 view-shell">
      <header data-tour="library-overview" className="premium-card relative flex flex-wrap items-end justify-between gap-4 overflow-hidden rounded-2xl border border-[var(--line)] p-5 animate-fade-up">
        <div className="absolute inset-x-0 top-0 h-[3px] bg-gradient-to-r from-[var(--a-deep)] via-[var(--a2)] to-[var(--a-deep)]" />
        <div>
          <div className="flex items-center gap-2">
            <span className="h-px w-5 bg-[var(--a)]" />
            <Eyebrow>Your complete Chess.com archive</Eyebrow>
          </div>
          <h1 className="mt-1 font-display text-3xl font-semibold text-[var(--ink)] sm:text-4xl">
            Library &amp; Insights
          </h1>
          <p className="mt-1 max-w-2xl text-sm text-[var(--ink-muted)]">
            {overview
              ? `${overview.totalArchiveGames.toLocaleString()} games from darrelnxt-2026-.zip (${overview.totalSupportedGames.toLocaleString()} engine-drillable, ${overview.totalChess960Games} Chess960 listed), plus ${overview.totalCustomGames} pasted PGNs. Pick any supported game for a live Stockfish 18 scan.`
              : 'Loading your archive…'}
          </p>
        </div>
        <div className="flex flex-wrap items-center gap-2">
          <SegmentedControl<'library' | 'insights'>
            value={mode}
            onChange={setMode}
            options={[
              { value: 'library', label: 'Library' },
              { value: 'insights', label: 'Insights' },
            ]}
          />
          <button
            type="button"
            onClick={refresh}
            className="inline-flex h-9 items-center gap-1.5 rounded-lg border border-[var(--line)] bg-[var(--surface)]/70 px-3 text-xs font-semibold text-[var(--ink-soft)] transition hover:border-[var(--a)]/50 hover:bg-[var(--a-soft)] hover-lift tap-scale"
            title="Refresh archive and overview"
          >
            <RefreshCw className="h-3.5 w-3.5" /> Refresh
          </button>
          <button
            type="button"
            data-tour="library-pgn"
            onClick={onOpenImport}
            className="inline-flex items-center gap-1.5 rounded-lg bg-[var(--a)] px-3.5 py-2.5 text-xs font-bold text-[#0a0714] transition hover:bg-[var(--a-hover)] tap-scale"
          >
            <Upload className="h-3.5 w-3.5" /> Paste PGN
          </button>
        </div>
      </header>

      {mode === 'insights' ? (
        <InsightsView overview={overview} onOpenImport={onOpenImport} />
      ) : (
        <div className="grid items-start gap-5 lg:grid-cols-[270px_minmax(0,1fr)]">
          <aside className="space-y-4 lg:sticky lg:top-24">
            <SurfaceCard className="p-4">
              <div className="flex items-center gap-2">
                <Sparkles className="h-4 w-4 text-[var(--a)]" />
                <h2 className="font-display text-lg font-semibold text-[var(--ink)]">Refine archive</h2>
              </div>
              <p className="mt-1 text-[11px] text-[var(--ink-secondary)]">
                {overview ? `${overview.totalArchiveGames.toLocaleString()} games indexed from the ZIP; ${overview.totalChess960Games} Chess960 games are listed but not drilled.` : 'Loading archive details…'}
              </p>

              <div className="mt-4 space-y-2.5">
                <FilterSelect
                  label="Source"
                  value={source}
                  options={[
                    { value: 'all', label: 'Archive + pasted' },
                    { value: 'archive', label: 'ZIP archive' },
                    { value: 'custom', label: 'Pasted PGNs' },
                  ]}
                  onChange={(v) => setFilter(setSource, v)}
                />
                <FilterSelect
                  label="Analysis"
                  value={analyzed}
                  options={[
                    { value: 'all', label: 'All games' },
                    { value: 'true', label: 'Analyzed' },
                    { value: 'false', label: 'Not analyzed yet' },
                  ]}
                  onChange={(v) => setFilter(setAnalyzed, v)}
                />
                <FilterSelect
                  label="Time control"
                  value={timeClass}
                  options={[
                    { value: 'all', label: 'All time controls' },
                    { value: 'rapid', label: 'Rapid' },
                    { value: 'blitz', label: 'Blitz' },
                    { value: 'bullet', label: 'Bullet' },
                    { value: 'classical', label: 'Classical' },
                  ]}
                  onChange={(v) => setFilter(setTimeClass, v)}
                />
                <FilterSelect
                  label="Result"
                  value={outcome}
                  options={[
                    { value: 'all', label: 'All results' },
                    { value: 'win', label: 'Wins' },
                    { value: 'loss', label: 'Losses' },
                    { value: 'draw', label: 'Draws' },
                  ]}
                  onChange={(v) => setFilter(setOutcome, v)}
                />
                <FilterSelect
                  label="Your color"
                  value={color}
                  options={[
                    { value: 'all', label: 'Either color' },
                    { value: 'w', label: 'White' },
                    { value: 'b', label: 'Black' },
                  ]}
                  onChange={(v) => setFilter(setColor, v)}
                />
                <FilterSelect label="Month" value={month} options={monthOptions} onChange={(v) => setFilter(setMonth, v)} />
              </div>

              <button
                type="button"
                onClick={() => {
                  setSource('all');
                  setAnalyzed('all');
                  setTimeClass('all');
                  setOutcome('all');
                  setColor('all');
                  setMonth('all');
                  setSearchInput('');
                  setPage(1);
                }}
                className="mt-4 w-full rounded-lg border border-[var(--line)] px-3 py-2 text-[11px] font-semibold text-[var(--ink-muted)] transition hover:text-[var(--a)]"
              >
                Clear all filters
              </button>
            </SurfaceCard>

            <SurfaceCard className="p-4">
              <Eyebrow>Archive pulse</Eyebrow>
              <div className="mt-3 flex items-center gap-3">
                <ProgressRing
                  value={overview ? (overview.analyzedGamesCount / Math.max(1, overview.totalArchiveGames + overview.totalCustomGames)) * 100 : 0}
                  size={62}
                  label={String(overview?.analyzedGamesCount ?? 0)}
                  subLabel="scanned"
                  color="#8b7cff"
                />
                <div className="min-w-0">
                  <p className="font-display text-lg font-semibold text-[var(--ink)]">
                    {overview?.wins ?? 0}–{overview?.losses ?? 0}–{overview?.draws ?? 0}
                  </p>
                  <p className="mt-0.5 text-[10px] text-[var(--ink-secondary)]">Wins losses draws</p>
                </div>
              </div>
              <div className="mt-3 flex items-center gap-1.5 rounded-lg border border-[var(--cool)]/20 bg-[var(--cool-bg)] px-2.5 py-2 text-[10px] text-[var(--cool)]">
                <CheckCircle2 className="h-3.5 w-3.5" /> 14 recent games pre-analyzed for instant start
              </div>
            </SurfaceCard>
          </aside>

          <main className="min-w-0 space-y-4">
            <div className="relative">
              <Search className="pointer-events-none absolute left-3.5 top-3.5 h-4 w-4 text-[var(--ink-muted)]" />
              <input
                value={searchInput}
                onChange={(event) => {
                  setSearchInput(event.target.value);
                  setPage(1);
                }}
                placeholder="Search opponents, openings, ECO codes, or dates…"
                className="w-full rounded-xl border border-[var(--line)] bg-[var(--surface)]/80 py-3 pl-10 pr-4 text-sm text-[var(--ink-soft)] outline-none transition placeholder:text-[var(--ink-dim)] focus:border-[var(--a)]/50 focus:ring-2 focus:ring-[var(--a)]/10"
              />
              <span className="absolute right-3 top-3.5 font-mono-tabular text-[10px] text-[var(--ink-muted)]">
                {data.total.toLocaleString()} games
              </span>
            </div>

            {error && (
              <div className="rounded-xl border border-[var(--warm)]/30 bg-[var(--warm-bg)] px-4 py-3 text-xs text-[var(--warm-soft)]">
                {error}
              </div>
            )}

            {loading ? (
              <div className="flex items-center justify-center gap-2 rounded-2xl border border-[var(--line)] bg-[var(--surface)]/60 py-16 text-sm text-[var(--ink-muted)]">
                <Spinner /> Searching archive…
              </div>
            ) : data.games.length === 0 ? (
              <EmptyState
                icon={<Library className="h-6 w-6" />}
                title="No games match this search."
                detail="Try a broader opponent name, another month, or clear the filters. You can also paste a completely new PGN at any time."
                action={
                  <button
                    type="button"
                    onClick={onOpenImport}
                    className="rounded-lg bg-[var(--a)] px-4 py-2.5 text-xs font-bold text-[#0a0714]"
                  >
                    Paste a PGN
                  </button>
                }
              />
            ) : (
              <>
                <div className="grid gap-3 md:grid-cols-2">
                  {data.games.map((game) => (
                    <GameCard key={game.id} game={game} onOpen={() => onOpenGame(game.id)} />
                  ))}
                </div>

                <div className="flex flex-wrap items-center justify-between gap-3 rounded-xl border border-[var(--line)] bg-[var(--surface)]/60 px-4 py-3">
                  <p className="text-[11px] text-[var(--ink-secondary)]">
                    Page <span className="font-mono-tabular text-[var(--ink-soft)]">{data.page}</span> of{' '}
                    <span className="font-mono-tabular text-[var(--ink-soft)]">{totalPages}</span> · showing {data.games.length} games
                  </p>
                  <div className="flex items-center gap-2">
                    <button
                      type="button"
                      disabled={page <= 1}
                      onClick={() => setPage((p) => Math.max(1, p - 1))}
                      className="inline-flex items-center gap-1 rounded-lg border border-[var(--line)] px-3 py-2 text-[11px] font-semibold text-[var(--ink-secondary)] transition hover:border-[var(--a)]/45 disabled:opacity-35"
                    >
                      <ChevronLeft className="h-3.5 w-3.5" /> Prev
                    </button>
                    <button
                      type="button"
                      disabled={page >= totalPages}
                      onClick={() => setPage((p) => Math.min(totalPages, p + 1))}
                      className="inline-flex items-center gap-1 rounded-lg border border-[var(--line)] px-3 py-2 text-[11px] font-semibold text-[var(--ink-secondary)] transition hover:border-[var(--a)]/45 disabled:opacity-35"
                    >
                      Next <ChevronRight className="h-3.5 w-3.5" />
                    </button>
                  </div>
                </div>
              </>
            )}
          </main>
        </div>
      )}
    </div>
  );
};
