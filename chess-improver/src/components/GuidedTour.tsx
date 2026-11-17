import React, { useEffect, useLayoutEffect, useRef, useState } from 'react';
import {
  ArrowLeft,
  ArrowRight,
  BookOpen,
  Compass,
  EyeOff,
  MousePointer2,
  Rocket,
  Sparkles,
  Upload,
  X,
} from 'lucide-react';
import { ProgressBar } from './ui';

export const TOUR_STORAGE_KEY = 'chess-improver.guided-tour.v2';

export type TourView = 'plan' | 'coach' | 'vault' | 'library';

interface TourStep {
  view: TourView;
  eyebrow: string;
  title: string;
  body: string;
  icon: React.ReactNode;
  /** First available element wins, so the tour still works while a view is loading. */
  targets: string[];
}

const TOUR_STEPS: TourStep[] = [
  {
    view: 'plan',
    eyebrow: 'Home · your map',
    title: 'Begin with the violet button',
    body: 'Home ranks your next blind drill from the full archive. The violet “Start session” button opens the highest-priority position — that is the main place to click.',
    icon: <Compass className="h-5 w-5" />,
    targets: [
      '[data-tour="start-training"]',
      '[data-tour="quick-guide"]',
      '[data-tour="nav-plan"]',
    ],
  },
  {
    view: 'coach',
    eyebrow: 'Coach · your answer',
    title: 'Move a piece on the board',
    body: 'Click one of your pieces, then click a target square — or drag the piece. The board is where you submit a better move. Hints are theme-only and never name the answer.',
    icon: <MousePointer2 className="h-5 w-5" />,
    targets: [
      '[data-tour="coach-board"]',
      '[data-tour="coach-guide"]',
      '[data-tour="nav-coach"]',
    ],
  },
  {
    view: 'vault',
    eyebrow: 'Mistake Vault · recall',
    title: 'Repeat until it sticks',
    body: 'Every unsolved position returns here. Use “Train due” for a cross-game queue; solving a mistake cleanly on two separate blind recalls moves it toward mastered.',
    icon: <Sparkles className="h-5 w-5" />,
    targets: [
      '[data-tour="vault-train"]',
      '[data-tour="vault-queue"]',
      '[data-tour="nav-vault"]',
    ],
  },
  {
    view: 'library',
    eyebrow: 'New games · any time',
    title: 'Paste a PGN to analyze it',
    body: 'Use the top-right Paste PGN button (also inside Library) to add a game. Stockfish 18 NNUE still supplies all chess knowledge locally; an optional server-side Gemini key only selects a topic; all coach answers are generated locally.',
    icon: <Upload className="h-5 w-5" />,
    targets: [
      '[data-tour="paste-pgn"]',
      '[data-tour="library-pgn"]',
      '[data-tour="nav-library"]',
    ],
  },
  {
    view: 'plan',
    eyebrow: 'The no-spoiler rule',
    title: 'Fail first, reveal second',
    body: 'The best move stays hidden during the blind challenge and any retry with attempts left. Only after your final failed attempt does the app reveal Stockfish’s answer and let you practice it.',
    icon: <EyeOff className="h-5 w-5" />,
    targets: [
      '[data-tour="quick-guide"]',
      '[data-tour="nav-plan"]',
    ],
  },
];

interface GuidedTourProps {
  open: boolean;
  onClose: () => void;
  onNavigate: (view: TourView) => void;
}

