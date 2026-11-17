import React, { useEffect, useRef, useState } from 'react';
import {
  ArrowRight,
  CheckCircle2,
  FileText,
  Sparkles,
  Upload,
  X,
} from 'lucide-react';
import type { GameSummary } from '../../shared/types';
import { api } from '../lib/api';
import { cx, formatGameDate } from '../lib/chessFormat';
import { Eyebrow, Pill, SegmentedControl, Spinner } from './ui';

interface PastePgnModalProps {
  open: boolean;
  onClose: () => void;
  onImported: (games: GameSummary[]) => void;
  onViewLibrary?: () => void;
}

type PreferredSide = 'auto' | 'w' | 'b';

interface PgnPreset {
  id: string;
  label: string;
  detail: string;
  pgn: string;
}

const PRESETS: PgnPreset[] = [
  {
    id: 'scholar',
    label: "Scholar's Mate",
    detail: 'Chess.com-style headers · you are Black',
    pgn: `[Event "Opening Trap Study"]
[Site "Coach Training"]
[Date "2026.11.15"]
[White "Opponent"]
[Black "darrelnxt"]
[Result "1-0"]
[TimeControl "600"]
[ECO "C50"]

1. e4 e5 2. Qh5 Nc6 3. Bc4 Nf6 4. Qxf7# 1-0`,
  },
  {
    id: 'fools',
    label: "Fool's Mate",
    detail: 'Bare SAN move list · you are White',
    pgn: `1. f3 e5 2. g4 Qh4# 0-1`,
  },
  {
    id: 'legal',
    label: "Legal's Mate",
    detail: 'Longer tactical trap · auto-detects darrelnxt',
    pgn: `[Event "Legal's Mate Trap"]
[Site "Coach Training"]
[Date "2026.11.15"]
[White "Opponent"]
[Black "darrelnxt"]
[Result "1-0"]
[TimeControl "600"]
[ECO "C50"]

1. e4 e5 2. Nf3 Nc6 3. Bc4 d6 4. Nc3 Bg4 5. h3 Bh5 6. Nxe5 Bxd1 7. Bxf7+ Ke7 8. Nd5# 1-0`,
  },
];

