import express from 'express';
import path from 'node:path';
import fs from 'node:fs';
import { fileURLToPath } from 'node:url';
import { loadLocalEnv } from './env.js';
import { coachService } from './geminiCoach.js';
import { getMirrorProfile, mirrorMove } from './mirrorOpponent.js';
import { pgnArchive } from './pgnArchive.js';
import { gameAnalyzer, MOTIF_LABELS } from './analyzer.js';
import { progressStore } from './progressStore.js';
import { stockfishPool } from './stockfishPool.js';
import {
  buildLearningPlan,
  emptyAnalyzeAllStatus,
  writeLearningPlanFiles,
} from './learningPlan.js';
import type {
  AnalyzeAllStatus,
  ArchiveOverviewResponse,
  AttemptMoveRequest,
  CoachAskRequest,
  GamePhase,
  MistakeChallengePublic,
  MistakeMotif,
  TimeClass,
} from '../shared/types.js';

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const PORT = Number(process.env.PORT || 5173);

// Optional local `.env` support for GEMINI_API_KEY. Existing process values win.
loadLocalEnv();

let analyzeAllJob: AnalyzeAllStatus = emptyAnalyzeAllStatus();

function getAnalyzeAllStatus(): AnalyzeAllStatus {
  return { ...analyzeAllJob };
}

async function runAnalyzeAllJob(): Promise<void> {
  const startedAt = new Date().toISOString();
  analyzeAllJob = {
    ...emptyAnalyzeAllStatus(),
    running: true,
    startedAt,
    message: 'Starting full-archive Stockfish analysis…',
  };
  console.log('[analyze-all] started');

  try {
    const result = await gameAnalyzer.analyzeAllGames((progress) => {
      analyzeAllJob = {
        ...analyzeAllJob,
        ...progress,
      };
    });

    analyzeAllJob = {
      ...analyzeAllJob,
      running: false,
      finishedAt: new Date().toISOString(),
      message: 'Full archive analysis complete',
      error: null,
      result,
      percent: 100,
    };
    writeLearningPlanFiles(getAnalyzeAllStatus());
    console.log('[analyze-all] learning plan written');
  } catch (err) {
    const message = err instanceof Error ? err.message : String(err);
    analyzeAllJob = {
      ...analyzeAllJob,
      running: false,
      finishedAt: new Date().toISOString(),
      error: message,
      message: `Full archive analysis failed: ${message}`,
    };
    console.error('[analyze-all] failed:', err);
  }
}

