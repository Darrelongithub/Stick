import fs from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';
import { gameAnalyzer, MOTIF_LABELS } from './analyzer.js';
import { pgnArchive } from './pgnArchive.js';
import { progressStore } from './progressStore.js';
import type {
  AnalyzeAllStatus,
  GamePhase,
  LearningPlanDrill,
  LearningPlanResponse,
  MasteryState,
  MistakeChallengePublic,
  MistakeMotif,
  MistakeSeverity,
} from '../shared/types.js';

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const APP_ROOT = path.resolve(__dirname, '..');
const DATA_DIR = process.env.CHESS_DATA_DIR ? path.resolve(process.env.CHESS_DATA_DIR) : path.join(APP_ROOT, 'data');
const LEARNING_PLAN_JSON = path.join(DATA_DIR, 'learning-plan.json');
const WHAT_TO_LEARN_MD = path.join(DATA_DIR, 'WHAT_TO_LEARN.md');
const FULL_CACHE_PATH = path.join(DATA_DIR, 'analysis-cache.json');

const PHASE_LABELS: Record<GamePhase, string> = {
  opening: 'Opening',
  middlegame: 'Middlegame',
  endgame: 'Endgame',
};

const MASTERY_LABELS: Record<MasteryState, string> = {
  unseen: 'Unseen',
  needs_review: 'Needs review',
  learning: 'Learning',
  mastered: 'Mastered',
};

const STATUS_PRIORITY: Record<MasteryState, number> = {
  needs_review: 0,
  learning: 1,
  unseen: 2,
  mastered: 3,
};

const FORBIDDEN_SOLUTION_KEYS = new Set([
  'solution',
  'bestMove',
  'bestPvSan',
  'bestEvalUserCp',
  'bestEvalUserMate',
  'alternatives',
  'playedRefutationPvSan',
  'coachExplanation',
]);

export function assertSpoilerFree(payload: unknown, label: string): void {
  // Inspect property names, not serialized text: a player's name or opening
  // may legitimately equal a forbidden field name without being a leak.
  if (!payload || typeof payload !== 'object') return;
  for (const [key, value] of Object.entries(payload)) {
    if (FORBIDDEN_SOLUTION_KEYS.has(key)) {
      throw new Error(`${label} leaked a Stockfish solution field: ${key}`);
    }
    assertSpoilerFree(value, label);
  }
}

export function emptyAnalyzeAllStatus(): AnalyzeAllStatus {
  pgnArchive.ensureLoaded();
  const counts = pgnArchive.getCounts();
  const total = counts.archive + counts.custom;
  const supported = counts.supported + counts.custom;
  return {
    running: false,
    startedAt: null,
    finishedAt: null,
    total,
    supported,
    processed: 0,
    analyzed: 0,
    skipped: 0,
    skippedVariant: 0,
    failed: 0,
    percent: 0,
    elapsedSeconds: 0,
    etaSeconds: null,
    totalMistakes: 0,
    currentGameId: null,
    currentOpening: null,
    message: 'No full-archive job is running in this session. The library shows the analyses currently saved locally.',
    error: null,
    result: null,
  };
}

function reasonForDrill(challenge: MistakeChallengePublic): string {
  const lost = Math.round(challenge.winProbLost * 100);
  switch (challenge.mastery.status) {
    case 'needs_review':
      return `Missed in a drill · recover ${lost}% win chance`;
    case 'learning':
      return challenge.mastery.failCount > 0 && challenge.mastery.streak === 0
        ? 'Two clean blind recalls away from mastered'
        : 'One clean blind recall away from mastered';
    case 'unseen':
      return `New Stockfish-verified mistake · ${lost}% win chance lost`;
    case 'mastered':
      return 'Cleanly recalled · keep it sharp';
  }
}