export const PastePgnModal: React.FC<PastePgnModalProps> = ({
  open,
  onClose,
  onImported,
  onViewLibrary,
}) => {
  const [pgn, setPgn] = useState('');
  const [fileName, setFileName] = useState('');
  const [side, setSide] = useState<PreferredSide>('auto');
  const [playerHint, setPlayerHint] = useState('darrelnxt');
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [imported, setImported] = useState<GameSummary[] | null>(null);
  const fileInputRef = useRef<HTMLInputElement | null>(null);

  useEffect(() => {
    if (!open) return;
    const previousOverflow = document.body.style.overflow;
    document.body.style.overflow = 'hidden';
    const onKeyDown = (event: KeyboardEvent) => {
      if (event.key === 'Escape' && !busy) onClose();
    };
    window.addEventListener('keydown', onKeyDown);
    return () => {
      document.body.style.overflow = previousOverflow;
      window.removeEventListener('keydown', onKeyDown);
    };
  }, [open, busy, onClose]);

  const loadPreset = (preset: PgnPreset) => {
    setPgn(preset.pgn);
    setFileName(`${preset.label} preset`);
    setSide('auto');
    setPlayerHint('darrelnxt');
    setImported(null);
    setError(null);
  };

  const handleFile = async (file: File | undefined) => {
    if (!file) return;
    try {
      const text = await file.text();
      setPgn(text);
      setFileName(file.name);
      setImported(null);
      setError(null);
    } catch {
      setError('Could not read that file. Try a plain .pgn or .txt file.');
    }
  };

  const submit = async () => {
    if (!pgn.trim()) {
      setError('Paste a PGN, upload a .pgn file, or choose a sample first.');
      return;
    }
    setBusy(true);
    setError(null);
    setImported(null);
    try {
      const result = await api.importPgn(pgn, side, playerHint.trim() || 'darrelnxt');
      setImported(result.games);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Import failed.');
    } finally {
      setBusy(false);
    }
  };

  if (!open) return null;

  return (
    <div className="fixed inset-0 z-[100] flex items-center justify-center bg-[var(--surface-deep)]/55 p-3 backdrop-blur-md sm:p-6 animate-fade-in">
      <div
        role="dialog"
        aria-modal="true"
        aria-labelledby="pgn-modal-title"
        className="premium-card relative flex max-h-[92vh] w-full max-w-5xl flex-col overflow-hidden rounded-3xl border border-[var(--line)] animate-scale-in"
      >
        <div className="absolute inset-x-0 top-0 h-[3px] bg-gradient-to-r from-[var(--a-deep)] via-[var(--a2)] to-[var(--a-deep)]" />
        <div className="pointer-events-none absolute -left-20 -top-24 h-72 w-72 rounded-full bg-[var(--a)]/[0.07] blur-3xl" />
        <div className="pointer-events-none absolute -bottom-28 -right-16 h-72 w-72 rounded-full bg-[var(--cool)]/8 blur-3xl" />

        <header className="relative flex items-start justify-between gap-4 border-b border-[var(--line)] px-5 py-4 sm:px-7">
          <div>
            <Eyebrow>New study material</Eyebrow>
            <h2 id="pgn-modal-title" className="mt-1 font-display text-2xl font-semibold text-[var(--ink)] sm:text-3xl">
              Paste a new PGN
            </h2>
            <p className="mt-1 text-xs text-[var(--ink-muted)]">
              Stockfish 18 NNUE will analyze it live, then every real mistake becomes a blind drill.
            </p>
          </div>
          <button
            type="button"
            onClick={onClose}
            disabled={busy}
            className="flex h-9 w-9 shrink-0 items-center justify-center rounded-full border border-[var(--line)] text-[var(--ink-secondary)] transition hover:border-[var(--warm)]/50 hover:text-[var(--warm-soft)] disabled:opacity-40"
            aria-label="Close PGN import"
          >
            <X className="h-4 w-4" />
          </button>
        </header>

        <div className="relative grid min-h-0 flex-1 gap-5 overflow-y-auto px-5 py-5 sm:px-7 lg:grid-cols-[minmax(0,1fr)_290px]">
          <div className="flex min-w-0 flex-col gap-4">
            <div className="flex flex-wrap items-center justify-between gap-2">
              <div className="flex items-center gap-2">
                <button
                  type="button"
                  onClick={() => fileInputRef.current?.click()}
                  className="inline-flex items-center gap-1.5 rounded-lg border border-[var(--line)] bg-[var(--surface)] px-3 py-2 text-xs font-semibold text-[var(--ink-soft)] transition hover:border-[var(--a)]/50 hover:text-[var(--ink)]"
                >
                  <Upload className="h-3.5 w-3.5" /> Upload .pgn / .txt
                </button>
                <input
                  ref={fileInputRef}
                  type="file"
                  accept=".pgn,.txt,.chess,text/plain"
                  className="hidden"
                  onChange={(event) => void handleFile(event.target.files?.[0])}
                />
                {fileName && (
                  <Pill className="border-[var(--cool)]/25 bg-[var(--cool-bg)] text-[var(--cool)]">
                    <FileText className="h-3 w-3" /> {fileName}
                  </Pill>
                )}
              </div>
              <span className="font-mono-tabular text-[10px] text-[var(--ink-muted)]">
                {pgn.trim() ? `${pgn.trim().split(/\s+/).length} tokens` : 'Multi-game PGN supported'}
              </span>
            </div>

            <textarea
              value={pgn}
              onChange={(event) => {
                setPgn(event.target.value);
                setImported(null);
                setError(null);
              }}
              spellCheck={false}
              placeholder={`[Event "My Game"]\n[White "darrelnxt"]\n[Black "Opponent"]\n[Result "1-0"]\n\n1. e4 e5 2. Nf3 Nc6 3. Bb5 a6 ...`}
              className="min-h-[260px] w-full resize-y rounded-xl border border-[var(--line)] bg-[var(--surface)] p-4 font-mono-tabular text-[12px] leading-relaxed text-[var(--ink-soft)] outline-none transition placeholder:text-[var(--ink-dim)] focus:border-[var(--a)]/55 focus:ring-2 focus:ring-[var(--a)]/10"
            />

            {error && (
              <div className="rounded-lg border border-[var(--warm)]/25 bg-[var(--warm-bg)] px-3 py-2 text-xs text-[var(--warm-soft)]">
                {error}
              </div>
            )}

            {imported && (
              <div className="rounded-xl border border-[var(--cool)]/25 bg-[var(--cool-bg)] p-3">
                <p className="flex items-center gap-1.5 text-sm font-semibold text-[var(--cool)]">
                  <CheckCircle2 className="h-4 w-4" />
                  {imported.length} {imported.length === 1 ? 'game' : 'games'} imported
                </p>
                <div className="mt-2 max-h-24 space-y-1 overflow-y-auto">
                  {imported.map((game) => (
                    <p key={game.id} className="truncate text-[11px] text-[var(--cool-soft)]">
                      {game.white} vs {game.black} · {formatGameDate(game.date)} · {game.moveCount} moves
                    </p>
                  ))}
                </div>
                <div className="mt-3 flex flex-wrap gap-2">
                  <button
                    type="button"
                    onClick={() => onImported(imported)}
                    className="inline-flex items-center gap-1.5 rounded-lg bg-[var(--a)] px-3 py-2 text-xs font-bold text-[#0a0714] transition hover:bg-[var(--a-hover)]"
                  >
                    Train first game <ArrowRight className="h-3.5 w-3.5" />
                  </button>
                  {onViewLibrary && (
                    <button
                      type="button"
                      onClick={onViewLibrary}
                      className="rounded-lg border border-[var(--line)] bg-[var(--surface)]/70 px-3 py-2 text-xs font-semibold text-[var(--ink-soft)] transition hover:border-[var(--a)]/50"
                    >
                      View in library
                    </button>
                  )}
                </div>
              </div>
            )}
          </div>

          <aside className="flex flex-col gap-4">
            <div className="rounded-xl border border-[var(--line)] bg-[var(--surface)]/80 p-3.5">
              <p className="mb-2 text-[10px] font-semibold uppercase tracking-[0.16em] text-[var(--ink-secondary)]">
                Which side did you play?
              </p>
              <SegmentedControl<PreferredSide>
                value={side}
                onChange={setSide}
                size="sm"
                className="w-full [&>button]:flex-1"
                options={[
                  { value: 'auto', label: 'Auto', hint: 'Detect using the player name below' },
                  { value: 'w', label: 'White', hint: 'Analyze White as you' },
                  { value: 'b', label: 'Black', hint: 'Analyze Black as you' },
                ]}
              />
              <label className="mt-3 block text-[10px] font-semibold uppercase tracking-[0.14em] text-[var(--ink-secondary)]">
                Your name for auto-detect
                <input
                  value={playerHint}
                  onChange={(event) => setPlayerHint(event.target.value)}
                  className="mt-1.5 w-full rounded-lg border border-[var(--line)] bg-[var(--surface-soft)] px-3 py-2 text-xs font-normal normal-case tracking-normal text-[var(--ink-soft)] outline-none focus:border-[var(--a)]/50"
                  placeholder="darrelnxt"
                />
              </label>
              <p className="mt-2 text-[10px] leading-relaxed text-[var(--ink-muted)]">
                Only the side you played is scored. Pasted games are saved as custom games and can be drilled later.
              </p>
            </div>

            <div className="rounded-xl border border-[var(--line)] bg-[var(--surface)]/80 p-3.5">
              <p className="mb-2 flex items-center gap-1.5 text-[10px] font-semibold uppercase tracking-[0.16em] text-[var(--ink-secondary)]">
                <Sparkles className="h-3 w-3 text-[var(--a)]" /> Try a sample
              </p>
              <div className="space-y-1.5">
                {PRESETS.map((preset) => (
                  <button
                    key={preset.id}
                    type="button"
                    onClick={() => loadPreset(preset)}
                    className={cx(
                      'w-full rounded-lg border px-3 py-2 text-left transition',
                      fileName === `${preset.label} preset`
                        ? 'border-[var(--a)]/50 bg-[var(--a-soft)]'
                        : 'border-[var(--line)] bg-[var(--surface)] hover:border-[var(--a)]/40'
                    )}
                  >
                    <p className="text-xs font-semibold text-[var(--ink-soft)]">{preset.label}</p>
                    <p className="mt-0.5 text-[10px] text-[var(--ink-muted)]">{preset.detail}</p>
                  </button>
                ))}
              </div>
            </div>
          </aside>
        </div>

        <footer className="relative flex items-center justify-between gap-3 border-t border-[var(--line)] bg-[var(--surface)] px-5 py-3.5 sm:px-7">
          <p className="hidden text-[11px] text-[var(--ink-muted)] sm:block">
            Best moves stay hidden until a drill is failed.
          </p>
          <div className="ml-auto flex items-center gap-2">
            <button
              type="button"
              onClick={onClose}
              disabled={busy}
              className="rounded-lg border border-[var(--line)] bg-[var(--surface)]/70 px-4 py-2.5 text-xs font-semibold text-[var(--ink-soft)] transition hover:text-[var(--ink)] disabled:opacity-40"
            >
              Cancel
            </button>
            <button
              type="button"
              onClick={() => void submit()}
              disabled={busy}
              className="inline-flex min-w-[150px] items-center justify-center gap-2 rounded-lg bg-[var(--a)] px-4 py-2.5 text-xs font-bold text-[#0a0714] transition hover:bg-[var(--a-hover)] disabled:opacity-60"
            >
              {busy ? <><Spinner /> Importing…</> : <>Import &amp; Analyze <ArrowRight className="h-3.5 w-3.5" /></>}
            </button>
          </div>
        </footer>
      </div>
    </div>
  );
};
