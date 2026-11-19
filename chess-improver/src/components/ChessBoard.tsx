import React, { useEffect, useMemo, useRef, useState } from 'react';
import { Chess, PieceSymbol, Square } from 'chess.js';
import { PieceSvg } from './PieceSvg';
import type { PlayerColor } from '../../shared/types';

export type BoardThemeName = 'walnut' | 'slate' | 'emerald';

export interface BoardArrow {
  from: string;
  to: string;
  kind: 'best' | 'game_mistake' | 'refutation' | 'attempt';
}

export interface SquareBadge {
  square: string;
  glyph: string;
  bgColor: string;
}

interface ChessBoardProps {
  fen: string;
  orientation: PlayerColor;
  interactive: boolean;
  allowedTurnColor?: PlayerColor;
  theme?: BoardThemeName;
  lastMove?: { from: string; to: string } | null;
  arrows?: BoardArrow[];
  badge?: SquareBadge | null;
  nudgeSquare?: string | null;
  /** Non-spoiling visual scan shown only after the player asks for a hint. */
  hintActive?: boolean;
  onMoveAttempt?: (uci: string) => void;
}

const THEMES: Record<
  BoardThemeName,
  { light: string; dark: string; lastLight: string; lastDark: string; coordLight: string; coordDark: string; border: string }
> = {
  // Violet — the Coach default, tuned for the dark glass shell.
  walnut: {
    light: '#c9c3d8',
    dark: '#51467d',
    lastLight: '#b9a8f5',
    lastDark: '#675a99',
    coordLight: '#6f5fe6',
    coordDark: '#f3f1f8',
    border: '#0c0a13',
  },
  // Midnight — cool, quiet alternative.
  slate: {
    light: '#aeb6cf',
    dark: '#3c4566',
    lastLight: '#c9d2ee',
    lastDark: '#58638c',
    coordLight: '#1b5d7a',
    coordDark: '#f3f1f8',
    border: '#06050a',
  },
  // Linen — warm neutral alternative.
  emerald: {
    light: '#d8d1c2',
    dark: '#8d806a',
    lastLight: '#ebe1c8',
    lastDark: '#a89a7e',
    coordLight: '#6b5f47',
    coordDark: '#f3f1f8',
    border: '#0c0a13',
  },
};

const FILES = ['a', 'b', 'c', 'd', 'e', 'f', 'g', 'h'];
const RANKS = ['8', '7', '6', '5', '4', '3', '2', '1'];

function squareToBoardXY(square: string, orientation: PlayerColor): { col: number; row: number } {
  const fileIdx = FILES.indexOf(square[0]);
  const rankNum = parseInt(square[1], 10); // 1..8
  if (orientation === 'w') {
    return { col: fileIdx, row: 8 - rankNum };
  }
  return { col: 7 - fileIdx, row: rankNum - 1 };
}