export const GuidedTour: React.FC<GuidedTourProps> = ({ open, onClose, onNavigate }) => {
  const [step, setStep] = useState(0);
  const [rect, setRect] = useState<DOMRect | null>(null);
  const [targetReady, setTargetReady] = useState(false);
  const [viewport, setViewport] = useState(() => ({
    width: typeof window === 'undefined' ? 1280 : window.innerWidth,
    height: typeof window === 'undefined' ? 800 : window.innerHeight,
  }));
  const nextRef = useRef<HTMLButtonElement | null>(null);
  const navigateRef = useRef(onNavigate);
  const closeRef = useRef(onClose);

  useEffect(() => {
    navigateRef.current = onNavigate;
  }, [onNavigate]);

  useEffect(() => {
    closeRef.current = onClose;
  }, [onClose]);

  useEffect(() => {
    if (open) setStep(0);
  }, [open]);

  useEffect(() => {
    if (!open) return;
    const onKey = (event: KeyboardEvent) => {
      if (event.key === 'Escape') closeRef.current();
      if (event.key === 'ArrowRight' && step < TOUR_STEPS.length - 1) {
        setStep((current) => Math.min(current + 1, TOUR_STEPS.length - 1));
      }
      if (event.key === 'ArrowLeft' && step > 0) {
        setStep((current) => Math.max(current - 1, 0));
      }
    };
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  }, [open, step]);

  useEffect(() => {
    if (!open || !targetReady) return;
    const frame = window.requestAnimationFrame(() => nextRef.current?.focus());
    return () => window.cancelAnimationFrame(frame);
  }, [open, step, targetReady]);

  useLayoutEffect(() => {
    if (!open) return;
    navigateRef.current(TOUR_STEPS[step].view);
    setTargetReady(false);

    let cancelled = false;
    let raf = 0;
    let settleInterval = 0;
    let lateTimer = 0;
    let finalTimer = 0;
    let readyTimer = 0;
    let readyDelay = 0;
    let attempts = 0;
    let target: Element | null = null;

    const measure = () => {
      if (cancelled || !target) return;
      const next = target.getBoundingClientRect();
      setRect((previous) =>
        previous &&
        Math.abs(previous.top - next.top) < 1 &&
        Math.abs(previous.left - next.left) < 1 &&
        Math.abs(previous.width - next.width) < 1 &&
        Math.abs(previous.height - next.height) < 1
          ? previous
          : next,
      );
    };

    const trackSettling = () => {
      window.clearInterval(settleInterval);
      settleInterval = window.setInterval(measure, 32);
    };

    // Wait for the page's fonts and first layout pass to settle before painting
    // the spotlight, so its cutout never lags behind the highlighted control.
    const revealAfterLayout = () => {
      window.clearTimeout(readyDelay);
      readyDelay = window.setTimeout(() => {
        if (!cancelled) setTargetReady(true);
      }, 220);
    };

    const find = () => {
      if (cancelled) return;
      window.cancelAnimationFrame(raf);

      const selectors = TOUR_STEPS[step].targets;
      const preferred = selectors[0]
        ? document.querySelector(selectors[0])
        : null;
      const fallback = selectors
        .map((selector) => document.querySelector(selector))
        .find((element): element is Element => Boolean(element)) ?? null;

      // Give the primary target a brief chance to mount before falling back,
      // so the spotlight never jumps between a nav item and the real control.
      if (!preferred && fallback && attempts < 24) {
        attempts += 1;
        raf = window.requestAnimationFrame(find);
        return;
      }

      const previousTarget = target;
      target = preferred ?? fallback;
      if (!target) {
        if (attempts < 40) {
          attempts += 1;
          raf = window.requestAnimationFrame(find);
        } else {
          setRect(null);
          revealAfterLayout();
        }
        return;
      }

      attempts = 0;
      revealAfterLayout();
      if (target !== previousTarget) {
        const initial = target.getBoundingClientRect();
        if (initial.top < 80 || initial.bottom > window.innerHeight - 80) {
          target.scrollIntoView({ block: 'center', behavior: 'smooth' });
        }
      }
      measure();
      trackSettling();
    };

    const onViewportChange = () => {
      setViewport({ width: window.innerWidth, height: window.innerHeight });
      measure();
    };

    find();
    lateTimer = window.setTimeout(find, 350);
    finalTimer = window.setTimeout(find, 800);
    readyTimer = window.setTimeout(() => {
      if (!cancelled) {
        setTargetReady(true);
        find();
      }
    }, 1000);
    window.addEventListener('resize', onViewportChange);
    window.addEventListener('scroll', onViewportChange, true);

    return () => {
      cancelled = true;
      window.cancelAnimationFrame(raf);
      window.clearInterval(settleInterval);
      window.clearTimeout(lateTimer);
      window.clearTimeout(finalTimer);
      window.clearTimeout(readyTimer);
      window.clearTimeout(readyDelay);
      window.removeEventListener('resize', onViewportChange);
      window.removeEventListener('scroll', onViewportChange, true);
    };
  }, [open, step]);

  if (!open || !targetReady) return null;

  const current = TOUR_STEPS[step];
  const isLast = step === TOUR_STEPS.length - 1;
  const narrow = viewport.width < 640;
  const cardWidth = 380;
  const cardHeight = 350;
  let cardStyle: React.CSSProperties;

  if (narrow) {
    cardStyle = {
      left: 12,
      right: 12,
      bottom: 12,
      width: 'auto',
      zIndex: 20,
    };
  } else {
    const clamp = (value: number, min: number, max: number) => Math.max(min, Math.min(max, value));
    const fitsBelow = rect ? rect.bottom + 18 + cardHeight <= viewport.height - 16 : false;
    const fitsAbove = rect ? rect.top - 18 - cardHeight >= 16 : false;
    const rightGutter = rect ? viewport.width - rect.right - 16 : 0;
    const leftGutter = rect ? rect.left - 16 : 0;
    const canPlaceRight = rightGutter >= cardWidth + 18;
    const canPlaceLeft = leftGutter >= cardWidth + 18;

    // Large targets (the chessboard) get a side gutter so the card never covers
    // the very control the step is explaining.
    if (rect && !fitsBelow && !fitsAbove && (canPlaceRight || canPlaceLeft)) {
      const left = canPlaceRight ? rect.right + 18 : rect.left - cardWidth - 18;
      const top = clamp(
        rect.top + rect.height / 2 - cardHeight / 2,
        16,
        viewport.height - cardHeight - 16,
      );
      cardStyle = { top, left, width: cardWidth, zIndex: 20 };
    } else {
      let top = rect ? rect.bottom + 18 : (viewport.height - cardHeight) / 2;
      if (top + cardHeight > viewport.height - 16) {
        top = rect ? rect.top - cardHeight - 18 : (viewport.height - cardHeight) / 2;
      }
      if (top < 16) top = Math.max(16, (viewport.height - cardHeight) / 2);
      const left = rect
        ? clamp(rect.left + rect.width / 2 - cardWidth / 2, 16, viewport.width - cardWidth - 16)
        : (viewport.width - cardWidth) / 2;
      cardStyle = { top, left, width: cardWidth, zIndex: 20 };
    }
  }

  const handleNext = () => {
    if (isLast) onClose();
    else setStep((currentStep) => currentStep + 1);
  };

  return (
    <div className="fixed inset-0 z-[150]" role="dialog" aria-modal="true" aria-label="Guided tour">
      {rect ? (
        <div
          className="pointer-events-none absolute animate-fade-in"
          style={{
            top: Math.max(4, rect.top - 7),
            left: Math.max(4, rect.left - 7),
            width: Math.max(20, rect.width + 14),
            height: Math.max(20, rect.height + 14),
            borderRadius: 18,
            background: 'transparent',
            boxShadow:
              '0 0 0 9999px rgba(6, 5, 10, 0.78), 0 0 0 2px rgba(139, 124, 255, 0.9), 0 0 34px rgba(139, 124, 255, 0.35)',
            zIndex: 1,
          }}
        />
      ) : (
        <div
          className="absolute inset-0"
          style={{
            backgroundColor: 'rgba(6, 5, 10, 0.72)',
            zIndex: 1,
          }}
        />
      )}

      <div className="absolute animate-scale-in" style={cardStyle}>
        <div className="premium-card relative overflow-hidden rounded-2xl border border-[var(--line)] p-5 backdrop-blur-xl">
          <div className="absolute inset-x-0 top-0 h-[3px] bg-gradient-to-r from-[var(--a-deep)] via-[var(--a2)] to-[var(--a-deep)]" />
          <div className="flex items-start justify-between gap-3">
            <div className="flex h-10 w-10 items-center justify-center rounded-xl border border-[var(--a-deep)] bg-[var(--a)] text-[#0a0714] animate-ring-glow">
              {current.icon}
            </div>
            <button
              type="button"
              onClick={onClose}
              className="flex h-8 w-8 items-center justify-center rounded-lg border border-[var(--line)] text-[var(--ink-muted)] transition hover:border-[var(--a)]/40 hover:text-[var(--ink)]"
              title="Close tour"
              aria-label="Close tour"
            >
              <X className="h-4 w-4" />
            </button>
          </div>

          <p className="mt-4 text-[10px] font-bold uppercase tracking-[0.18em] text-[var(--a)]">
            {current.eyebrow}
          </p>
          <h2 className="mt-1.5 font-display text-xl font-semibold leading-tight text-[var(--ink)]">
            {current.title}
          </h2>
          <p className="mt-2 text-[12px] leading-relaxed text-[var(--ink-secondary)]">{current.body}</p>

          <div className="mt-4">
            <ProgressBar value={((step + 1) / TOUR_STEPS.length) * 100} />
            <div className="mt-2 flex items-center justify-between gap-2">
              <span className="font-mono-tabular text-[9px] uppercase tracking-widest text-[var(--ink-muted)]">
                Step {step + 1} of {TOUR_STEPS.length}
              </span>
              <div className="flex items-center gap-1.5" aria-label="Tour steps">
                {TOUR_STEPS.map((tourStep, index) => (
                  <button
                    key={tourStep.eyebrow}
                    type="button"
                    onClick={() => setStep(index)}
                    title={`Go to step ${index + 1}`}
                    aria-label={`Go to step ${index + 1}`}
                    className={`h-1.5 rounded-full transition-all duration-300 ${
                      index === step
                        ? 'w-5 bg-[var(--a)]'
                        : 'w-1.5 bg-[var(--surface-soft)] hover:bg-[var(--a2)]/50'
                    }`}
                  />
                ))}
              </div>
            </div>
          </div>

          <div className="mt-4 flex items-center justify-between gap-2 border-t border-[var(--line)] pt-3">
            <button
              type="button"
              onClick={onClose}
              className="text-[11px] font-semibold text-[var(--ink-secondary)] transition hover:text-[var(--ink)]"
            >
              Skip tour
            </button>
            <div className="flex items-center gap-2">
              <button
                type="button"
                onClick={() => setStep((currentStep) => Math.max(0, currentStep - 1))}
                disabled={step === 0}
                className="inline-flex items-center gap-1 rounded-lg border border-[var(--line)] bg-[var(--surface)]/70 px-3 py-2 text-[11px] font-semibold text-[var(--ink-soft)] transition hover:border-[var(--a)]/45 disabled:opacity-35"
              >
                <ArrowLeft className="h-3.5 w-3.5" /> Back
              </button>
              <button
                ref={nextRef}
                type="button"
                onClick={handleNext}
                className="inline-flex items-center gap-1.5 rounded-lg bg-[var(--a)] px-3.5 py-2 text-[11px] font-bold text-[#0a0714] transition hover:bg-[var(--a-hover)] tap-scale"
              >
                {isLast ? (
                  <>
                    <Rocket className="h-3.5 w-3.5" /> Finish
                  </>
                ) : (
                  <>
                    Next <ArrowRight className="h-3.5 w-3.5" />
                  </>
                )}
              </button>
            </div>
          </div>

          <p className="mt-3 flex items-center gap-1.5 text-[9px] uppercase tracking-wider text-[var(--ink-muted)]">
            <BookOpen className="h-3 w-3" /> Reopen any time with the ? button
          </p>
        </div>
      </div>
    </div>
  );
};