export function buildLearningPlan(analyzeAll: AnalyzeAllStatus): LearningPlanResponse {
  gameAnalyzer.ensureLoaded();
  pgnArchive.ensureLoaded();

  const counts = pgnArchive.getCounts();
  const challenges: MistakeChallengePublic[] = [];
  const bySeverity: Record<MistakeSeverity, number> = {
    blunder: 0,
    mistake: 0,
    inaccuracy: 0,
  };
  const byPhase: Record<GamePhase, number> = {
    opening: 0,
    middlegame: 0,
    endgame: 0,
  };
  const byMastery: Record<MasteryState, number> = {
    unseen: 0,
    needs_review: 0,
    learning: 0,
    mastered: 0,
  };
  const motifTally = new Map<MistakeMotif, { count: number; mastered: number }>();
  let attemptedFirstTries = 0;
  let passedFirstTries = 0;
  let analyzedGames = 0;

  for (const analysis of gameAnalyzer.getAllCached()) {
    const game = pgnArchive.getGameById(analysis.gameId);
    if (!game || game.summary.analyzable === false) continue;
    analyzedGames++;

    for (const mistake of analysis.mistakes) {
      const pub = gameAnalyzer.toPublicChallenge(mistake, game);
      challenges.push(pub);
      bySeverity[pub.severity]++;
      byPhase[pub.phase]++;
      byMastery[pub.mastery.status]++;

      const record = progressStore.getRecord(mistake.id);
      if (record.solvedFirstTry !== null) {
        attemptedFirstTries++;
        if (record.solvedFirstTry) passedFirstTries++;
      }

      const mt = motifTally.get(pub.motif) ?? { count: 0, mastered: 0 };
      mt.count++;
      if (pub.mastery.status === 'mastered') mt.mastered++;
      motifTally.set(pub.motif, mt);
    }
  }

  challenges.sort((a, b) => {
    const pa = STATUS_PRIORITY[a.mastery.status];
    const pb = STATUS_PRIORITY[b.mastery.status];
    if (pa !== pb) return pa - pb;
    if (b.winProbLost !== a.winProbLost) return b.winProbLost - a.winProbLost;
    return b.gameDate.localeCompare(a.gameDate);
  });

  const recommendedDrills: LearningPlanDrill[] = challenges.filter(c => c.mastery.status !== 'mastered').slice(0, 24).map((c, idx) => ({
    rank: idx + 1,
    mistakeId: c.id,
    gameId: c.gameId,
    gameDate: c.gameDate,
    opponent: c.gameOpponent,
    openingName: c.openingName,
    timeClass: c.timeClass,
    moveNumber: c.moveNumber,
    userColor: c.userColor,
    playedMoveSan: c.playedMove.san,
    severity: c.severity,
    motif: c.motif,
    motifLabel: MOTIF_LABELS[c.motif],
    phase: c.phase,
    phaseLabel: PHASE_LABELS[c.phase],
    winProbLost: c.winProbLost,
    mastery: c.mastery,
    focus: `${MOTIF_LABELS[c.motif]} · ${PHASE_LABELS[c.phase]}`,
    reason: reasonForDrill(c),
  }));

  const byMotif = Array.from(motifTally.entries())
    .map(([motif, val]) => ({
      motif,
      label: MOTIF_LABELS[motif],
      count: val.count,
      mastered: val.mastered,
    }))
    .sort((a, b) => b.count - a.count);

  const totalMistakes = challenges.length;
  const plan: LearningPlanResponse = {
    generatedAt: new Date().toISOString(),
    player: 'darrelnxt',
    engine: 'Stockfish 18 Lite NNUE (local)',
    totalArchiveGames: counts.archive,
    totalSupportedGames: counts.supported,
    totalChess960Games: counts.chess960,
    totalCustomGames: counts.custom,
    analyzedGames,
    totalMistakes,
    dueCount: totalMistakes - byMastery.mastered,
    masteredCount: byMastery.mastered,
    firstTrySolveRate:
      attemptedFirstTries > 0 ? Math.round((passedFirstTries / attemptedFirstTries) * 100) : 0,
    counts: {
      bySeverity,
      byPhase,
      byMastery,
      byMotif,
    },
    recommendedDrills,
    analyzeAll,
    files: {
      fullAnalysisCache: 'data/analysis-cache.json',
      learningPlanJson: 'data/learning-plan.json',
      whatToLearnMarkdown: 'data/WHAT_TO_LEARN.md',
    },
  };

  assertSpoilerFree(plan, 'Learning plan');
  return plan;
}