export async function createApp() {
  const app = express();
  app.use(express.json({ limit: '4mb' }));

  // Warm up archive, cached analyses, and Stockfish 18 NNUE workers
  pgnArchive.ensureLoaded();
  gameAnalyzer.ensureLoaded();
  stockfishPool.warmup().catch((err) => {
    console.error('[stockfishPool] Warmup error:', err);
  });
  // Always keep a current spoiler-free curriculum file on disk.
  try {
    writeLearningPlanFiles(getAnalyzeAllStatus());
  } catch (err) {
    console.warn('[learningPlan] Could not write initial curriculum:', err);
  }

  // 0. Lightweight health check for the `chess` launcher
  app.get('/api/health', (_req, res) => {
    res.json({
      ok: true,
      player: 'darrelnxt',
      engine: 'Stockfish 18 Lite NNUE',
      analyzeAllRunning: analyzeAllJob.running,
    });
  });

  // Separate from blind drills: only completed game moves are returned.
  app.get('/api/mirror/profile', async (_req, res) => {
    try {
      const p = await getMirrorProfile();
      res.json({ indexed: p.indexed, games: p.games, skipped: p.skipped });
    } catch { res.status(500).json({ error: 'Could not build your playing profile.' }); }
  });
  app.post('/api/mirror/move', async (req, res) => {
    try { res.json(await mirrorMove(req.body?.moves)); }
    catch (err) {
      const message = err instanceof Error ? err.message : 'Could not choose a move.';
      res.status(/blind drill/i.test(message) ? 409 : /move history|moves must|already over|moves continue/i.test(message) ? 400 : 503).json({ error: message });
    }
  });

  // 1. Archive & Mastery Overview
  app.get('/api/overview', (_req, res) => {
    const allRecords = pgnArchive.getAllRecords();
    const counts = pgnArchive.getCounts();

    let wins = 0;
    let losses = 0;
    let draws = 0;

    const byTimeClass: ArchiveOverviewResponse['byTimeClass'] = {
      rapid: { games: 0, wins: 0, losses: 0, latestElo: null, peakElo: null },
      blitz: { games: 0, wins: 0, losses: 0, latestElo: null, peakElo: null },
      bullet: { games: 0, wins: 0, losses: 0, latestElo: null, peakElo: null },
      classical: { games: 0, wins: 0, losses: 0, latestElo: null, peakElo: null },
    };

    const monthBuckets = new Map<
      string,
      { rapidElo: number | null; blitzElo: number | null; bulletElo: number | null; games: number }
    >();
    const openingCounts = new Map<string, { games: number; wins: number }>();

    // Iterate chronological (oldest -> newest) so latestElo per month/timeClass is accurate
    const chronological = [...pgnArchive.getArchiveRecordsOnly()].reverse();
    for (const rec of chronological) {
      const s = rec.summary;
      if (s.userOutcome === 'win') wins++;
      else if (s.userOutcome === 'loss') losses++;
      else draws++;

      const tcStats = byTimeClass[s.timeClass];
      tcStats.games++;
      if (s.userOutcome === 'win') tcStats.wins++;
      else if (s.userOutcome === 'loss') tcStats.losses++;
      if (s.userElo !== null) {
        tcStats.latestElo = s.userElo;
        if (tcStats.peakElo === null || s.userElo > tcStats.peakElo) {
          tcStats.peakElo = s.userElo;
        }
      }

      const mb = monthBuckets.get(s.month) ?? {
        rapidElo: null,
        blitzElo: null,
        bulletElo: null,
        games: 0,
      };
      mb.games++;
      if (s.userElo !== null) {
        if (s.timeClass === 'rapid') mb.rapidElo = s.userElo;
        else if (s.timeClass === 'blitz') mb.blitzElo = s.userElo;
        else if (s.timeClass === 'bullet') mb.bulletElo = s.userElo;
      }
      monthBuckets.set(s.month, mb);

      const op = openingCounts.get(s.openingName) ?? { games: 0, wins: 0 };
      op.games++;
      if (s.userOutcome === 'win') op.wins++;
      openingCounts.set(s.openingName, op);
    }

    const eloTimeline = Array.from(monthBuckets.entries())
      .sort(([a], [b]) => a.localeCompare(b))
      .map(([month, v]) => ({ month, ...v }));

    const topOpenings = Array.from(openingCounts.entries())
      .sort((a, b) => b[1].games - a[1].games)
      .slice(0, 6)
      .map(([name, v]) => ({
        name,
        games: v.games,
        winRate: Math.round((v.wins / Math.max(1, v.games)) * 100),
      }));

    // Aggregate mistake stats across all analyzed games
    const cachedAnalyses = gameAnalyzer.getAllCached();
    let totalDiscovered = 0;
    let unseen = 0;
    let needsReview = 0;
    let learning = 0;
    let mastered = 0;
    let blunders = 0;
    let mistakes = 0;
    let inaccuracies = 0;
    let attemptedFirstTries = 0;
    let passedFirstTries = 0;

    const motifTally = new Map<MistakeMotif, { count: number; mastered: number }>();
    const byPhase: Record<GamePhase, number> = {
      opening: 0,
      middlegame: 0,
      endgame: 0,
    };

    for (const analysis of cachedAnalyses) {
      // Only count if game exists in archive or custom
      if (!pgnArchive.getGameById(analysis.gameId)) continue;
      for (const m of analysis.mistakes) {
        totalDiscovered++;
        if (m.severity === 'blunder') blunders++;
        else if (m.severity === 'mistake') mistakes++;
        else inaccuracies++;

        byPhase[m.phase]++;
        const prog = progressStore.getRecord(m.id);
        if (prog.status === 'unseen') unseen++;
        else if (prog.status === 'needs_review') needsReview++;
        else if (prog.status === 'learning') learning++;
        else if (prog.status === 'mastered') mastered++;

        if (prog.solvedFirstTry !== null) {
          attemptedFirstTries++;
          if (prog.solvedFirstTry) passedFirstTries++;
        }

        const mt = motifTally.get(m.motif) ?? { count: 0, mastered: 0 };
        mt.count++;
        if (prog.status === 'mastered') mt.mastered++;
        motifTally.set(m.motif, mt);
      }
    }

    const byMotif = Array.from(motifTally.entries())
      .map(([motif, val]) => ({
        motif,
        label: MOTIF_LABELS[motif],
        count: val.count,
        mastered: val.mastered,
      }))
      .sort((a, b) => b.count - a.count);

    const payload: ArchiveOverviewResponse = {
      player: 'darrelnxt',
      totalArchiveGames: counts.archive,
      totalSupportedGames: counts.supported,
      totalChess960Games: counts.chess960,
      totalCustomGames: counts.custom,
      analyzedGamesCount: allRecords.filter((r) => Boolean(gameAnalyzer.getCached(r.summary.id)))
        .length,
      wins,
      losses,
      draws,
      byTimeClass,
      eloTimeline,
      topOpenings,
      mistakeStats: {
        totalDiscovered,
        unseen,
        needsReview,
        learning,
        mastered,
        blunders,
        mistakes,
        inaccuracies,
        firstTrySolveRate:
          attemptedFirstTries > 0
            ? Math.round((passedFirstTries / attemptedFirstTries) * 100)
            : 0,
        byMotif,
        byPhase,
      },
    };

    res.json(payload);
  });

  // 2. Paginated & Filterable Games List
  app.get('/api/games', (req, res) => {
    const all = pgnArchive.getAllRecords();
    const {
      source,
      analyzed,
      timeClass,
      outcome,
      color,
      month,
      search,
      page = '1',
      limit = '30',
    } = req.query as Record<string, string | undefined>;

    const monthsSet = new Set<string>();
    for (const r of all) monthsSet.add(r.summary.month);
    const months = Array.from(monthsSet).sort((a, b) => b.localeCompare(a));

    const q = (search || '').trim().toLowerCase();

    const filtered = all
      .map((r) => gameAnalyzer.enrichGameSummary(r))
      .filter((g) => {
        if (source && source !== 'all' && g.source !== source) return false;
        if (analyzed === 'true' && !g.analyzed) return false;
        if (analyzed === 'false' && g.analyzed) return false;
        if (timeClass && timeClass !== 'all' && g.timeClass !== (timeClass as TimeClass))
          return false;
        if (outcome && outcome !== 'all' && g.userOutcome !== outcome) return false;
        if (color && color !== 'all' && g.userColor !== color) return false;
        if (month && month !== 'all' && g.month !== month) return false;
        if (q) {
          const hay = `${g.opponentName} ${g.openingName} ${g.eco} ${g.date}`.toLowerCase();
          if (!hay.includes(q)) return false;
        }
        return true;
      });

    const pageNum = Math.max(1, parseInt(page, 10) || 1);
    const pageSize = Math.min(100, Math.max(5, parseInt(limit, 10) || 30));
    const start = (pageNum - 1) * pageSize;
    const items = filtered.slice(start, start + pageSize);

    res.json({
      total: filtered.length,
      page: pageNum,
      limit: pageSize,
      months,
      games: items,
    });
  });

  // 3. Pick Next Best Game to Learn From
  app.get('/api/games/next-coach', (req, res) => {
    const excludeId = (req.query.excludeId as string) || '';
    const all = pgnArchive
      .getAllRecords()
      .filter((r) => r.summary.analyzable !== false)
      .map((r) => gameAnalyzer.enrichGameSummary(r));

    // Prefer already-analyzed games with unmastered mistakes first, then unanalyzed losses/games!
    const withUnmastered = all.find(
      (g) =>
        g.id !== excludeId &&
        g.analyzed &&
        (g.totalMistakesCount ?? 0) > (g.masteredMistakesCount ?? 0)
    );
    if (withUnmastered) {
      res.json({ game: withUnmastered });
      return;
    }

    const unanalyzedLoss = all.find(
      (g) => g.id !== excludeId && !g.analyzed && g.userOutcome === 'loss'
    );
    if (unanalyzedLoss) {
      res.json({ game: unanalyzedLoss });
      return;
    }

    const anyNext = all.find((g) => g.id !== excludeId) ?? all[0];
    res.json({ game: anyNext ?? null });
  });

  // 4. Single Game Detail (Spoiler-Free Mistakes)
  app.get('/api/games/:id', (req, res) => {
    const record = pgnArchive.getGameById(req.params.id);
    if (!record) {
      res.status(404).json({ error: 'Game not found' });
      return;
    }
    res.json(gameAnalyzer.buildGameDetailResponse(record));
  });

  // 5. Analyze Game via SSE Real-Time Progress Stream
  app.get('/api/games/:id/analyze-stream', async (req, res) => {
    const record = pgnArchive.getGameById(req.params.id);
    if (!record) {
      res.status(404).json({ error: 'Game not found' });
      return;
    }
    if (record.summary.analyzable === false) {
      res.status(400).json({
        error:
          'This Chess960 / variant game is in the library, but the bundled standard chess.js replay cannot drill its castling moves.',
      });
      return;
    }

    res.setHeader('Content-Type', 'text/event-stream');
    res.setHeader('Cache-Control', 'no-cache');
    res.setHeader('Connection', 'keep-alive');
    res.flushHeaders?.();

    const sendEvent = (data: unknown) => {
      res.write(`data: ${JSON.stringify(data)}\n\n`);
    };

    try {
      await gameAnalyzer.analyzeGame(record.summary.id, (prog) => {
        sendEvent({ type: 'progress', ...prog });
      });
      const detail = gameAnalyzer.buildGameDetailResponse(record);
      sendEvent({ type: 'done', game: detail });
      res.end();
    } catch (err) {
      sendEvent({
        type: 'error',
        message: err instanceof Error ? err.message : 'Stockfish analysis failed',
      });
      res.end();
    }
  });

  // 6. Standard POST Analyze Fallback
  app.post('/api/games/:id/analyze', async (req, res) => {
    const record = pgnArchive.getGameById(req.params.id);
    if (!record) {
      res.status(404).json({ error: 'Game not found' });
      return;
    }
    if (record.summary.analyzable === false) {
      res.status(400).json({
        error:
          'This Chess960 / variant game is in the library, but the bundled standard chess.js replay cannot drill its castling moves.',
      });
      return;
    }
    try {
      await gameAnalyzer.analyzeGame(record.summary.id);
      res.json(gameAnalyzer.buildGameDetailResponse(record));
    } catch (err) {
      res.status(500).json({
        error: err instanceof Error ? err.message : 'Stockfish analysis failed',
      });
    }
  });

  // 7. Import Pasted PGN
  app.post('/api/pgn/import', (req, res) => {
    const { pgn, preferredSide = 'auto', playerHint } = (req.body ?? {}) as {
      pgn?: string;
      preferredSide?: 'auto' | 'w' | 'b';
      playerHint?: string;
    };

    try {
      if (typeof pgn !== 'string' || !['auto', 'w', 'b'].includes(preferredSide) || (playerHint !== undefined && typeof playerHint !== 'string')) throw new Error('Provide PGN text and a valid side.');
      const records = pgnArchive.importPgnText(pgn, preferredSide, playerHint);
      res.json({
        importedCount: records.length,
        games: records.map((r) => gameAnalyzer.enrichGameSummary(r)),
      });
    } catch (err) {
      res.status(400).json({
        error: err instanceof Error ? err.message : 'Invalid PGN input',
      });
    }
  });

  // 8. Cross-Game Mistake Vault (Spaced Repetition Queue)
  app.get('/api/mistakes', (req, res) => {
    const {
      status = 'all',
      severity = 'all',
      motif = 'all',
      phase = 'all',
    } = req.query as Record<string, string | undefined>;

    const allChallenges: MistakeChallengePublic[] = [];
    for (const analysis of gameAnalyzer.getAllCached()) {
      const gameRec = pgnArchive.getGameById(analysis.gameId);
      if (!gameRec) continue;
      for (const m of analysis.mistakes) {
        const pub = gameAnalyzer.toPublicChallenge(m, gameRec);
        if (status && status !== 'all') {
          if (status === 'due') {
            if (pub.mastery.status === 'mastered') continue;
          } else if (pub.mastery.status !== status) {
            continue;
          }
        }
        if (severity && severity !== 'all' && pub.severity !== severity) continue;
        if (motif && motif !== 'all' && pub.motif !== motif) continue;
        if (phase && phase !== 'all' && pub.phase !== phase) continue;
        allChallenges.push(pub);
      }
    }

    // Priority order for spaced repetition: needs_review -> learning -> unseen -> mastered, then highest winProbLost
    const statusPriority: Record<string, number> = {
      needs_review: 0,
      learning: 1,
      unseen: 2,
      mastered: 3,
    };

    allChallenges.sort((a, b) => {
      const pa = statusPriority[a.mastery.status] ?? 9;
      const pb = statusPriority[b.mastery.status] ?? 9;
      if (pa !== pb) return pa - pb;
      return b.winProbLost - a.winProbLost;
    });

    res.json({
      total: allChallenges.length,
      mistakes: allChallenges,
    });
  });

  // 9. Evaluate Player Candidate Move (Strict Anti-Spoiler Reveal Contract!)
  app.post('/api/mistakes/:id/attempt', async (req, res) => {
    const body = req.body as AttemptMoveRequest;
    if (typeof body?.moveUci !== 'string' || !/^[a-h][1-8][a-h][1-8][qrbn]?$/i.test(body.moveUci)) {
      res.status(400).json({ error: 'A valid UCI move is required' });
      return;
    }

    try {
      const result = await gameAnalyzer.evaluateAttempt(req.params.id, {
        moveUci: body.moveUci,
        attemptNumber: Math.max(1, Number(body.attemptNumber) || 1),
        maxAttempts: Math.min(3, Math.max(1, Number(body.maxAttempts) || 1)),
        isPracticeRetry: Boolean(body.isPracticeRetry),
      });
      res.json(result);
    } catch (err) {
      res.status(400).json({
        error: err instanceof Error ? err.message : 'Could not evaluate move',
      });
    }
  });

  // 10. Reset Mistake Mastery for Blind Retest
  app.post('/api/mistakes/:id/reset', (req, res) => {
    const mastery = progressStore.resetMistake(req.params.id);
    res.json({ mastery });
  });

  // 11. Spoiler-free cross-game curriculum ("what am I supposed to learn?")
  app.get('/api/learning-plan', (_req, res) => {
    try {
      res.json(buildLearningPlan(getAnalyzeAllStatus()));
    } catch (err) {
      res.status(500).json({
        error: err instanceof Error ? err.message : 'Could not build learning plan',
      });
    }
  });

  // 11b. Gemini coach status. Reload `.env` so adding a key after startup is
  // picked up on the next refresh; existing process values still win.
  app.get('/api/coach/status', (_req, res) => {
    loadLocalEnv();
    res.json(coachService.status());
  });

  // 11c. Ask Coach. The request never carries a key; the knowledge digest is
  // built from spoiler-free Stockfish data and Gemini answers are checked before
  // they are allowed to reach the browser.
  app.post('/api/coach/ask', async (req, res) => {
    loadLocalEnv();
    const body = req.body as CoachAskRequest | null;
    const question = String(body?.question ?? '').trim();
    if (!question) {
      res.status(400).json({ error: 'A question is required' });
      return;
    }
    if (question.length > 800) {
      res.status(400).json({ error: 'Please keep questions under 800 characters' });
      return;
    }
    try {
      const answer = await coachService.ask(
        {
          question,
          history: Array.isArray(body?.history) ? body!.history!.slice(-6) : [],
        },
        getAnalyzeAllStatus(),
      );
      res.json(answer);
    } catch (err) {
      res.status(500).json({
        error: err instanceof Error ? err.message : 'Coach could not answer right now',
      });
    }
  });

  // 12. Full-archive local Stockfish batch job
  app.post('/api/admin/analyze-all', (_req, res) => {
    if (analyzeAllJob.running) {
      res.status(202).json({ started: false, status: getAnalyzeAllStatus() });
      return;
    }
    void runAnalyzeAllJob();
    res.status(202).json({ started: true, status: getAnalyzeAllStatus() });
  });

  app.get('/api/admin/analyze-all/status', (_req, res) => {
    res.json(getAnalyzeAllStatus());
  });

  // Serve Frontend via Vite Middleware (Dev) or Static Dist (Prod)
  const isProd = process.env.NODE_ENV === 'production';
  if (!isProd) {
    const { createServer: createViteServer } = await import('vite');
    const vite = await createViteServer({
      root: path.resolve(__dirname, '..'),
      server: {
        middlewareMode: true,
        allowedHosts: true,
      },
      appType: 'spa',
    });
    app.use(vite.middlewares);
  } else {
    const distDir = path.resolve(__dirname, '../dist');
    app.use(express.static(distDir));
    app.get('/{*splat}', (_req, res) => {
      const indexHtml = path.join(distDir, 'index.html');
      if (fs.existsSync(indexHtml)) {
        res.sendFile(indexHtml);
      } else {
        res.status(404).send('Build not found. Run npm run build first.');
      }
    });
  }

  return app;
}

// Start HTTP server when invoked directly
const isMain =
  process.argv[1] &&
  path.resolve(process.argv[1]) === fileURLToPath(import.meta.url);

if (isMain) {
  createApp()
    .then((app) => {
      const server = app.listen(PORT, '0.0.0.0');
      server.on('listening', () => {
        console.log(`[Coach · Chess Improver] Running on http://0.0.0.0:${PORT} (Stockfish 18 NNUE ready)`);
      });
      server.on('error', (err) => {
        console.error('Failed to start server:', err.message);
        stockfishPool.shutdown();
        process.exit(1);
      });
    })
    .catch((err) => {
      console.error('Failed to start server:', err);
      process.exit(1);
    });
}
