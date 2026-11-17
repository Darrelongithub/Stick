import React, { useEffect, useId, useMemo, useState } from 'react';
import type { MistakeChallengePublic, MoveClassification, PlyAnalysisSummary } from '../../shared/types';
import { evalToWinFraction } from '../lib/chessFormat';

interface EvalGraphProps {
  plies: PlyAnalysisSummary[];
  mistakes: MistakeChallengePublic[];
  activePly?: number | null;
  onSelectMistake?: (mistake: MistakeChallengePublic) => void;
  onSelectPly?: (ply: PlyAnalysisSummary) => void;
  className?: string;
}

const CLASSIFICATION_COLORS: Record<MoveClassification, string> = {
  book: '#a29daf',
  best: '#4cc9f0',
  excellent: '#6ad8f7',
  good: '#ffb340',
  inaccuracy: '#ffb340',
  mistake: '#ffb340',
  blunder: '#ff6b57',
};

const SEVERITY_COLORS = {
  blunder: '#ff6b57',
  mistake: '#ffb340',
  inaccuracy: '#ffb340',
};

interface GraphTooltip {
  x: number;
  y: number;
  label: string;
  detail: string;
  color: string;
}

export const EvalGraph: React.FC<EvalGraphProps> = ({
  plies,
  mistakes,
  activePly,
  onSelectMistake,
  onSelectPly,
  className = '',
}) => {
  const rawId = useId();
  const uid = rawId.replace(/[^a-zA-Z0-9_-]/g, '');
  const [hover, setHover] = useState<GraphTooltip | null>(null);
  const [drawn, setDrawn] = useState(false);

  const geometry = useMemo(() => {
    const left = 30;
    const right = 704;
    const top = 18;
    const bottom = 150;
    const center = 84;

    const points = plies.map((ply, idx) => {
      const fraction = evalToWinFraction(ply.whiteEvalCp, ply.whiteMate);
      const x = plies.length <= 1 ? left : left + (idx / (plies.length - 1)) * (right - left);
      const y = bottom - fraction * (bottom - top);
      return { ply, x, y, fraction };
    });

    const linePath = points.map((p, i) => `${i === 0 ? 'M' : 'L'} ${p.x.toFixed(2)} ${p.y.toFixed(2)}`).join(' ');
    const areaPath =
      points.length > 0
        ? `${linePath} L ${points[points.length - 1].x.toFixed(2)} ${center} L ${points[0].x.toFixed(2)} ${center} Z`
        : '';
    let lineLength = 0;
    for (let i = 1; i < points.length; i += 1) {
      lineLength += Math.hypot(points[i].x - points[i - 1].x, points[i].y - points[i - 1].y);
    }

    return { left, right, top, bottom, center, points, linePath, areaPath, lineLength };
  }, [plies]);

  // Redraw the evaluation line whenever a different game/graph arrives.
  useEffect(() => {
    setDrawn(false);
    const frame = requestAnimationFrame(() => setDrawn(true));
    return () => cancelAnimationFrame(frame);
  }, [geometry.linePath]);

  useEffect(() => {
    setHover(null);
  }, [plies]);

  const mistakeByPly = useMemo(() => {
    const map = new Map<number, MistakeChallengePublic>();
    for (const m of mistakes) map.set(m.ply, m);
    return map;
  }, [mistakes]);

  const activeX = useMemo(() => {
    if (activePly == null || geometry.points.length === 0) return null;
    const idx = geometry.points.findIndex((p) => p.ply.ply === activePly);
    if (idx < 0) return null;
    return geometry.points[idx].x;
  }, [activePly, geometry.points]);

  const pointFromPointer = (event: React.MouseEvent<SVGSVGElement>) => {
    const rect = event.currentTarget.getBoundingClientRect();
    // viewBox is 720 wide with preserveAspectRatio="none": restore SVG user units first.
    const x = ((event.clientX - rect.left) / Math.max(1, rect.width)) * 720;
    return geometry.points.reduce((best, point) =>
      Math.abs(point.x - x) < Math.abs(best.x - x) ? point : best
    );
  };

  const describePoint = (point: (typeof geometry.points)[number]): GraphTooltip => {
    const mistake = mistakeByPly.get(point.ply.ply);
    const whiteWin = Math.round(point.fraction * 100);
    return {
      x: point.x,
      y: point.y,
      label: `Move ${point.ply.moveNumber}${point.ply.color === 'w' ? '' : '…'} · ${point.ply.classification}`,
      detail: mistake ? 'Click pin to train this mistake' : `${whiteWin}% White · click to replay`,
      color: CLASSIFICATION_COLORS[point.ply.classification],
    };
  };

  const handleBackgroundClick = (event: React.MouseEvent<SVGSVGElement>) => {
    if (!onSelectPly || plies.length === 0) return;
    onSelectPly(pointFromPointer(event).ply);
  };

  const handleGraphMouseMove = (event: React.MouseEvent<SVGSVGElement>) => {
    if (plies.length === 0) return;
    setHover(describePoint(pointFromPointer(event)));
  };

  if (plies.length === 0) {
    return (
      <div className={`flex h-44 items-center justify-center rounded-xl border border-dashed border-[var(--line-strong)] bg-[var(--surface)]/85 text-xs text-[var(--ink-muted)] ${className}`}>
        Evaluation graph appears after Stockfish analyzes this game.
      </div>
    );
  }

  const tooltipWidth = 182;
  const tooltipX = Math.max(32, Math.min(704 - tooltipWidth, (hover?.x ?? 0) - tooltipWidth / 2));
  const tooltipY = Math.max(4, Math.min(128, (hover?.y ?? 0) - 44));

  return (
    <svg
      viewBox="0 0 720 180"
      preserveAspectRatio="none"
      onClick={handleBackgroundClick}
      onMouseMove={handleGraphMouseMove}
      onMouseLeave={() => setHover(null)}
      className={`h-44 w-full cursor-crosshair rounded-xl border border-[var(--line)] bg-[var(--surface)] shadow-[inset_0_1px_0_rgba(255,255,255,0.9)] transition-colors duration-300 hover:border-[var(--a)]/35 ${className}`}
      role="img"
      aria-label="Stockfish evaluation graph. Click the line to replay a move, or click a colored pin to train that mistake."
    >
      <defs>
        <linearGradient id={`${uid}-above`} x1="0" y1="0" x2="0" y2="1">
          <stop offset="0%" stopColor="#4cc9f0" stopOpacity="0.34" />
          <stop offset="100%" stopColor="#4cc9f0" stopOpacity="0.02" />
        </linearGradient>
        <linearGradient id={`${uid}-below`} x1="0" y1="0" x2="0" y2="1">
          <stop offset="0%" stopColor="#ff6b57" stopOpacity="0.03" />
          <stop offset="100%" stopColor="#ff6b57" stopOpacity="0.32" />
        </linearGradient>
        <clipPath id={`${uid}-clip-above`}>
          <rect x="0" y="0" width="720" height={geometry.center} />
        </clipPath>
        <clipPath id={`${uid}-clip-below`}>
          <rect x={0} y={geometry.center} width="720" height={180 - geometry.center} />
        </clipPath>
      </defs>

      {/* Center / equal position line */}
      <line
        x1={geometry.left}
        y1={geometry.center}
        x2={geometry.right}
        y2={geometry.center}
        stroke="rgba(255, 255, 255, 0.18)"
        strokeWidth="1"
        strokeDasharray="4 5"
      />
      <line
        x1={geometry.left}
        y1={geometry.top}
        x2={geometry.left}
        y2={geometry.bottom}
        stroke="rgba(255, 255, 255, 0.09)"
      />

      {/* Evaluation area, split at equality */}
      {geometry.areaPath && (
        <>
          <path d={geometry.areaPath} fill={`url(#${uid}-above)`} clipPath={`url(#${uid}-clip-above)`} />
          <path d={geometry.areaPath} fill={`url(#${uid}-below)`} clipPath={`url(#${uid}-clip-below)`} />
        </>
      )}

      {/* Colored move-by-move line */}
      {geometry.points.slice(1).map((point, idx) => {
        const prev = geometry.points[idx];
        return (
          <line
            key={`seg-${point.ply.ply}`}
            x1={prev.x}
            y1={prev.y}
            x2={point.x}
            y2={point.y}
            stroke={CLASSIFICATION_COLORS[point.ply.classification]}
            strokeWidth="2.2"
            strokeLinecap="round"
            opacity="0.9"
          />
        );
      })}
      {geometry.linePath && (
        <>
          <path d={geometry.linePath} fill="none" stroke="rgba(255, 255, 255, 0.3)" strokeWidth="0.8" />
          <path
            d={geometry.linePath}
            fill="none"
            stroke="rgba(139, 124, 255, 0.42)"
            strokeWidth="1.5"
            strokeLinecap="round"
            strokeDasharray={geometry.lineLength || 1}
            strokeDashoffset={drawn ? 0 : geometry.lineLength || 1}
            style={{ transition: 'stroke-dashoffset 850ms cubic-bezier(0.16,1,0.3,1)' }}
          />
        </>
      )}

      {/* Active move marker */}
      {activeX !== null && (
        <line
          x1={activeX}
          y1={geometry.top - 4}
          x2={activeX}
          y2={geometry.bottom + 4}
          stroke="#8b7cff"
          strokeWidth="1.5"
          strokeDasharray="3 4"
          opacity="0.85"
        />
      )}

      {/* Clickable mistake pins — deliberately contain NO solution information */}
      {Array.from(mistakeByPly.entries()).map(([plyNumber, mistake], idx) => {
        const point = geometry.points.find((p) => p.ply.ply === plyNumber);
        if (!point) return null;
        const color = SEVERITY_COLORS[mistake.severity];
        const isActive = activePly === plyNumber;
        const pinTip: GraphTooltip = {
          x: point.x,
          y: point.y,
          label: `Move ${mistake.moveNumber} · ${mistake.severity}`,
          detail: `${Math.round(mistake.winProbLost * 100)}% win chance lost · train blind`,
          color,
        };
        return (
          <g
            key={mistake.id}
            onClick={(event) => {
              event.stopPropagation();
              onSelectMistake?.(mistake);
            }}
            onKeyDown={(event) => {
              if (event.key === 'Enter' || event.key === ' ') {
                event.preventDefault();
                onSelectMistake?.(mistake);
              }
            }}
            onMouseEnter={() => setHover(pinTip)}
            onFocus={() => setHover(pinTip)}
            onBlur={() => setHover(null)}
            tabIndex={0}
            role="button"
            aria-label={`Mistake on move ${mistake.moveNumber}. Press Enter to train it.`}
            className="animate-pin-in outline-none"
            style={{ cursor: 'pointer', animationDelay: `${Math.min(idx * 18, 360)}ms` }}
          >
            <title>{`Move ${mistake.moveNumber} · ${mistake.severity} · ${Math.round(mistake.winProbLost * 100)}% win chance lost`}</title>
            <circle cx={point.x} cy={point.y} r="13" fill="transparent" />
            <circle cx={point.x} cy={point.y} r={isActive ? 8.5 : 6.5} fill="#14111d" stroke={color} strokeWidth="2.4" />
            <circle cx={point.x} cy={point.y} r={isActive ? 3.6 : 2.6} fill={color} />
          </g>
        );
      })}

      {/* Hover tooltip — labels and severity only, never a best move. */}
      {hover && (
        <g pointerEvents="none" className="animate-fade-in">
          <rect
            x={tooltipX}
            y={tooltipY}
            width={tooltipWidth}
            height="34"
            rx="8"
            fill="#14111d"
            stroke={hover.color}
            strokeOpacity="0.6"
          />
          <circle cx={tooltipX + 12} cy={tooltipY + 17} r="3" fill={hover.color} />
          <text x={tooltipX + 21} y={tooltipY + 14} fill="#f3f1f8" fontSize="10" fontWeight="700">
            {hover.label}
          </text>
          <text x={tooltipX + 21} y={tooltipY + 27} fill="#b9b4c7" fontSize="9">
            {hover.detail}
          </text>
        </g>
      )}

      <text x="7" y="24" fill="#8f8ba0" fontSize="9" fontFamily="var(--font-mono)">
        W+
      </text>
      <text x="7" y="89" fill="#8f8ba0" fontSize="8" fontFamily="var(--font-mono)">
        =
      </text>
      <text x="7" y="148" fill="#8f8ba0" fontSize="9" fontFamily="var(--font-mono)">
        B+
      </text>
      <text x={geometry.left} y="171" fill="#8f8ba0" fontSize="9" fontFamily="var(--font-mono)">
        {plies[0].moveNumber}
      </text>
      <text x={(geometry.left + geometry.right) / 2} y="171" textAnchor="middle" fill="#8f8ba0" fontSize="9" fontFamily="var(--font-mono)">
        {plies[Math.floor(plies.length / 2)].moveNumber}
      </text>
      <text x={geometry.right} y="171" textAnchor="end" fill="#8f8ba0" fontSize="9" fontFamily="var(--font-mono)">
        {plies[plies.length - 1].moveNumber}
      </text>
      <text x={geometry.right} y="13" textAnchor="end" fill="#8f8ba0" fontSize="8" fontFamily="var(--font-mono)" letterSpacing="0.8">
        CLICK LINE TO REPLAY · PINS TO TRAIN
      </text>
    </svg>
  );
};
