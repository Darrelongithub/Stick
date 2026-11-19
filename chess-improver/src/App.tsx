import React, { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import {
  BookOpen,
  Brain,
  CheckCircle2,
  CircleHelp,
  Crown,
  Sparkles,
  Target,
  Volume2,
  VolumeX,
  X,
} from 'lucide-react';
import type { ArchiveOverviewResponse, GameDetailResponse, GameSummary } from '../shared/types';
import { api, streamGameAnalysis } from './lib/api';
import type { AnalysisProgress } from './lib/api';
import { cx } from './lib/chessFormat';
import { soundEngine } from './lib/sound';
import { CoachPanel } from './components/CoachPanel';
import { HomeView } from './components/HomeView';
import { MirrorView } from './components/MirrorView';
import { LibraryInsightsView } from './components/LibraryInsightsView';
import { MistakeVaultView } from './components/MistakeVaultView';
import { GuidedTour, TOUR_STORAGE_KEY } from './components/GuidedTour';
import type { TourView } from './components/GuidedTour';
import { PastePgnModal } from './components/PastePgnModal';
import { Spinner } from './components/ui';

type AppView = 'plan' | 'coach' | 'vault' | 'library' | 'mirror';

const NAV_ITEMS: Array<{
  id: AppView;
  step: string;
  label: string;
  icon: React.ReactNode;
  hint: string;
}> = [
  { id: 'plan', step: '1', label: 'Start Here', icon: <Sparkles className="h-3.5 w-3.5" />, hint: 'Your learning plan' },
  { id: 'coach', step: '2', label: 'Coach', icon: <Target className="h-3.5 w-3.5" />, hint: 'Blind mistake training' },
  { id: 'vault', step: '3', label: 'Mistake Vault', icon: <Brain className="h-3.5 w-3.5" />, hint: 'Spaced repetition' },
  { id: 'library', step: '4', label: 'Library', icon: <BookOpen className="h-3.5 w-3.5" />, hint: 'Your games and insights' },
  { id: 'mirror', step: '5', label: 'Mirror', icon: <Target className="h-3.5 w-3.5" />, hint: 'Play against your recorded patterns' },
];

const ACCENTS = [
  { name: 'Violet', a: '#8b7cff', a2: '#cfc7ff' },
  { name: 'Blue', a: '#4ea1ff', a2: '#bddcff' },
  { name: 'Rose', a: '#ff6fae', a2: '#ffc6e0' },
  { name: 'Amber', a: '#ffb340', a2: '#ffe0a8' },
] as const;

export default function App() {
  const [view, setView] = useState<AppView>('plan');
  const [overview, setOverview] = useState<ArchiveOverviewResponse | null>(null);
  const [overviewError, setOverviewError] = useState<string | null>(null);
  const [activeGame, setActiveGame] = useState<GameDetailResponse | null>(null);
  const [gameLoading, setGameLoading] = useState(false);
  const [analysisProgress, setAnalysisProgress] = useState<AnalysisProgress | null>(null);
  const [initialMistakeId, setInitialMistakeId] = useState<string | null>(null);
  const [importOpen, setImportOpen] = useState(false);
  const [libraryRevision, setLibraryRevision] = useState(0);
  const [muted, setMuted] = useState(soundEngine.muted);
  const [booting, setBooting] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [toast, setToast] = useState<string | null>(null);
  const [tourOpen, setTourOpen] = useState(false);
  const streamCloseRef = useRef<(() => void) | null>(null);
  const activeGameIdRef = useRef<string | null>(null);
  const gameRequestRef = useRef(0);
  const overviewRequestRef = useRef(0);
  const bootedRef = useRef(false);
  const spotRef = useRef<HTMLDivElement | null>(null);
  const [accentIndex, setAccentIndex] = useState(0);

  useEffect(() => {
    const root = document.documentElement;
    const accent = ACCENTS[accentIndex];
    root.style.setProperty('--a', accent.a);
    root.style.setProperty('--a2', accent.a2);
    root.style.setProperty('--burgundy', accent.a);
    root.style.setProperty('--burgundy-light', accent.a2);
  }, [accentIndex]);

  useEffect(() => {
    // A full-screen radial-gradient repaint on every pointer event was the
    // largest source of home-page jank. Move one composited element instead,
    // and only on fine pointers where the spotlight is visible.
    if (
      window.matchMedia('(pointer: coarse)').matches ||
      window.matchMedia('(prefers-reduced-motion: reduce)').matches
    ) {
      return;
    }
    let frame = 0;
    let x = window.innerWidth / 2;
    let y = window.innerHeight * 0.3;
    const apply = () => {
      frame = 0;
      const spot = spotRef.current;
      if (spot) spot.style.transform = `translate3d(${x}px, ${y}px, 0)`;
    };
    const onPointerMove = (event: PointerEvent) => {
      x = event.clientX;
      y = event.clientY;
      if (!frame) frame = window.requestAnimationFrame(apply);
    };
    window.addEventListener('pointermove', onPointerMove, { passive: true });
    return () => {
      window.removeEventListener('pointermove', onPointerMove);
      if (frame) window.cancelAnimationFrame(frame);
    };
  }, []);

  const refreshOverview = useCallback(async () => {
    const token = ++overviewRequestRef.current;
    try {
      const data = await api.overview();
      if (token === overviewRequestRef.current) { setOverview(data); setOverviewError(null); }
    } catch (err) {
      if (token === overviewRequestRef.current) setOverviewError(err instanceof Error ? err.message : 'Could not load archive overview.');
    }
  }, []);

  const startAnalysis = useCallback(
    (gameId: string) => {
      streamCloseRef.current?.();
      setAnalysisProgress({
        stage: 'Connecting to Stockfish 18 NNUE…',
        current: 0,
        total: 0,
        percent: 0,
      });

      const close = streamGameAnalysis(gameId, {
        onProgress: (progress) => {
          if (activeGameIdRef.current === gameId) setAnalysisProgress(progress);
        },
        onDone: (detail) => {
          if (activeGameIdRef.current !== gameId) return;
          streamCloseRef.current = null;
          setActiveGame(detail);
          setAnalysisProgress(null);
          void refreshOverview();
          setToast(
            detail.mistakes.length > 0
              ? `Stockfish found ${detail.mistakes.length} mistakes to learn from.`
              : 'Stockfish found no costly mistakes in this game.'
          );
        },
        onError: (message) => {
          if (activeGameIdRef.current !== gameId) return;
          streamCloseRef.current = null;
          setAnalysisProgress(null);
          setError(message);
        },
      });

      streamCloseRef.current = close;
    },
    [refreshOverview]
  );

  const loadGame = useCallback(
    async (gameId: string, mistakeId: string | null = null, switchView = true, requestId?: number) => {
      const token = requestId ?? ++gameRequestRef.current;
      if (token !== gameRequestRef.current) return;
      streamCloseRef.current?.();
      streamCloseRef.current = null;
      activeGameIdRef.current = gameId;
      setActiveGame(null);
      setGameLoading(true);
      // Boot warms the first drill in the background without stealing Start Here.
      if (switchView) setView('coach');
      setInitialMistakeId(mistakeId);
      setError(null);
      setAnalysisProgress(null);

      try {
        const detail = await api.game(gameId);
        if (activeGameIdRef.current !== gameId || token !== gameRequestRef.current) return;
        setActiveGame(detail);
        if (!detail.analyzed) startAnalysis(gameId);
      } catch (err) {
        if (token === gameRequestRef.current) setError(err instanceof Error ? err.message : `Could not open game ${gameId}.`);
      } finally {
        if (token === gameRequestRef.current) setGameLoading(false);
      }
    },
    [startAnalysis]
  );

  const loadNextGame = useCallback(
    async (excludeId?: string, switchView = true) => {
      const token = ++gameRequestRef.current;
      setGameLoading(true);
      try {
        const result = await api.nextCoachGame(excludeId);
        if (token !== gameRequestRef.current) return;
        if (result.game) await loadGame(result.game.id, null, switchView, token);
        else setGameLoading(false);
      } catch (err) {
        if (token !== gameRequestRef.current) return;
        setGameLoading(false);
        setError(err instanceof Error ? err.message : 'Could not pick a game.');
      }
    },
    [loadGame]
  );

  useEffect(() => {
    if (bootedRef.current) return;
    bootedRef.current = true;
    let cancelled = false;

    const boot = async () => {
      try {
        // Home only needs the aggregate overview. The 47 KB coach game detail
        // is loaded on first Coach navigation instead of warming in the
        // background and re-rendering the whole dashboard.
        await refreshOverview();
      } catch (err) {
        setError(err instanceof Error ? err.message : 'Could not initialize the chess improver.');
      } finally {
        if (!cancelled) setBooting(false);
      }
    };

    void boot();

    return () => {
      cancelled = true;
      streamCloseRef.current?.();
    };
  }, [refreshOverview]);

  useEffect(() => {
    if (!toast) return;
    const timer = window.setTimeout(() => setToast(null), 4200);
    return () => window.clearTimeout(timer);
  }, [toast]);

  const selectView = useCallback(
    (next: AppView) => {
      if (next === 'coach' && !activeGame && !gameLoading) void loadNextGame(undefined, false);
      setView(next);
    },
    [activeGame, gameLoading, loadNextGame]
  );

  const navigateForTour = useCallback(
    (next: TourView) => {
      setView(next);
      if (next === 'coach' && !activeGame && !gameLoading) void loadNextGame(undefined, false);
    },
    [activeGame, gameLoading, loadNextGame]
  );

  const openTour = useCallback(() => setTourOpen(true), []);
  const closeTour = useCallback(() => {
    setTourOpen(false);
    try {
      window.localStorage.setItem(TOUR_STORAGE_KEY, 'done');
    } catch {
      // Private browsing can disable localStorage; the tour simply reappears next time.
    }
  }, []);

  useEffect(() => {
    if (booting) return;
    try {
      if (window.localStorage.getItem(TOUR_STORAGE_KEY) !== 'done') setTourOpen(true);
    } catch {
      setTourOpen(true);
    }
  }, [booting]);

  const toggleSound = () => {
    const next = !muted;
    soundEngine.muted = next;
    setMuted(next);
  };

  const openImport = useCallback(() => setImportOpen(true), []);
  const closeImport = useCallback(() => setImportOpen(false), []);

  const handleImported = useCallback(
    async (games: GameSummary[]) => {
      closeImport();
      void refreshOverview();
      if (games[0]) {
        setToast(`${games.length} ${games.length === 1 ? 'game' : 'games'} imported · launching Stockfish…`);
        await loadGame(games[0].id);
      }
    },
    [closeImport, loadGame, refreshOverview]
  );

  const openGameFromVault = useCallback(
    (gameId: string, mistakeId?: string) => {
      void loadGame(gameId, mistakeId ?? null);
    },
    [loadGame]
  );

  const viewLibraryFromImport = useCallback(() => {
    closeImport();
    setView('library');
    void refreshOverview();
  }, [closeImport, refreshOverview]);

  const coachKey = useMemo(() => {
    if (!activeGame) return 'none';
    return `${activeGame.summary.id}:${activeGame.analyzed ? activeGame.mistakes.length : 'pending'}:${initialMistakeId ?? ''}`;
  }, [activeGame, initialMistakeId]);

  return (
    <div className="relative min-h-screen text-[var(--ink)]">
      <div className="ambient-orb o1" />
      <div className="ambient-orb o2" />
      <div className="ambient-orb o3" />
      <div className="cursor-spot" ref={spotRef} />
      <div className="grain" />

      <div className="relative z-[1]">
        <nav className="glass-nav" aria-label="Main sections">
          <button type="button" className="logo" onClick={() => selectView('plan')} aria-label="Coach home">
            <b><Crown className="h-4 w-4" /></b> Coach
          </button>
          <select className="mobile-nav-select" aria-label="Choose a section" value={view} onChange={event => selectView(event.target.value as AppView)}>
            {NAV_ITEMS.map(item => <option value={item.id} key={item.id}>{item.label}</option>)}
          </select>
          {NAV_ITEMS.map((item) => {
            const active = view === item.id;
            return (
              <button
                key={item.id}
                type="button"
                data-tour={`nav-${item.id}`}
                title={`${item.label}: ${item.hint}`}
                aria-label={`${item.label}: ${item.hint}`}
                aria-current={active ? 'page' : undefined}
                onClick={() => selectView(item.id)}
                className={cx('nav-link', active && 'active')}
              >
                {item.label}
              </button>
            );
          })}
          <button
            type="button"
            onClick={openImport}
            data-tour="paste-pgn"
            className="nav-link nav-imp"
            title="Paste or upload a new PGN for local Stockfish analysis"
          >
            + Import games
          </button>
          <button
            type="button"
            onClick={openTour}
            data-tour="tour-help"
            className="nav-icon"
            title="Replay the guided tour"
            aria-label="Replay the guided tour"
          >
            <CircleHelp className="h-4 w-4" />
          </button>
          <button
            type="button"
            onClick={toggleSound}
            className="nav-icon"
            title={muted ? 'Unmute board sounds' : 'Mute board sounds'}
            aria-label={muted ? 'Unmute board sounds' : 'Mute board sounds'}
          >
            {muted ? <VolumeX className="h-4 w-4" /> : <Volume2 className="h-4 w-4" />}
          </button>
        </nav>

        <div className="sync">
          <i className="dot" />
          <span className="sync-text">
            {overview ? `${overview.analyzedGamesCount.toLocaleString()} games analyzed` : overviewError ? 'Archive overview unavailable' : 'Loading your archive'} · Stockfish runs locally · Blind drills keep answers hidden
          </span>
        </div>
      </div>

      <main className="relative z-[1] mx-auto max-w-[1400px] px-4 py-6 sm:px-6 sm:py-8">
        {overviewError && (
          <div role="alert" className="mb-5 flex flex-wrap items-center justify-between gap-3 rounded-2xl border border-[var(--warm)]/30 bg-[var(--warm-bg)]/85 px-4 py-3 text-sm text-[var(--warm-soft)]">
            <span>Archive overview unavailable: {overviewError}</span>
            <button type="button" onClick={() => void refreshOverview()} className="rounded-lg border border-current px-3 py-1.5 font-semibold">Retry overview</button>
          </div>
        )}
        {error && (
          <div className="mb-5 flex items-start justify-between gap-3 rounded-2xl border border-[var(--warm)]/30 bg-[var(--warm-bg)]/85 px-4 py-3 text-sm text-[var(--warm-soft)] shadow-[0_22px_60px_-30px_rgba(0,0,0,0.9)] backdrop-blur-xl animate-slide-in-right">
            <span>{error}</span>
            <button type="button" onClick={() => setError(null)} aria-label="Dismiss error">
              <X className="h-4 w-4" />
            </button>
          </div>
        )}

        {booting ? (
          <div className="flex min-h-[60vh] flex-col items-center justify-center gap-4 text-center animate-fade-up">
            <div className="avatar animate-float" style={{ width: 64, height: 64 }}>
              <Crown className="h-8 w-8" />
              <span className="absolute -bottom-1 -right-1 flex h-6 w-6 items-center justify-center rounded-full bg-[var(--surface)] text-[var(--a)]">
                <Spinner className="h-3.5 w-3.5" />
              </span>
            </div>
            <div>
              <p className="font-display text-2xl font-semibold text-[var(--ink)]">Remembering your games…</p>
              <p className="mt-1 text-sm text-[var(--ink-secondary)]">Indexing the archive and warming Stockfish 18 NNUE workers.</p>
            </div>
          </div>
        ) : view === 'plan' ? (
          <HomeView
            overview={overview}
            onTrainMistake={(gameId, mistakeId) => void loadGame(gameId, mistakeId)}
            onOpenGame={(gameId) => void loadGame(gameId)}
            onOpenVault={() => setView('vault')}
            onOpenCoach={() => selectView('coach')}
            onOpenImport={openImport}
            onOpenLibrary={() => setView('library')}
            onOpenTour={openTour}
            onOpenMirror={() => selectView('mirror')}
            onRefreshOverview={() => void refreshOverview()}
          />
        ) : view === 'coach' ? (
          gameLoading ? (
            <div role="status" className="flex min-h-[45vh] items-center justify-center gap-3 text-sm text-[var(--ink-secondary)]"><Spinner className="h-4 w-4" /> Loading your game…</div>
          ) : activeGame ? (
            <CoachPanel
              key={coachKey}
              game={activeGame}
              analysisProgress={analysisProgress}
              initialMistakeId={initialMistakeId}
              onAnalyze={() => startAnalysis(activeGame.summary.id)}
              onRefreshOverview={() => void refreshOverview()}
              onOpenLibrary={() => setView('library')}
              onOpenVault={() => setView('vault')}
            />
          ) : (
            <div className="flex min-h-[55vh] flex-col items-center justify-center gap-4 text-center animate-fade-up">
              <Sparkles className="h-8 w-8 text-[var(--a)]" />
              <h2 className="font-display text-2xl font-semibold text-[var(--ink)]">No game selected</h2>
              <button
                type="button"
                onClick={() => void loadNextGame()}
                className="rounded-lg bg-[var(--a)] px-4 py-2.5 text-xs font-bold text-[#0a0714]"
              >
                Pick a game
              </button>
            </div>
          )
        ) : view === 'mirror' ? (
          <MirrorView />
        ) : view === 'vault' ? (
          <MistakeVaultView
            overview={overview}
            onRefreshOverview={() => void refreshOverview()}
            onOpenGame={openGameFromVault}
            onOpenLibrary={() => setView('library')}
          />
        ) : (
          <LibraryInsightsView
            revision={libraryRevision}
            overview={overview}
            onOpenGame={(id) => void loadGame(id)}
            onOpenImport={openImport}
            onRefreshOverview={() => void refreshOverview()}
          />
        )}
      </main>

      <footer className="page-footer relative z-[1]">
        Built from your games · Stockfish analysis runs locally · Gemini, if enabled, only selects a topic.
        <div className="mt-2 flex items-center justify-center gap-1.5">
          <CheckCircle2 className="h-3 w-3 text-[var(--a2)]" /> Spoiler-safe by design
        </div>
      </footer>

      {toast && (
        <div className="fixed bottom-5 left-1/2 z-[120] flex -translate-x-1/2 items-center gap-2 rounded-full border border-[var(--a)]/40 bg-[var(--a-soft)]/95 px-4 py-2.5 text-xs font-semibold text-[var(--a2)] shadow-[0_14px_45px_rgba(0,0,0,0.55)] backdrop-blur-xl animate-slide-in-up">
          <CheckCircle2 className="h-4 w-4" /> {toast}
        </div>
      )}

      <PastePgnModal
        open={importOpen}
        onClose={closeImport}
        onSaved={() => { setLibraryRevision((revision) => revision + 1); void refreshOverview(); }}
        onImported={(games) => void handleImported(games)}
        onViewLibrary={viewLibraryFromImport}
      />

      <GuidedTour
        open={tourOpen && !booting}
        onClose={closeTour}
        onNavigate={navigateForTour}
      />

      <div className="swatches" aria-label="Accent color">
        <small>Accent</small>
        {ACCENTS.map((accent, index) => (
          <button
            key={accent.name}
            type="button"
            className={cx('sw', accentIndex === index && 'on')}
            style={{ background: accent.a, color: accent.a }}
            onClick={() => setAccentIndex(index)}
            title={accent.name}
            aria-label={`${accent.name} accent`}
            aria-pressed={accentIndex === index}
          />
        ))}
      </div>
    </div>
  );
}