export const ChessBoard: React.FC<ChessBoardProps> = ({
  fen,
  orientation,
  interactive,
  allowedTurnColor,
  theme = 'walnut',
  lastMove,
  arrows = [],
  badge,
  nudgeSquare,
  hintActive = false,
  onMoveAttempt,
}) => {
  const palette = THEMES[theme];
  const boardRef = useRef<HTMLDivElement | null>(null);
  const dragRef = useRef<typeof dragState>(null);
  const floatingRef = useRef<HTMLDivElement | null>(null);

  const [selectedSquare, setSelectedSquare] = useState<string | null>(null);
  const [focusedSquare, setFocusedSquare] = useState<string | null>(null);
  const [pendingPromotion, setPendingPromotion] = useState<{ from: string; to: string } | null>(
    null
  );
  const [dragState, setDragState] = useState<{
    from: string;
    piece: PieceSymbol;
    color: PlayerColor;
    x: number;
    y: number;
    startX: number;
    startY: number;
    moved: boolean;
  } | null>(null);

  // Reset transient board interaction whenever the displayed position changes.
  useEffect(() => {
    setSelectedSquare(null);
    setPendingPromotion(null);
    dragRef.current = null;
    setDragState(null);
  }, [fen]);

  const chess = useMemo(() => {
    try {
      return new Chess(fen);
    } catch {
      return new Chess();
    }
  }, [fen]);

  const turn = chess.turn() as PlayerColor;
  const canInteractNow =
    interactive && (!allowedTurnColor || allowedTurnColor === turn) && !chess.isGameOver();

  // Compute legal destinations from selectedSquare (or drag origin)
  const activeSourceSquare = dragState?.from ?? selectedSquare;
  const legalTargets = useMemo(() => {
    const map = new Map<string, { isCapture: boolean; isPromotion: boolean }>();
    if (!canInteractNow || !activeSourceSquare) return map;
    try {
      const moves = chess.moves({ square: activeSourceSquare as Square, verbose: true });
      for (const m of moves) {
        map.set(m.to, {
          isCapture: Boolean(m.captured) || m.flags.includes('e'),
          isPromotion: Boolean(m.promotion),
        });
      }
    } catch {
      // ignore
    }
    return map;
  }, [chess, canInteractNow, activeSourceSquare]);

  // Locate king square if in check
  const checkedKingSquare = useMemo(() => {
    if (!chess.inCheck()) return null;
    const grid = chess.board();
    for (let r = 0; r < 8; r++) {
      for (let c = 0; c < 8; c++) {
        const cell = grid[r][c];
        if (cell && cell.type === 'k' && cell.color === turn) {
          return cell.square;
        }
      }
    }
    return null;
  }, [chess, turn]);

  const displayFiles = orientation === 'w' ? FILES : [...FILES].reverse();
  const displayRanks = orientation === 'w' ? RANKS : [...RANKS].reverse();

  const tryExecuteMove = (from: string, to: string) => {
    if (!canInteractNow) return false;
    const moves = chess.moves({ square: from as Square, verbose: true });
    const matching = moves.filter((m) => m.to === to);
    if (matching.length === 0) return false;

    if (matching.some((m) => m.promotion)) {
      setPendingPromotion({ from, to });
      setSelectedSquare(null);
      return true;
    }

    setSelectedSquare(null);
    onMoveAttempt?.(`${from}${to}`);
    return true;
  };

  const getSquareFromClientCoords = (clientX: number, clientY: number): string | null => {
    const el = boardRef.current;
    if (!el) return null;
    const rect = el.getBoundingClientRect();
    if (
      clientX < rect.left ||
      clientX > rect.right ||
      clientY < rect.top ||
      clientY > rect.bottom
    ) {
      return null;
    }
    const col = Math.min(7, Math.max(0, Math.floor(((clientX - rect.left) / rect.width) * 8)));
    const row = Math.min(7, Math.max(0, Math.floor(((clientY - rect.top) / rect.height) * 8)));
    const file = displayFiles[col];
    const rank = displayRanks[row];
    return `${file}${rank}`;
  };

  const handleSquarePointerDown = (
    e: React.PointerEvent<HTMLButtonElement>,
    sq: string,
    cell: { type: PieceSymbol; color: PlayerColor } | null
  ) => {
    if (!canInteractNow || pendingPromotion) return;

    // If a source square is already selected and user clicks a legal target square, execute right away!
    if (selectedSquare && selectedSquare !== sq && legalTargets.has(sq)) {
      e.preventDefault();
      tryExecuteMove(selectedSquare, sq);
      return;
    }

    if (cell && cell.color === turn) {
      e.currentTarget.setPointerCapture?.(e.pointerId);
      const rect = boardRef.current?.getBoundingClientRect();
      const x = rect ? e.clientX - rect.left : 0;
      const y = rect ? e.clientY - rect.top : 0;
      const nextDrag = {
        from: sq,
        piece: cell.type,
        color: cell.color,
        x,
        y,
        startX: e.clientX,
        startY: e.clientY,
        moved: false,
      };
      dragRef.current = nextDrag;
      setDragState(nextDrag);
    } else {
      setSelectedSquare(null);
    }
  };

  const handleBoardPointerMove = (e: React.PointerEvent<HTMLDivElement>) => {
    const drag = dragRef.current;
    if (!drag || !boardRef.current) return;
    const rect = boardRef.current.getBoundingClientRect();
    const moved = drag.moved || Math.hypot(e.clientX - drag.startX, e.clientY - drag.startY) >= 6;
    dragRef.current = { ...drag, x: e.clientX - rect.left, y: e.clientY - rect.top, moved };
    // Render only once when dragging begins; subsequent pointer events update
    // the floating piece directly instead of re-rendering all 64 squares.
    if (moved && !drag.moved) setDragState(dragRef.current);
    if (floatingRef.current) {
      floatingRef.current.style.left = `${e.clientX - rect.left}px`;
      floatingRef.current.style.top = `${e.clientY - rect.top}px`;
    }
  };

  const handleBoardPointerUp = (e: React.PointerEvent<HTMLDivElement>) => {
    const drag = dragRef.current;
    if (!drag) return;
    const dropSq = getSquareFromClientCoords(e.clientX, e.clientY);
    const wasDrag = drag.moved;
    const originSq = drag.from;
    dragRef.current = null;
    setDragState(null);

    if (wasDrag && dropSq && dropSq !== originSq) {
      const ok = tryExecuteMove(originSq, dropSq);
      if (!ok) {
        setSelectedSquare(originSq);
      }
    } else {
      // Treated as a click! Toggle selection
      setSelectedSquare((prev) => (prev === originSq ? null : originSq));
    }
  };

  const handleBoardPointerCancel = () => {
    // A cancelled pointer has no reliable coordinates; never treat it as a drop.
    dragRef.current = null;
    setDragState(null);
  };

  return (
    <div
      className="relative aspect-square w-full select-none rounded-[10px] p-[5px] shadow-[0_18px_48px_rgba(0, 0, 0, 0.165)] animate-scale-in transition-shadow duration-300 hover:shadow-[0_22px_58px_rgba(0, 0, 0, 0.186)]"
      style={{
        background: palette.border,
        border: '1px solid rgba(255, 255, 255, 0.14)',
      }}
    >
      <div
        ref={boardRef}
        onPointerMove={handleBoardPointerMove}
        onPointerUp={handleBoardPointerUp}
        onPointerCancel={handleBoardPointerCancel}
        role="group"
        aria-label="Chess board. Use arrow keys to move between squares, and Enter or Space to select a piece or destination."
        className="relative grid h-full w-full grid-cols-8 grid-rows-8 overflow-hidden rounded-[6px] touch-none"
      >
        {displayRanks.map((rank, rowIdx) =>
          displayFiles.map((file, colIdx) => {
            const sq = `${file}${rank}` as Square;
            // a1 is dark: even file-index + rank sums are light squares.
            const isLight = (FILES.indexOf(file) + parseInt(rank, 10)) % 2 === 0;
            const isLastMove = lastMove?.from === sq || lastMove?.to === sq;
            const isSelected = activeSourceSquare === sq;
            const targetMeta = legalTargets.get(sq);
            const cell = chess.get(sq) || null;
            const isKingChecked = checkedKingSquare === sq;
            const isNudged = nudgeSquare?.toLowerCase() === sq;

            let bg = isLight ? palette.light : palette.dark;
            if (isLastMove) {
              bg = isLight ? palette.lastLight : palette.lastDark;
            }

            const isDraggedOrigin = dragState?.moved && dragState.from === sq;

            return (
              <button
                type="button"
                key={sq}
                data-square={sq}
                aria-label={`${sq}${cell ? ` ${cell.color === 'w' ? 'white' : 'black'} ${{ p: 'pawn', n: 'knight', b: 'bishop', r: 'rook', q: 'queen', k: 'king' }[cell.type]}` : ' empty'}${isSelected ? ', selected' : ''}${targetMeta ? ', legal destination' : ''}`}
                aria-pressed={isSelected}
                tabIndex={canInteractNow && (focusedSquare ? focusedSquare === sq : rowIdx === 0 && colIdx === 0) ? 0 : -1}
                onFocus={() => setFocusedSquare(sq)}
                onKeyDown={(e) => {
                  const direction: Record<string, [number, number]> = { ArrowLeft: [0, -1], ArrowRight: [0, 1], ArrowUp: [-1, 0], ArrowDown: [1, 0] };
                  if (e.key === 'Escape') { setSelectedSquare(null); return; }
                  const delta = direction[e.key];
                  if (!delta) return;
                  e.preventDefault();
                  const row = Math.max(0, Math.min(7, rowIdx + delta[0]));
                  const col = Math.max(0, Math.min(7, colIdx + delta[1]));
                  const next = `${displayFiles[col]}${displayRanks[row]}`;
                  setFocusedSquare(next);
                  boardRef.current?.querySelector<HTMLElement>(`[data-square="${next}"]`)?.focus();
                }}
                onClick={(e) => {
                  // Pointer actions are handled on pointer down/up. Keyboard
                  // activation has detail zero and follows the same legal rules.
                  if (e.detail !== 0 || !canInteractNow || pendingPromotion) return;
                  if (selectedSquare && selectedSquare !== sq && legalTargets.has(sq)) tryExecuteMove(selectedSquare, sq);
                  else if (cell && cell.color === turn) setSelectedSquare(selectedSquare === sq ? null : sq);
                  else setSelectedSquare(null);
                }}
                onPointerDown={(e) =>
                  handleSquarePointerDown(
                    e,
                    sq,
                    cell ? { type: cell.type, color: cell.color as PlayerColor } : null
                  )
                }
                className={`relative flex items-center justify-center transition-colors duration-300 ${
                  canInteractNow && ((cell && cell.color === turn) || targetMeta)
                    ? 'cursor-pointer'
                    : ''
                }`}
                style={{ backgroundColor: bg }}
              >
                {/* Selected square warm bronze highlight */}
                {isSelected && (
                  <div className="pointer-events-none absolute inset-0 bg-[var(--a)]/45 ring-2 ring-inset ring-[var(--a2)]/75" />
                )}

                {/* Piece Hint Nudge Ring (only when user clicked Hint!) */}
                {isNudged && (
                  <div className="pointer-events-none absolute inset-[3px] rounded-md ring-2 ring-[var(--cool)] bg-[var(--cool)]/20 animate-pulse" />
                )}

                {/* Checked King crimson radial alert */}
                {isKingChecked && (
                  <div
                    className="pointer-events-none absolute inset-0"
                    style={{
                      background:
                        'radial-gradient(circle, rgba(255, 107, 87, 0.85) 0%, rgba(255, 107, 87, 0.35) 55%, rgba(255, 107, 87, 0) 78%)',
                    }}
                  />
                )}

                {/* Rank label along left edge */}
                {colIdx === 0 && (
                  <span
                    className="pointer-events-none absolute left-1 top-0.5 text-[10px] font-semibold leading-none font-mono-tabular opacity-85"
                    style={{ color: isLight ? palette.coordLight : palette.coordDark }}
                  >
                    {rank}
                  </span>
                )}

                {/* File label along bottom edge */}
                {rowIdx === 7 && (
                  <span
                    className="pointer-events-none absolute bottom-0.5 right-1 text-[10px] font-semibold leading-none font-mono-tabular opacity-85"
                    style={{ color: isLight ? palette.coordLight : palette.coordDark }}
                  >
                    {file}
                  </span>
                )}

                {/* Chess Piece SVG */}
                {cell && (
                  <div
                    key={`${sq}-${cell.color}-${cell.type}`}
                    className={`h-[86%] w-[86%] animate-fade-in transition-transform duration-150 ${
                      isDraggedOrigin ? 'opacity-25 scale-95' : 'hover:scale-[1.03]'
                    }`}
                  >
                    <PieceSvg color={cell.color as PlayerColor} piece={cell.type} />
                  </div>
                )}

                {/* Legal target move dot / capture ring */}
                {targetMeta && !targetMeta.isCapture && (
                  <div className="pointer-events-none h-[26%] w-[26%] rounded-full bg-[var(--ink)]/32 shadow-inner" />
                )}
                {targetMeta && targetMeta.isCapture && (
                  <div className="pointer-events-none absolute inset-[6%] rounded-full border-[3.5px] border-[var(--a2)]/38" />
                )}

                {/* Tactical Square Classification Badge (e.g. ?, ??, ?!, ★) */}
                {badge && badge.square === sq && (
                  <div
                    className="pointer-events-none absolute -right-0.5 -top-0.5 z-20 flex h-[22px] min-w-[22px] items-center justify-center rounded-full px-1 text-[11px] font-bold text-[#0a0714] shadow-[0_2px_6px_rgba(0, 0, 0, 0.150)] ring-2 ring-[var(--a2)]"
                    style={{ backgroundColor: badge.bgColor }}
                  >
                    {badge.glyph}
                  </div>
                )}
              </button>
            );
          })
        )}

        {/* Tactical SVG Arrow Overlay */}
        {arrows.length > 0 && (
          <svg
            viewBox="0 0 800 800"
            className="pointer-events-none absolute inset-0 z-10 h-full w-full animate-arrow-in"
          >
            <defs>
              {[
                { id: 'arrow-best', color: '#4cc9f0' },
                { id: 'arrow-mistake', color: '#ff6b57' },
                { id: 'arrow-refutation', color: '#ff6b57' },
                { id: 'arrow-attempt', color: '#ffb340' },
              ].map((marker) => (
                <marker
                  key={marker.id}
                  id={marker.id}
                  viewBox="0 0 34 34"
                  markerUnits="userSpaceOnUse"
                  markerWidth="34"
                  markerHeight="34"
                  refX="28"
                  refY="17"
                  orient="auto"
                >
                  <polygon points="0 0, 34 17, 0 34" fill={marker.color} />
                </marker>
              ))}
            </defs>

            {arrows.map((arr, idx) => {
              const start = squareToBoardXY(arr.from, orientation);
              const end = squareToBoardXY(arr.to, orientation);
              const x1 = start.col * 100 + 50;
              const y1 = start.row * 100 + 50;
              const rawX2 = end.col * 100 + 50;
              const rawY2 = end.row * 100 + 50;

              const dx = rawX2 - x1;
              const dy = rawY2 - y1;
              const len = Math.hypot(dx, dy) || 1;
              // Pull back the line so the fixed-size arrowhead lands inside the target square.
              const pullback = 18;
              const x2 = rawX2 - (dx / len) * pullback;
              const y2 = rawY2 - (dy / len) * pullback;

              const strokeMap: Record<BoardArrow['kind'], { color: string; marker: string; dash?: string; opacity: number }> = {
                best: { color: '#4cc9f0', marker: 'url(#arrow-best)', opacity: 0.88 },
                game_mistake: {
                  color: '#ff6b57',
                  marker: 'url(#arrow-mistake)',
                  dash: '18 11',
                  opacity: 0.82,
                },
                refutation: {
                  color: '#ff6b57',
                  marker: 'url(#arrow-refutation)',
                  opacity: 0.78,
                },
                attempt: {
                  color: '#ffb340',
                  marker: 'url(#arrow-attempt)',
                  dash: '14 10',
                  opacity: 0.82,
                },
              };

              const style = strokeMap[arr.kind];
              return (
                <line
                  key={`${arr.from}-${arr.to}-${arr.kind}-${idx}`}
                  x1={x1}
                  y1={y1}
                  x2={x2}
                  y2={y2}
                  stroke={style.color}
                  strokeWidth={arr.kind === 'best' ? 18 : 14}
                  strokeLinecap="round"
                  strokeDasharray={style.dash}
                  markerEnd={style.marker}
                  opacity={style.opacity}
                />
              );
            })}
          </svg>
        )}

        {/* Non-spoiling hint scan: visual guidance only, never a square or move. */}
        {hintActive && (
          <div className="pointer-events-none absolute inset-0 z-20 overflow-hidden rounded-[6px] animate-fade-in">
            <div className="absolute inset-0 rounded-[6px] ring-2 ring-inset ring-[var(--cool)]/35 animate-pulse-soft" />
            <div className="absolute inset-x-0 top-0 h-1/4 bg-gradient-to-b from-transparent via-[var(--cool)]/20 to-transparent animate-board-scan" />
            <div className="absolute bottom-2 left-1/2 -translate-x-1/2 whitespace-nowrap rounded-full border border-[var(--cool)]/35 bg-[var(--surface)]/85 px-2.5 py-1 text-[8px] font-bold uppercase tracking-[0.14em] text-[var(--cool)] shadow-lg">
              Scan checks · captures · threats
            </div>
          </div>
        )}

        {/* Floating Dragged Piece */}
        {dragState && dragState.moved && (
          <div
            ref={floatingRef}
            className="pointer-events-none absolute z-30 h-[13.5%] w-[13.5%] -translate-x-1/2 -translate-y-1/2 drop-shadow-[0_12px_18px_rgba(0, 0, 0, 0.180)]"
            style={{
              left: `${dragState.x}px`,
              top: `${dragState.y}px`,
            }}
          >
            <PieceSvg color={dragState.color} piece={dragState.piece} />
          </div>
        )}

        {/* Pawn Promotion Picker Modal Overlay */}
        {pendingPromotion && (
          <div
            onClick={() => setPendingPromotion(null)}
            className="absolute inset-0 z-40 flex items-center justify-center bg-[var(--surface-deep)]/50 backdrop-blur-[2px]"
          >
            <div
              onClick={(e) => e.stopPropagation()}
              className="premium-card flex flex-col items-center gap-2 rounded-xl border border-[var(--a)]/35 bg-[var(--surface)] p-3"
            >
              <span className="text-xs font-medium tracking-wide text-[var(--a)] uppercase">
                Promote Pawn
              </span>
              <div className="flex gap-2">
                {(['q', 'r', 'b', 'n'] as PieceSymbol[]).map((p) => (
                  <button
                    key={p}
                    type="button"
                    onClick={() => {
                      const uci = `${pendingPromotion.from}${pendingPromotion.to}${p}`;
                      setPendingPromotion(null);
                      onMoveAttempt?.(uci);
                    }}
                    className="flex h-14 w-14 items-center justify-center rounded-lg border border-[var(--line)] bg-[var(--surface)] p-1.5 transition hover:border-[var(--a)] hover:bg-[var(--surface-soft)]"
                  >
                    <PieceSvg color={turn} piece={p} />
                  </button>
                ))}
              </div>
            </div>
          </div>
        )}
      </div>
    </div>
  );
};
