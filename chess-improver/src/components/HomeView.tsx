import React, { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { ArrowUpRight, CheckCircle2, CircleHelp, Clock3, Crown, Flame, Target, Upload } from 'lucide-react';
import type {
  ArchiveOverviewResponse,
  CoachAnswerResponse,
  CoachAskRequest,
  CoachStatusResponse,
  GameSummary,
  LearningPlanResponse,
} from '../../shared/types';
import { api } from '../lib/api';
import { cx } from '../lib/chessFormat';
import { LearningPlanView } from './LearningPlanView';

type CoachHistory = NonNullable<CoachAskRequest['history']>;

interface HomeViewProps {
  overview: ArchiveOverviewResponse | null;
  onTrainMistake: (gameId: string, mistakeId: string) => void;
  onOpenGame: (gameId: string) => void;
  onOpenVault: () => void;
  onOpenCoach: () => void;
  onOpenImport: () => void;
  onOpenLibrary: () => void;
  onOpenTour: () => void;
  onOpenMirror: () => void;
  onRefreshOverview: () => void;
}

const COACH_CHIPS = [
  'Why do I lose with Black?',
  'What should I study this week?',
  'Show my worst blunders',
  'Am I improving?',
];

function formatMonth(month: string): string {
  const [year, monthNumber] = month.split('-').map(Number);
  if (!year || !monthNumber) return month;
  return new Intl.DateTimeFormat('en', { month: 'short', year: 'numeric', timeZone: 'UTC' }).format(
    new Date(Date.UTC(year, monthNumber - 1, 1)),
  );
}

function scorePct(entry: { games: number; wins: number; losses: number } | undefined): number {
  if (!entry || entry.games === 0) return 0;
  const draws = Math.max(0, entry.games - entry.wins - entry.losses);
  return Math.round(((entry.wins + draws * 0.5) / entry.games) * 100);
}

function weekdayLabel(): string {
  const now = new Date();
  const weekday = new Intl.DateTimeFormat('en', { weekday: 'long' }).format(now);
  const hour = now.getHours();
  const part = hour < 12 ? 'morning' : hour < 18 ? 'afternoon' : 'evening';
  return `${weekday} ${part}`;
}

type CurriculumProps = React.ComponentProps<typeof LearningPlanView> & {
  initialPlan: LearningPlanResponse | null;
};

function DeferredCurriculum({ initialPlan, ...props }: CurriculumProps) {
  const [ready, setReady] = useState(false);
  const sentinel = useRef<HTMLDivElement | null>(null);

  useEffect(() => {
    if (ready) return;
    const node = sentinel.current;
    if (!node || typeof IntersectionObserver === 'undefined') {
      setReady(true);
      return;
    }
    const observer = new IntersectionObserver(
      (entries) => {
        if (entries.some((entry) => entry.isIntersecting)) {
          setReady(true);
          observer.disconnect();
        }
      },
      { rootMargin: '700px 0px' },
    );
    observer.observe(node);
    return () => observer.disconnect();
  }, [ready]);

  return (
    <div className="curriculum-defer" ref={sentinel}>
      {ready ? (
        <LearningPlanView initialPlan={initialPlan} {...props} />
      ) : (
        <div className="curriculum-placeholder">Scroll to load the full ranked curriculum…</div>
      )}
    </div>
  );
}

interface RatingPoint {
  month: string;
  value: number;
  x: number;
  y: number;
}

function RatingChart({ overview }: { overview: ArchiveOverviewResponse | null }) {
  const [hoverIndex, setHoverIndex] = useState<number | null>(null);
  const chart = useMemo(() => {
    const rows = overview?.eloTimeline ?? [];
    const values = rows
      .map((row) => row.rapidElo ?? row.blitzElo ?? row.bulletElo)
      .filter((value): value is number => typeof value === 'number');
    if (values.length === 0) {
      return { points: [] as RatingPoint[], linePath: '', areaPath: '', lo: 0, hi: 1 };
    }
    const lo = Math.min(...values) - 30;
    const hi = Math.max(...values) + 30;
    const width = 800;
    const height = 230;
    const pad = 18;
    const points: RatingPoint[] = [];
    rows.forEach((row, index) => {
      const value = row.rapidElo ?? row.blitzElo ?? row.bulletElo;
      if (typeof value !== 'number') return;
      const x = rows.length > 1 ? (index / (rows.length - 1)) * width : width / 2;
      const y = height - pad - ((value - lo) / Math.max(1, hi - lo)) * (height - pad * 2);
      points.push({ month: row.month, value, x, y });
    });
    const linePath = points.map((point, index) => `${index ? 'L' : 'M'}${point.x.toFixed(1)} ${point.y.toFixed(1)}`).join(' ');
    const areaPath = points.length
      ? `${linePath} L${points[points.length - 1].x.toFixed(1)} ${height} L${points[0].x.toFixed(1)} ${height} Z`
      : '';
    return { points, linePath, areaPath, lo, hi };
  }, [overview]);

  const latest = chart.points[chart.points.length - 1]?.value;
  const first = chart.points[0]?.value;
  const delta = typeof latest === 'number' && typeof first === 'number' ? latest - first : 0;
  const hovered = hoverIndex !== null ? chart.points[hoverIndex] : null;

  return (
    <>
      <div className="big">
        {latest?.toLocaleString() ?? '—'} <small>{delta >= 0 ? '▲' : '▼'} {Math.abs(delta)} since {chart.points[0] ? formatMonth(chart.points[0].month) : 'the start'}</small>
      </div>
      <div className="font-mono-tabular mt-2 text-[13px] text-[var(--ink-muted)]">
        {hovered
          ? `${formatMonth(hovered.month)} · ${hovered.value.toLocaleString()} Elo`
          : 'Hover to travel through your rating history. Values come from the archive timeline.'}
      </div>
      {chart.points.length > 1 ? (
        <svg
          className="chart"
          viewBox="0 0 800 230"
          preserveAspectRatio="none"
          role="img"
          aria-label="Rating history from the local game archive"
          onMouseMove={(event) => {
            const rect = event.currentTarget.getBoundingClientRect();
            const ratio = (event.clientX - rect.left) / Math.max(1, rect.width);
            const index = Math.round(ratio * (chart.points.length - 1));
            setHoverIndex(Math.max(0, Math.min(chart.points.length - 1, index)));
          }}
          onMouseLeave={() => setHoverIndex(null)}
        >
          <defs>
            <linearGradient id="coach-rating-fill" x1="0" y1="0" x2="0" y2="1">
              <stop offset="0%" stopColor="var(--a)" stopOpacity="0.45" />
              <stop offset="100%" stopColor="var(--a)" stopOpacity="0" />
            </linearGradient>
          </defs>
          <path d={chart.areaPath} fill="url(#coach-rating-fill)" />
          <path
            d={chart.linePath}
            fill="none"
            stroke="var(--a2)"
            strokeWidth="2.5"
            strokeLinejoin="round"
            style={{ filter: 'drop-shadow(0 0 6px var(--a))' }}
          />
          {chart.points.map((point, index) =>
            index % 6 === 0 || index === chart.points.length - 1 ? (
              <circle
                key={point.month}
                cx={point.x}
                cy={point.y}
                r="4.5"
                fill="var(--surface-deep)"
                stroke="var(--a2)"
                strokeWidth="2"
              />
            ) : null,
          )}
          {hovered && (
            <>
              <line x1={hovered.x} y1="0" x2={hovered.x} y2="230" stroke="rgba(255,255,255,0.3)" />
              <circle cx={hovered.x} cy={hovered.y} r="6" fill="var(--ink)" />
            </>
          )}
        </svg>
      ) : (
        <div className="mt-4 rounded-xl border border-[var(--line)] bg-[var(--surface-soft)] px-4 py-8 text-center text-sm text-[var(--ink-muted)]">
          Rating timeline appears after the archive loads.
        </div>
      )}
    </>
  );
}

export const HomeView: React.FC<HomeViewProps> = ({
  overview,
  onTrainMistake,
  onOpenGame,
  onOpenVault,
  onOpenCoach,
  onOpenImport,
  onOpenLibrary,
  onOpenTour,
  onOpenMirror,
  onRefreshOverview,
}) => {
  const [plan, setPlan] = useState<LearningPlanResponse | null>(null);
  const [coachStatus, setCoachStatus] = useState<CoachStatusResponse | null>(null);
  const [games, setGames] = useState<GameSummary[]>([]);
  const [loadError, setLoadError] = useState<string | null>(null);
  const [question, setQuestion] = useState('');
  const [answer, setAnswer] = useState<CoachAnswerResponse | null>(null);
  const [history, setHistory] = useState<CoachHistory>([]);
  const [asking, setAsking] = useState(false);
  const [coachError, setCoachError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    // Independent requests prevent a slow plan build from hiding coach status.
    api.learningPlan().then((value) => { if (!cancelled) setPlan(value); })
      .catch((err: unknown) => { if (!cancelled) setLoadError(err instanceof Error ? err.message : 'Could not load the learning plan.'); });
    api.coachStatus().then((value) => { if (!cancelled) setCoachStatus(value); })
      .catch(() => { if (!cancelled) setCoachError('Could not check coach status.'); });
    api.games({ limit: 10 }).then((value) => { if (!cancelled) setGames(value.games); })
      .catch(() => { if (!cancelled) setLoadError('Could not load recent games.'); });
    return () => {
      cancelled = true;
    };
  }, []);

  const initialGreeting = useMemo(() => {
    if (!plan) return 'Loading your local study plan…';
    return `Stockfish has analyzed ${plan.analyzedGames.toLocaleString()} games and found ${plan.totalMistakes.toLocaleString()} mistakes. ${plan.dueCount.toLocaleString()} blind drills are ready. Ask about your study plan or start a session.`;
  }, [plan]);

  // The old 8ms character-by-character typing effect re-rendered the entire
  // dashboard ~200 times per answer. Render once; the caret still indicates
  // a request in flight.
  const coachText = answer?.answer ?? initialGreeting;

  const ask = useCallback(
    async (raw: string) => {
      const nextQuestion = raw.trim().slice(0, 800);
      if (!nextQuestion || asking) return;
      setAsking(true);
      setCoachError(null);
      setQuestion('');
      try {
        const response = await api.askCoach(nextQuestion, history.slice(-6));
        setAnswer(response);
        // Refresh status after a provider attempt so errors and newly added keys are visible.
        void api.coachStatus().then(setCoachStatus).catch(() => {});
        const entries: CoachHistory = [
          { role: 'user', text: nextQuestion },
          { role: 'coach', text: response.answer },
        ];
        setHistory((previous) => [...previous, ...entries].slice(-6));
      } catch (err) {
        setQuestion(nextQuestion);
        setCoachError(err instanceof Error ? err.message : 'The coach could not answer right now.');
      } finally {
        setAsking(false);
      }
    },
    [asking, history],
  );

  const topMotif = plan?.counts.byMotif[0];
  const firstDrill = plan?.recommendedDrills[0];
  const topMotifs = plan?.counts.byMotif.slice(0, 3) ?? [];
  const openings = overview?.topOpenings.slice(0, 3) ?? [];
  const latestGame = useMemo(() => {
    if (games.length === 0) return null;
    return [...games].sort((a, b) => b.date.localeCompare(a.date))[0] ?? null;
  }, [games]);

  const rapidPct = scorePct(overview?.byTimeClass.rapid);
  const bulletPct = scorePct(overview?.byTimeClass.bullet);
  const phase = plan?.counts.byPhase;
  const severity = plan?.counts.bySeverity;
  const maxPhase = Math.max(1, phase?.opening ?? 0, phase?.middlegame ?? 0, phase?.endgame ?? 0);
  const maxSeverity = Math.max(1, severity?.blunder ?? 0, severity?.mistake ?? 0, severity?.inaccuracy ?? 0);

  const startTraining = () => {
    if (firstDrill) onTrainMistake(firstDrill.gameId, firstDrill.mistakeId);
    else onOpenCoach();
  };

  return (
    <div className="wrap view-shell">
      {loadError && (
        <div className="mb-4 rounded-2xl border border-[var(--warm)]/30 bg-[var(--warm-bg)]/80 px-4 py-3 text-sm text-[var(--warm-soft)]">
          {loadError}
        </div>
      )}

      <section className="hero">
        <div>
          <div className="flex flex-wrap items-center gap-3">
            <span className="eyebrow">{weekdayLabel()}</span>
            <button
              type="button"
              onClick={onOpenTour}
              className="inline-flex items-center gap-1.5 text-xs font-medium text-[var(--ink-muted)] transition hover:text-[var(--a2)]"
            >
              <CircleHelp className="h-3.5 w-3.5" /> 60-sec tour
            </button>
          </div>
          <h1 className="hero-title">
            Your games,<br />
            <em>remembered.</em>
          </h1>

          <div className="coach-card">
            <div className="avatar"><Crown className="h-5 w-5" /></div>
            <div className="min-w-0 flex-1">
              <div className="flex flex-wrap items-center gap-2">
                <small>Your coach</small>
                <span
                  className="rounded-full border border-[var(--line)] bg-[var(--a-soft)] px-2 py-0.5 text-[10px] font-semibold text-[var(--a2)]"
                  title={coachStatus?.reason ?? 'Coach status loading…'}
                >
                  {!coachStatus ? 'Checking coach…' : !coachStatus.configured ? 'Gemini off · local coach' : answer?.source === 'gemini' ? 'Gemini intent · local facts' : coachStatus.lastProviderError ? 'Gemini unavailable · local coach' : 'Gemini key configured · not yet verified'}
                </span>
                <span className="text-[10px] text-[var(--ink-muted)]">
                  {answer ? (answer.source === 'gemini' ? 'Gemini · ' : 'Local · ') + answer.status : 'Stockfish 18 NNUE · spoiler-free'}
                </span>
              </div>
              <p className="coach-card-answer">
                {coachText}
                {asking && <i className="caret" />}
              </p>
              {(answer?.error || coachError) && (
                <p className="mt-1 text-[11px] leading-relaxed text-[var(--ink-muted)]">
                  {coachError ?? answer?.error}
                </p>
              )}
            </div>
          </div>

          <form
            className="ask"
            onSubmit={(event) => {
              event.preventDefault();
              void ask(question);
            }}
          >
            <input
              value={question}
              onChange={(event) => setQuestion(event.target.value)}
              placeholder="Ask anything about your chess…"
              autoComplete="off"
              maxLength={800}
              aria-label="Ask the coach about your chess"
            />
            <button className="btn" type="submit" disabled={asking || !question.trim()}>
              {asking ? 'Thinking…' : 'Ask'}
            </button>
          </form>

          <div className="chips">
            {(answer?.suggestions.length ? answer.suggestions : COACH_CHIPS).map((chip) => (
              <button key={chip} className="chip" type="button" onClick={() => void ask(chip)} disabled={asking}>
                {chip}
              </button>
            ))}
          </div>

          <p className="mt-3 max-w-[520px] text-[11px] leading-relaxed text-[var(--ink-muted)]">
            {answer?.knowledge
              ? `${answer.knowledge.engine} · ${answer.knowledge.analyzedGames.toLocaleString()} analyzed games · ${answer.knowledge.totalMistakes.toLocaleString()} verified mistakes · ${answer.knowledge.dueCount.toLocaleString()} due. Answers never name the engine move before a drill is failed.`
              : 'Stockfish supplies the chess knowledge; Gemini may choose a topic; answers are generated locally from Stockfish and archive data. No key is sent to the browser.'}
            {coachStatus?.hint ? ` ${coachStatus.hint}` : ''}
          </p>
        </div>

        <aside className="home-focus" aria-labelledby="focus-title">
          <span className="home-focus-kicker">Your next step</span>
          <h2 id="focus-title">A little practice, built around your games.</h2>
          <p>Try a position blind, then review the Stockfish analysis. Your answer stays hidden until the drill is finished.</p>
          <div className="home-focus-stats">
            <div><strong>{plan?.dueCount.toLocaleString() ?? '—'}</strong><span>positions due</span></div>
            <div><strong>{plan?.analyzedGames.toLocaleString() ?? '—'}</strong><span>games analyzed</span></div>
          </div>
          <button type="button" data-tour="start-training" className="btn home-focus-action" onClick={startTraining}>
            Start training <span aria-hidden="true">→</span>
          </button>
          <div className="home-focus-links"><button type="button" className="home-focus-link" onClick={onOpenMirror}>Play against your mirror →</button><button type="button" className="home-focus-link" onClick={onOpenVault}>Explore your mistake vault →</button></div>
        </aside>
      </section>

      <div className="section-title">
        <h2>
          Your <em>chess mind</em>, at a glance
        </h2>
        <span>Updated from your local archive</span>
      </div>

      <section className="bento">
        <div className="card s4">
          <h3>
            Rating journey
            <button type="button" onClick={onOpenLibrary} className="inline-flex items-center gap-1">
              Full library <ArrowUpRight className="h-3 w-3" />
            </button>
          </h3>
          <RatingChart overview={overview} />
        </div>

        <div className="card s2 train">
          <h3>Today's training</h3>
          <div className="stack">
            {(plan?.recommendedDrills.slice(0, 3) ?? []).map((drill, index) => (
              <div key={drill.mistakeId} style={{ zIndex: 3 - index }}>
                <small>
                  #{drill.rank} · {drill.motifLabel} · {drill.phaseLabel}
                </small>
                Move {drill.moveNumber} {drill.playedMoveSan} vs {drill.opponent} — {drill.focus}
              </div>
            ))}
            {!plan && (
              <>
                <div><small>Loading plan…</small>Stockfish is indexing your archive.</div>
                <div><small>Blind first</small>The answer stays hidden.</div>
                <div><small>Recall loop</small>Missed positions come back first.</div>
              </>
            )}
          </div>
          <p>
            <b>{plan?.dueCount.toLocaleString() ?? '—'} positions</b> from your own mistakes are due. Choose a position and work at your own pace.
          </p>
          <button
            type="button"
            className="btn"
            onClick={startTraining}
          >
            Start session →
          </button>
        </div>

        <div className="card s2">
          <h3>
            Recurring mistakes
            <button type="button" onClick={onOpenVault} className="inline-flex items-center gap-1">
              All <ArrowUpRight className="h-3 w-3" />
            </button>
          </h3>
          <div className="mt-3">
            {topMotifs.map((motif, index) => (
              <div className="pat" key={motif.motif}>
                <div className="ic">
                  {index === 0 ? <Flame className="h-4 w-4" /> : index === 1 ? <Target className="h-4 w-4" /> : <Clock3 className="h-4 w-4" />}
                </div>
                <div className="t">
                  {motif.label}
                  <small className={index === 1 ? 'up' : 'down'}>
                    {motif.mastered.toLocaleString()} mastered · Stockfish verified
                  </small>
                </div>
                <div className="n">{motif.count.toLocaleString()}</div>
              </div>
            ))}
            {topMotifs.length === 0 && <p className="py-6 text-sm text-[var(--ink-muted)]">Patterns appear after analysis.</p>}
          </div>
        </div>

        <div className="card s2 op">
          <h3>
            Opening results
            <button type="button" onClick={onOpenLibrary} className="inline-flex items-center gap-1">
              Repertoire <ArrowUpRight className="h-3 w-3" />
            </button>
          </h3>
          <div className="mt-4 space-y-4">
            {openings.map((opening) => (
              <div key={opening.name}>
                <div className="row">
                  <span>{opening.name}</span>
                  <small>{opening.games} games · {opening.winRate}% win rate</small>
                </div>
                <div className="seg">
                  {Array.from({ length: 10 }, (_, index) => (
                    <i key={index} className={index < Math.round((opening.winRate / 100) * 10) ? 'k' : ''} />
                  ))}
                </div>
              </div>
            ))}
            {openings.length === 0 && <p className="text-sm text-[var(--ink-muted)]">Openings appear after the archive loads.</p>}
          </div>
          <div className="legend"><span>Win rate</span></div>
        </div>

        <div className="card s2">
          <h3>
            Latest game
            {latestGame && (
              <button type="button" onClick={() => onOpenGame(latestGame.id)} className="inline-flex items-center gap-1">
                Replay <ArrowUpRight className="h-3 w-3" />
              </button>
            )}
          </h3>
          {latestGame ? (
            <>
              <div className="mt-3 font-display text-[22px]">
                vs. {latestGame.opponentName}{' '}
                <span className={cx('res', latestGame.userOutcome === 'win' && '!border-[var(--cool)] !text-[var(--cool)]')}>
                  {latestGame.userOutcome === 'win' ? 'Won' : latestGame.userOutcome === 'loss' ? 'Lost' : latestGame.userOutcome === 'draw' ? 'Drew' : 'Unfinished'}
                </span>
              </div>
              <p className="mt-1 text-[12px] text-[var(--ink-muted)]">
                {latestGame.date} · {latestGame.openingName} · {latestGame.timeClass}
              </p>
              {latestGame.analyzed ? <div className="mt-4 flex items-end gap-2">
                {[
                  { label: 'Blunders', value: latestGame.blundersCount ?? 0, color: 'var(--warm)' },
                  { label: 'Mistakes', value: latestGame.mistakesCount ?? 0, color: 'var(--amber)' },
                  { label: 'Inaccuracies', value: latestGame.inaccuraciesCount ?? 0, color: 'var(--cool)' },
                ].map((bar) => {
                  const max = Math.max(1, latestGame.blundersCount ?? 0, latestGame.mistakesCount ?? 0, latestGame.inaccuraciesCount ?? 0);
                  return (
                    <div key={bar.label} className="flex-1">
                      <div
                        className="rounded-t-md"
                        style={{ height: `${Math.max(8, (bar.value / max) * 64)}px`, background: bar.color }}
                      />
                      <p className="mt-1 text-[9px] uppercase tracking-wider text-[var(--ink-muted)]">{bar.label} {bar.value}</p>
                    </div>
                  );
                })}
              </div> : <p className="mt-4 text-sm text-[var(--ink-muted)]">This game has not been analyzed yet.</p>}
              {latestGame.analyzed && <div className="moment">
                <b className="bad">??</b>
                <div>
                  Stockfish-verified moments
                  <small>Open the game to train them blind; answers appear only after a final miss.</small>
                </div>
              </div>}
            </>
          ) : (
            <div className="mt-4 rounded-xl border border-[var(--line)] bg-[var(--surface-soft)] px-4 py-8 text-center text-sm text-[var(--ink-muted)]">
              Loading the latest archive game…
            </div>
          )}
          <button
            type="button"
            onClick={onOpenImport}
            className="mt-4 inline-flex w-full items-center justify-center gap-2 rounded-xl border border-[var(--line)] bg-[var(--surface-soft)] px-3 py-2 text-xs font-semibold text-[var(--ink-secondary)] transition hover:border-[var(--a)] hover:text-[var(--ink)]"
          >
            <Upload className="h-3.5 w-3.5" /> Import games
          </button>
        </div>

        <div className="card s6" data-tour="quick-guide">
          <h3>Insights only your history could reveal</h3>
          <div className="ins">
            <div>
              <span className="tag">Time control</span>
              <h4>Rapid scores {rapidPct}%, bullet {bulletPct}%.</h4>
              <div className="bars">
                <div><span>Rapid</span><i style={{ width: `${rapidPct}%` }} /><b>{rapidPct}%</b></div>
                <div><span>Bullet</span><i className="weak" style={{ width: `${bulletPct}%` }} /><b>{bulletPct}%</b></div>
              </div>
              <p className="mt-3 text-[11px] leading-relaxed text-[var(--ink-muted)]">
                Score includes draws as half points, computed from the local archive.
              </p>
            </div>
            <div>
              <span className="tag">Phase pressure</span>
              <h4>Where Stockfish finds the most costly slips.</h4>
              <div className="bars">
                <div><span>Opening</span><i style={{ width: `${((phase?.opening ?? 0) / maxPhase) * 100}%` }} /><b>{phase?.opening.toLocaleString() ?? '—'}</b></div>
                <div><span>Middlegame</span><i className={phase?.middlegame === maxPhase ? 'weak' : ''} style={{ width: `${((phase?.middlegame ?? 0) / maxPhase) * 100}%` }} /><b>{phase?.middlegame.toLocaleString() ?? '—'}</b></div>
                <div><span>Endgame</span><i style={{ width: `${((phase?.endgame ?? 0) / maxPhase) * 100}%` }} /><b>{phase?.endgame.toLocaleString() ?? '—'}</b></div>
              </div>
            </div>
            <div>
              <span className="tag">No-spoiler rule</span>
              <h4>Fail first, reveal second.</h4>
              <div className="bars">
                <div><span>Blunders</span><i className="weak" style={{ width: `${((severity?.blunder ?? 0) / maxSeverity) * 100}%` }} /><b>{severity?.blunder.toLocaleString() ?? '—'}</b></div>
                <div><span>Mastered</span><i style={{ width: `${plan?.totalMistakes ? (plan.masteredCount / plan.totalMistakes) * 100 : 0}%` }} /><b>{plan?.masteredCount.toLocaleString() ?? '—'}</b></div>
                <div><span>First try</span><i style={{ width: `${plan?.firstTrySolveRate ?? 0}%` }} /><b>{plan?.firstTrySolveRate ?? 0}%</b></div>
              </div>
              <p className="mt-3 flex items-start gap-1.5 text-[11px] leading-relaxed text-[var(--ink-muted)]">
                <CheckCircle2 className="mt-0.5 h-3 w-3 shrink-0 text-[var(--a2)]" />
                Coach answers use aggregate counts and your own moves only — never an engine answer.
              </p>
            </div>
          </div>
        </div>
      </section>

      <div className="section-title">
        <h2>
          Your full <em>curriculum</em>
        </h2>
        <span>Ranked by Stockfish · still spoiler-free</span>
      </div>
      <DeferredCurriculum
        initialPlan={plan}
        onTrainMistake={onTrainMistake}
        onOpenVault={onOpenVault}
        onOpenCoach={onOpenCoach}
        onOpenImport={onOpenImport}
        onOpenTour={onOpenTour}
        onRefreshOverview={onRefreshOverview}
      />
    </div>
  );
};