function renderMarkdown(plan: LearningPlanResponse): string {
  const lines: string[] = [];
  lines.push('# What to learn, Darrel');
  lines.push('');
  lines.push(`_Generated ${plan.generatedAt} by ${plan.engine}._`);
  lines.push('');
  lines.push(
    `All **${plan.totalArchiveGames.toLocaleString()}** games from \`darrelnxt-2026-.zip\` are loaded: ` +
      `**${plan.totalSupportedGames.toLocaleString()}** standard-rules games are engine-drillable and ` +
      `**${plan.totalChess960Games}** Chess960 games are listed but not drilled. ` +
      `${plan.totalCustomGames} pasted PGNs are also in the library.`
  );
  lines.push('');
  lines.push(
    `**${plan.analyzedGames.toLocaleString()} games analyzed · ${plan.totalMistakes.toLocaleString()} verified mistakes · ` +
      `${plan.dueCount.toLocaleString()} due · ${plan.masteredCount.toLocaleString()} mastered · ` +
      `${plan.firstTrySolveRate}% first-try recall.**`
  );
  lines.push('');
  if (plan.analyzeAll.running) {
    lines.push(
      `> Batch analysis is running: ${plan.analyzeAll.percent}% · ${plan.analyzeAll.processed}/${plan.analyzeAll.total} games · ETA ${plan.analyzeAll.etaSeconds ?? '—'}s`
    );
    lines.push('');
  } else if (plan.analyzeAll.result) {
    lines.push(
      `> Last full scan: ${plan.analyzeAll.result.analyzedGames} newly analyzed, ` +
        `${plan.analyzeAll.result.skippedGames} already cached, ` +
        `${plan.analyzeAll.result.failedGames} failed in ${plan.analyzeAll.result.durationSeconds}s.`
    );
    lines.push('');
  }

  lines.push('## Start here');
  lines.push('');
  lines.push('The app hides every best move until you fail a drill. Start with rank 1 and work down.');
  lines.push('');
  lines.push('| # | Game | Your move | Why it is due | Focus | Mastery |');
  lines.push('|---:|---|---|---|---|---|');
  for (const drill of plan.recommendedDrills.slice(0, 20)) {
    const lost = Math.round(drill.winProbLost * 100);
    lines.push(
      `| ${drill.rank} | ${drill.gameDate} vs ${drill.opponent} · move ${drill.moveNumber} | ` +
        `\`${drill.playedMoveSan}\` (${drill.severity}, −${lost}%) | ${drill.reason} | ` +
        `${drill.focus} | ${MASTERY_LABELS[drill.mastery.status]} |`
    );
  }
  if (plan.recommendedDrills.length === 0) {
    lines.push(plan.totalMistakes > 0
      ? '| — | No positions due | — | All discovered drills are mastered | — | — |'
      : '| — | No mistakes yet | — | Analyze games first | — | — |');
  }

  lines.push('');
  lines.push('## Weakness profile');
  lines.push('');
  lines.push('| Pattern | Mistakes | Mastered |');
  lines.push('|---|---:|---:|');
  for (const row of plan.counts.byMotif.slice(0, 8)) {
    lines.push(`| ${row.label} | ${row.count} | ${row.mastered} |`);
  }
  if (plan.counts.byMotif.length === 0) {
    lines.push('| No analyzed mistakes yet | 0 | 0 |');
  }

  lines.push('');
  lines.push('## How it teaches');
  lines.push('');
  lines.push('1. **Blind recall.** You see the position and your game move, never Stockfish’s answer.');
  lines.push('2. **Fail to reveal.** A wrong move gets feedback; only after the final failed attempt is the best move and refutation unlocked.');
  lines.push('3. **Practice and re-drill.** Step through the PV, play the best move yourself, then recall missed positions blind.');
  lines.push('4. **Spaced repetition.** Missed positions return first; two clean blind recalls master a previously failed mistake.');
  lines.push('');
  lines.push('## Local data');
  lines.push('');
  lines.push(`- Full Stockfish analyses: \`${plan.files.fullAnalysisCache}\` (gitignored).`);
  lines.push(`- Machine-readable curriculum: \`${plan.files.learningPlanJson}\` (gitignored).`);
  lines.push('- Pre-seeded instant-start games: `data/preanalyzed-games.json`.');
  lines.push('');
  lines.push('Stockfish 18 runs locally and remains the only chess knowledge source. An optional server-side `GEMINI_API_KEY` lets Gemini select a topic only; the server generates all answers from local Stockfish analysis and archive statistics. The browser never receives the key.');
  lines.push('');

  const markdown = lines.join('\n');
  return markdown;
}

export function writeLearningPlanFiles(analyzeAll: AnalyzeAllStatus): LearningPlanResponse {
  fs.mkdirSync(DATA_DIR, { recursive: true });
  const plan = buildLearningPlan(analyzeAll);
  fs.writeFileSync(LEARNING_PLAN_JSON, JSON.stringify(plan, null, 2), 'utf8');
  fs.writeFileSync(WHAT_TO_LEARN_MD, renderMarkdown(plan), 'utf8');
  return plan;
}

export const LEARNING_PLAN_PATHS = {
  FULL_CACHE_PATH,
  LEARNING_PLAN_JSON,
  WHAT_TO_LEARN_MD,
};
