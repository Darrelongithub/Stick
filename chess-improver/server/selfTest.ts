import assert from 'node:assert/strict';
import fs from 'node:fs';
import path from 'node:path';
import os from 'node:os';
import { spawnSync } from 'node:child_process';
import { fileURLToPath } from 'node:url';
import type { Server } from 'node:http';
import type { AddressInfo } from 'node:net';
import { Chess } from 'chess.js';

const __dirname = path.dirname(fileURLToPath(import.meta.url));
// Never overwrite or restore the user's live files: another running server may
// be writing them at the same time, and abrupt termination skips cleanup.
const DATA_DIR = fs.mkdtempSync(path.join(os.tmpdir(), 'chess-self-test-'));
const SEED_PATH = path.join(DATA_DIR, 'preanalyzed-games.json');
fs.copyFileSync(path.resolve(__dirname, '../data/preanalyzed-games.json'), SEED_PATH);
const TEST_ENV_PATH = path.join(DATA_DIR, '.env');
process.env.CHESS_DATA_DIR = DATA_DIR;
process.env.CHESS_ENV_FILE = TEST_ENV_PATH;

interface SeedMove {
  san: string;
  uci: string;
  from: string;
  to: string;
}

interface SeedAlternative {
  uci: string;
}

interface SeedMistake {
  id: string;
  gameId: string;
  fenBefore: string;
  userColor: 'w' | 'b';
  playedMove: SeedMove;
  bestMove: SeedMove;
  bestEvalUserCp: number;
  bestEvalUserMate: number | null;
  evalAfterPlayedUserCp: number;
  evalAfterPlayedUserMate: number | null;
  alternatives: SeedAlternative[];
}

interface SeedAnalysis {
  gameId: string;
  mistakes: SeedMistake[];
}

interface JsonRecord {
  [key: string]: unknown;
}

function cpToWinProb(cp: number): number {
  const clamped = Math.max(-4000, Math.min(4000, cp));
  return 1 / (1 + Math.exp(-0.00368208 * clamped));
}

function hasNoSolutionKeys(value: unknown): boolean {
  const text = JSON.stringify(value);
  const forbidden = [
    '"solution"',
    '"bestMove"',
    '"bestPvSan"',
    '"bestEvalUserCp"',
    '"bestEvalUserMate"',
    '"alternatives"',
    '"playedRefutationPvSan"',
    '"coachExplanation"',
  ];
  return forbidden.every((key) => !text.includes(key));
}

function assertNoSolution(value: unknown, label: string) {
  assert.ok(hasNoSolutionKeys(value), `${label} leaked a Stockfish solution field!`);
}

function assertChallengeIsSpoilerFree(challenge: JsonRecord, label: string) {
  assertNoSolution(challenge, label);
  const hint = String(challenge.pieceNudge ?? '');
  assert.doesNotMatch(
    hint,
    /\bon\s+[a-hA-H][1-8]\b|castl/i,
    `${label} hint exposed a square or castling move: ${hint}`
  );
  assert.doesNotMatch(hint, /\b(?:your|one of your)\s+(?:king|queen|rook|bishop|knight|pawn)s?\b/i,
    `${label} hint exposed the type of the best piece: ${hint}`);
}

function passed(label: string) {
  console.log(`  ✓ ${label}`);
}

// Keep Vite out of the API self-test: production mode skips middleware and serves API routes only.
// Never spend a real Gemini quota during the deterministic self-test.
process.env.NODE_ENV = 'production';
for (const key of [
  'GEMINI_API_KEY',
  'ADAPT_GEMINI_API_KEY',
  'GEMINI_MODEL',
  'ADAPT_GEMINI_MODEL_STANDARD',
  'GEMINI_MODEL_FALLBACK',
  'ADAPT_GEMINI_MODEL_FALLBACK',
  'GEMINI_BASE_URL',
  'ADAPT_GEMINI_BASE_URL',
]) {
  delete process.env[key];
}

const { createApp } = await import('./index.js');
const { createCoachService } = await import('./geminiCoach.js');
const { stockfishPool, StockfishPool } = await import('./stockfishPool.js');
const { progressStore, ProgressStore } = await import('./progressStore.js');
const { pgnArchive, PgnArchiveStore, normalizeChess960Fen } = await import('./pgnArchive.js');
const { gameAnalyzer } = await import('./analyzer.js');
const { buildLearningPlan, emptyAnalyzeAllStatus, writeLearningPlanFiles, assertSpoilerFree } = await import('./learningPlan.js');
const { groupMoveSheet, capturedPiecesByFen, clocksAtFen, preferredRatingSeries, archiveWinRate, lineMoveLabel } = await import('../src/lib/chessFormat.js');

const seedRaw = JSON.parse(fs.readFileSync(SEED_PATH, 'utf8')) as Record<string, SeedAnalysis>;
const seedAnalyses = Object.values(seedRaw);
const seedMistakes = seedAnalyses.flatMap((analysis) => analysis.mistakes);
const firstSeedGameId = Object.keys(seedRaw)[0];
assert.ok(firstSeedGameId, 'Expected at least one pre-analyzed game');
assert.ok(seedMistakes.length > 1, 'Expected multiple pre-analyzed mistakes');

let server: Server | null = null;
let baseUrl = '';
const startedAt = Date.now();

async function requestJson(urlPath: string, init?: RequestInit): Promise<any> {
  const response = await fetch(`${baseUrl}${urlPath}`, {
    ...init,
    signal: AbortSignal.timeout(60_000),
  });
  const text = await response.text();
  let body: any = text;
  if (text) {
    try {
      body = JSON.parse(text);
    } catch {
      // leave as raw text for a useful assertion message
    }
  }
  assert.ok(
    response.ok,
    `${init?.method ?? 'GET'} ${urlPath} failed (${response.status}): ${text.slice(0, 500)}`
  );
  return body;
}

async function postJson(urlPath: string, body: unknown): Promise<any> {
  return requestJson(urlPath, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  });
}

async function readSseDone(urlPath: string): Promise<{ progressCount: number; game: any }> {
  const response = await fetch(`${baseUrl}${urlPath}`, {
    signal: AbortSignal.timeout(60_000),
  });
  assert.equal(response.status, 200, `SSE ${urlPath} returned ${response.status}`);
  assert.match(response.headers.get('content-type') ?? '', /text\/event-stream/);
  assert.ok(response.body, 'SSE response had no readable body');

  const reader = response.body.getReader();
  const decoder = new TextDecoder();
  let buffer = '';
  let progressCount = 0;

  try {
    while (true) {
      const { value, done } = await reader.read();
      if (value) buffer += decoder.decode(value, { stream: true });

      let separator: number;
      while ((separator = buffer.indexOf('\n\n')) !== -1) {
        const eventBlock = buffer.slice(0, separator);
        buffer = buffer.slice(separator + 2);
        const dataLine = eventBlock
          .split('\n')
          .find((line) => line.startsWith('data: '));
        if (!dataLine) continue;

        const eventData = JSON.parse(dataLine.slice(6)) as JsonRecord;
        if (eventData.type === 'progress') progressCount++;
        if (eventData.type === 'error') {
          throw new Error(String(eventData.message ?? 'SSE analysis error'));
        }
        if (eventData.type === 'done') {
          return { progressCount, game: eventData.game };
        }
      }

      if (done) break;
    }
  } finally {
    await reader.cancel().catch(() => {});
  }

  throw new Error(`SSE ${urlPath} ended before a done event`);
}

/**
 * Picks a legal move that Stockfish should NOT accept as a strong fix, so the
 * API's strict reveal rules are exercised deterministically.
 */
async function findBadCandidate(mistake: SeedMistake): Promise<string | null> {
  const legal = new Chess(mistake.fenBefore)
    .moves({ verbose: true })
    .map((move) => `${move.from}${move.to}${move.promotion ?? ''}`);

  const excluded = new Set<string>([
    mistake.bestMove.uci,
    mistake.playedMove.uci,
    ...mistake.alternatives.map((alt) => alt.uci),
  ]);
  const candidates = legal.filter((uci) => !excluded.has(uci)).slice(0, 16);

  const bestWp = cpToWinProb(mistake.bestEvalUserCp);
  const playedWp = cpToWinProb(mistake.evalAfterPlayedUserCp);

  for (const uci of candidates) {
    const after = new Chess(mistake.fenBefore);
    after.move({
      from: uci.slice(0, 2),
      to: uci.slice(2, 4),
      promotion: uci.length >= 5 ? uci[4] : undefined,
    });

    const evaluated = await stockfishPool.evaluateFen(after.fen(), {
      depth: 12,
      multiPv: 1,
    });
    const top = evaluated.lines[0];
    if (!top) continue;

    // After the user's candidate, it is the opponent's turn. Its score negated
    // is the evaluation from the learner's perspective.
    const candidateUserCp = -top.cpFromTurn;
    const candidateUserMate =
      top.mateFromTurn === null ? null : -top.mateFromTurn;
    const candidateWp = cpToWinProb(candidateUserCp);

    const isStrongFix =
      bestWp - candidateWp <= 0.045 &&
      candidateWp - playedWp >= 0.045 &&
      !(
        mistake.bestEvalUserMate !== null &&
        mistake.bestEvalUserMate > 0 &&
        (candidateUserMate === null || candidateUserMate <= 0)
      );

    if (!isStrongFix) return uci;
  }

  return null;
}

try {
  console.log('\nCoach · Chess Improver · endpoint, Stockfish, Gemini coach & anti-spoiler self-test\n');

  // Exercise damaged files and write failures without touching real user data.
  const temporaryData = fs.mkdtempSync(path.join(os.tmpdir(), 'chess-store-test-'));
  try {
    const progressPath = path.join(temporaryData, 'progress.json');
    fs.writeFileSync(progressPath, '{ damaged');
    const brokenProgress = new ProgressStore(progressPath);
    assert.throws(() => brokenProgress.recordFailure('m1'), /saved progress file could not be read/);
    assert.equal(fs.readFileSync(progressPath, 'utf8'), '{ damaged');
    assert.equal(brokenProgress.getRecord('m1').status, 'unseen');

    fs.rmSync(progressPath);
    const healthyProgress = new ProgressStore(progressPath);
    healthyProgress.recordFailure('m1');
    fs.rmSync(progressPath);
    fs.mkdirSync(progressPath); // rename over a directory must fail
    assert.throws(() => healthyProgress.recordSuccess('m1', true));
    assert.equal(healthyProgress.getRecord('m1').status, 'needs_review');
    assert.equal(healthyProgress.revision, 1);
    const retryPath = path.join(temporaryData, 'retry-progress.json');
    const retryProgress = new ProgressStore(retryPath);
    assert.equal(retryProgress.recordSuccess('m2', false).status, 'learning');
    const laterRecall = retryProgress.recordSuccess('m2', true);
    assert.equal(laterRecall.status, 'mastered');
    assert.equal(laterRecall.solvedFirstTry, false);
    const streakPath = path.join(temporaryData, 'streak.json');
    const streakProgress = new ProgressStore(streakPath);
    streakProgress.recordFailure('m3');
    assert.equal(streakProgress.recordSuccess('m3', true).streak, 1);
    const assisted = streakProgress.recordSuccess('m3', false);
    assert.equal(assisted.status, 'learning');
    assert.equal(assisted.streak, 0);
    assert.equal(streakProgress.recordSuccess('m3', true).status, 'learning');
    assert.equal(streakProgress.recordSuccess('m3', true).status, 'mastered');


    const gamesPath = path.join(temporaryData, 'games.json');
    fs.writeFileSync(gamesPath, '[ damaged');
    const brokenArchive = new PgnArchiveStore(gamesPath);
    assert.throws(() => brokenArchive.importPgnText('1. e4 e5 2. Nf3 Nc6'), /saved custom games file could not be read/);
    assert.equal(fs.readFileSync(gamesPath, 'utf8'), '[ damaged');
    assert.equal(brokenArchive.getCounts().custom, 0);
    const structurallyBrokenPath = path.join(temporaryData, 'invalid-games.json');
    const structurallyBrokenText = JSON.stringify([{ pgn: '1. e4 e5', summary: { id: 'pgn-broken' } }]);
    fs.writeFileSync(structurallyBrokenPath, structurallyBrokenText);
    const structurallyBroken = new PgnArchiveStore(structurallyBrokenPath);
    assert.equal(structurallyBroken.getCounts().custom, 0);
    assert.throws(() => structurallyBroken.importPgnText('1. e4 e5'), /saved custom games file could not be read/);
    assert.equal(fs.readFileSync(structurallyBrokenPath, 'utf8'), structurallyBrokenText);

    const multiArchive = new PgnArchiveStore(path.join(temporaryData, 'multi-games.json'));
    const multi = multiArchive.importPgnText('[White "Alice"]\n[Black "Bob"]\n\n1. e4 { comment\n[Event "not a game"]\n} e5 1-0\n\n[Site "Test"]\n[Event "Second"]\n[White "Cara"]\n[Black "Dan"]\n\n1. d4 d5 0-1', 'w');
    assert.equal(multi.length, 2);
    assert.deepEqual(multi.map(game => game.summary.result), ['1-0', '0-1']);
    assert.throws(() => multiArchive.importPgnText('[Result "0-1"]\n\n1. e4 e5 1-0', 'w'), /conflicts/);
    assert.equal(multiArchive.getCounts().custom, 2);
    const commentGame = multiArchive.importPgnText('[White "Alice"]\n[Black "Bob"]\n\n1. e4 {\n[White "Mallory"]\n[Variant "Chess960"]\n[Result "0-1"]\n} e5 *', 'w');
    assert.equal(commentGame[0].summary.white, 'Alice');
    assert.equal(commentGame[0].summary.result, '*');
    assert.throws(() => multiArchive.importPgnText('[Result "bogus"]\n\n1. e4 e5', 'w'), /PGN result must be/);
    const quotedNames = multiArchive.importPgnText('[White "A;B"]\n[Black "C{D}"]\n\n1. e4 e5 *', 'auto', 'A;B');
    assert.equal(quotedNames[0].summary.white, 'A;B');
    assert.equal(quotedNames[0].summary.black, 'C{D}');
    assert.equal(quotedNames[0].summary.userColor, 'w');

    assert.equal(multiArchive.getCounts().custom, 4);
    assert.equal(normalizeChess960Fen('2kr1r2/8/8/8/8/8/8/2KR1R2 w FDfd - 0 1'), '2kr1r2/8/8/8/8/8/8/2KR1R2 w Kk - 0 1');
    assert.equal(normalizeChess960Fen('r3k2r/8/8/8/8/8/8/R3K2R w KQha - 0 1'), 'r3k2r/8/8/8/8/8/8/R3K2R w KQkq - 0 1');
    fs.rmSync(gamesPath);
    const healthyArchive = new PgnArchiveStore(gamesPath);
    healthyArchive.importPgnText('1. e4 e5 2. Nf3 Nc6');
    fs.rmSync(gamesPath);
    fs.mkdirSync(gamesPath);
    assert.throws(() => healthyArchive.importPgnText('1. d4 d5 2. c4 e6'));
    assert.equal(healthyArchive.getCounts().custom, 1);
    assert.equal(healthyArchive.revision, 1);
    assert.ok(!fs.readdirSync(temporaryData).some(name => name.endsWith('.tmp')));
  } finally { fs.rmSync(temporaryData, { recursive: true, force: true }); }
  passed('Damaged data is preserved and failed writes do not change in-memory progress or imports');
  const cacheTestDir = fs.mkdtempSync(path.join(os.tmpdir(), 'chess-cache-test-'));
  try {
    fs.copyFileSync(SEED_PATH, path.join(cacheTestDir, 'preanalyzed-games.json'));
    const corruptPath = path.join(cacheTestDir, 'analysis-cache.json');
    const corrupt = JSON.stringify({ x: { gameId: 'x', plies: [], mistakes: [null] } });
    fs.writeFileSync(corruptPath, corrupt);
    const script = `
      import assert from 'node:assert/strict';
      const { gameAnalyzer } = await import('./server/analyzer.ts');
      const { stockfishPool } = await import('./server/stockfishPool.ts');
      try {
        gameAnalyzer.ensureLoaded();
        assert.throws(() => gameAnalyzer.persistRuntimeCache(), /existing analysis cache could not be read/);
      } finally { stockfishPool.shutdown(); }
    `;
    const child = spawnSync(process.execPath, ['--import', 'tsx', '--input-type=module', '-e', script], {
      cwd: path.resolve(__dirname, '..'), env: { ...process.env, CHESS_DATA_DIR: cacheTestDir }, encoding: 'utf8', timeout: 15_000,
    });
    assert.equal(child.status, 0, `Cache guard subprocess failed: ${child.stderr}`);
    assert.equal(fs.readFileSync(corruptPath, 'utf8'), corrupt);
    const almostValid = JSON.parse(fs.readFileSync(SEED_PATH, 'utf8'));
    const firstAnalysis = Object.values(almostValid)[0] as { mistakes: Array<{ bestMove: unknown }> };
    firstAnalysis.mistakes[0].bestMove = {};
    const brokenMoveCache = JSON.stringify(almostValid);
    fs.writeFileSync(corruptPath, brokenMoveCache);
    const brokenMoveChild = spawnSync(process.execPath, ['--import', 'tsx', '--input-type=module', '-e', script], {
      cwd: path.resolve(__dirname, '..'), env: { ...process.env, CHESS_DATA_DIR: cacheTestDir }, encoding: 'utf8', timeout: 15_000,
    });
    assert.equal(brokenMoveChild.status, 0, `Malformed move cache guard failed: ${brokenMoveChild.stderr}`);
    assert.equal(fs.readFileSync(corruptPath, 'utf8'), brokenMoveCache);
    const brokenFen = JSON.parse(fs.readFileSync(SEED_PATH, 'utf8'));
    (Object.values(brokenFen)[0] as { mistakes: Array<{ fenBefore: string }> }).mistakes[0].fenBefore = 'not-a-fen';
    const brokenFenCache = JSON.stringify(brokenFen);
    fs.writeFileSync(corruptPath, brokenFenCache);
    const brokenFenChild = spawnSync(process.execPath, ['--import', 'tsx', '--input-type=module', '-e', script], {
      cwd: path.resolve(__dirname, '..'), env: { ...process.env, CHESS_DATA_DIR: cacheTestDir }, encoding: 'utf8', timeout: 15_000,
    });
    assert.equal(brokenFenChild.status, 0, `Malformed FEN cache guard failed: ${brokenFenChild.stderr}`);
    assert.equal(fs.readFileSync(corruptPath, 'utf8'), brokenFenCache);
    const illegalCache = JSON.parse(fs.readFileSync(SEED_PATH, 'utf8'));
    (Object.values(illegalCache)[0] as { mistakes: Array<{ bestMove: { san: string; uci: string; from: string; to: string } }> }).mistakes[0].bestMove = { san: 'e5', uci: 'e2e5', from: 'e2', to: 'e5' };
    const illegalCacheText = JSON.stringify(illegalCache);
    fs.writeFileSync(corruptPath, illegalCacheText);
    const illegalChild = spawnSync(process.execPath, ['--import', 'tsx', '--input-type=module', '-e', script], {
      cwd: path.resolve(__dirname, '..'), env: { ...process.env, CHESS_DATA_DIR: cacheTestDir }, encoding: 'utf8', timeout: 15_000,
    });
    assert.equal(illegalChild.status, 0, `Illegal move cache guard failed: ${illegalChild.stderr}`);
    assert.equal(fs.readFileSync(corruptPath, 'utf8'), illegalCacheText);
  } finally { fs.rmSync(cacheTestDir, { recursive: true, force: true }); }
  passed('Structurally corrupt analysis caches are preserved rather than overwritten');


  const app = await createApp();
  server = await new Promise<Server>((resolve) => {
    const listening = app.listen(0, '127.0.0.1', () => resolve(listening));
  });
  const address = server.address() as AddressInfo;
  baseUrl = `http://127.0.0.1:${address.port}`;
  await stockfishPool.warmup();
  const racePool = new StockfishPool(1);
  try {
    const [, , evaluation] = await Promise.all([racePool.warmup(), racePool.warmup(), racePool.evaluateFen(new Chess().fen(), { depth: 4 })]);
    assert.ok(evaluation.bestMoveUci);
  } finally { racePool.shutdown(); }
  passed('Concurrent Stockfish warmup and evaluation share a reliable handshake');
  const priorityPool = new StockfishPool(1);
  try {
    type TestWorker = { evaluate: (fen: string, depth: number) => Promise<{ bestMoveUci: string | null; lines: Array<{ multipv: number; cpFromTurn: number; mateFromTurn: number | null; pvUci: string[] }> }> };
    const worker = (priorityPool as unknown as { workers: TestWorker[] }).workers[0];
    const order: number[] = [];
    let releaseFirst!: () => void;
    const firstStarted = new Promise<void>(resolve => {
      worker.evaluate = async (_fen, depth) => {
        order.push(depth);
        if (depth === 1) { resolve(); await new Promise<void>(release => { releaseFirst = release; }); }
        return { bestMoveUci: 'e2e4', lines: [{ multipv: 1, cpFromTurn: 10, mateFromTurn: null, pvUci: ['e2e4'] }] };
      };
    });
    const fen = new Chess().fen();
    const first = priorityPool.evaluateFen(fen, { depth: 1, priority: 'background' });
    await firstStarted;
    const queuedBackground = priorityPool.evaluateFen(fen, { depth: 2, priority: 'background' });
    const interactive = priorityPool.evaluateFen(fen, { depth: 3 });
    releaseFirst();
    await Promise.all([first, queuedBackground, interactive]);
    assert.deepEqual(order, [1, 3, 2]);
  } finally { priorityPool.shutdown(); }
  passed('Live moves are prioritized over queued full-game analysis');
  const malformedPool = new StockfishPool(1);
  try {
    const worker = (malformedPool as unknown as { workers: Array<{ evaluate: () => Promise<unknown> }> }).workers[0];
    worker.evaluate = async () => ({ bestMoveUci: 'e2e4', lines: [] });
    await assert.rejects(malformedPool.evaluateFen(new Chess().fen()), /incomplete or illegal evaluation/);
    worker.evaluate = async () => ({ bestMoveUci: 'e2e5', lines: [{ pvUci: ['e2e4'] }] });
    await assert.rejects(malformedPool.evaluateFen(new Chess().fen()), /incomplete or illegal evaluation/);
    worker.evaluate = async () => ({ bestMoveUci: 'e2e4', lines: [
      { multipv: 1, cpFromTurn: 10, mateFromTurn: null, pvUci: ['e2e4'] },
      { multipv: 2, cpFromTurn: Number.NaN, mateFromTurn: null, pvUci: ['d2d4'] },
    ] });
    await assert.rejects(malformedPool.evaluateFen(new Chess().fen(), { multiPv: 2 }), /incomplete or illegal evaluation/);
    worker.evaluate = async () => ({ bestMoveUci: 'e2e4', lines: [{ multipv: 1, cpFromTurn: 10, mateFromTurn: null, pvUci: ['e2e4'] }] });
    await assert.rejects(malformedPool.evaluateFen(new Chess().fen(), { multiPv: 3 }), /incomplete or illegal evaluation/);
    worker.evaluate = async () => ({ bestMoveUci: 'e2e4', lines: [{ multipv: 1, cpFromTurn: 10, mateFromTurn: null, pvUci: ['e2e4', 'e7e3'] }] });
    await assert.rejects(malformedPool.evaluateFen(new Chess().fen()), /incomplete or illegal evaluation/);
    worker.evaluate = async () => ({ bestMoveUci: 'e2e4', lines: [{ multipv: 1, cpFromTurn: 10, mateFromTurn: null, pvUci: ['d2d4'] }] });
    await assert.rejects(malformedPool.evaluateFen(new Chess().fen()), /incomplete or illegal evaluation/);
  } finally { malformedPool.shutdown(); }
  passed('Incomplete or illegal engine output cannot become a neutral chess evaluation');

  const recoveryPool = new StockfishPool(1);
  try {
    await recoveryPool.warmup();
    const worker = (recoveryPool as unknown as { workers: Array<{ proc: import('node:child_process').ChildProcess }> }).workers[0];
    const exit = new Promise<void>(resolve => worker.proc.once('exit', () => resolve()));
    worker.proc.kill('SIGKILL');
    await exit;
    const recovered = await recoveryPool.evaluateFen(new Chess().fen(), { depth: 3 });
    assert.ok(recovered.bestMoveUci, 'A signal-killed worker must be replaced');
  } finally { recoveryPool.shutdown(); }
  const shutdownPool = new StockfishPool(1);
  const running = shutdownPool.evaluateFen(new Chess().fen(), { depth: 18 });
  const queued = shutdownPool.evaluateFen(new Chess().fen(), { depth: 18 });
  shutdownPool.shutdown();
  const settled = await Promise.race([
    Promise.allSettled([running, queued]),
    new Promise<never>((_, reject) => setTimeout(() => reject(new Error('Shutdown left engine jobs pending')), 3000)),
  ]);
  assert.ok(settled.every(result => result.status === 'rejected'));
  await assert.rejects(shutdownPool.evaluateFen(new Chess().fen()), /shut down/);
  passed('Crashed workers restart and shutdown rejects active and queued jobs');


  passed(`Unified API server listening on ${baseUrl}`);

  // 1. Archive overview
  const overview = await requestJson('/api/overview');
  assert.equal(overview.player, 'darrelnxt');
  assert.equal(overview.totalArchiveGames, 1128);
  assert.equal(overview.totalSupportedGames, 1108);
  assert.equal(overview.totalChess960Games, 20);
  assert.ok(overview.analyzedGamesCount >= 14);
  assert.ok(overview.mistakeStats.totalDiscovered >= 67);
  assert.equal(overview.wins + overview.losses + overview.draws, 1128);
  passed(
    `Archive overview: 1,128 games loaded (1,108 drillable + 20 Chess960), ${overview.analyzedGamesCount} analyzed, ${overview.mistakeStats.totalDiscovered} mistakes`
  );

  const health = await requestJson('/api/health');
  assert.equal(health.ok, true);
  const initialJob = await requestJson('/api/admin/analyze-all/status');
  assert.equal(initialJob.running, false);
  const plan = await requestJson('/api/learning-plan');
  assert.equal(plan.totalArchiveGames, 1128);
  assert.equal(plan.totalSupportedGames, 1108);
  assert.ok(plan.totalMistakes >= 67);
  assertNoSolution(plan.recommendedDrills, 'GET /api/learning-plan drills');
  passed('Health, batch status, and spoiler-free learning-plan endpoints');

  const mirrorProfile = await requestJson('/api/mirror/profile');
  assert.equal(mirrorProfile.indexed, 1128);
  assert.equal(mirrorProfile.games + mirrorProfile.skipped, mirrorProfile.indexed);
  assert.ok(mirrorProfile.games >= 1108);
  const mirrorFirst = await postJson('/api/mirror/move', { moves: [] });
  assert.equal(mirrorFirst.source, 'archive');
  assert.match(mirrorFirst.move, /^[a-h][1-8][a-h][1-8][qrbn]?$/);
  assert.ok(mirrorFirst.occurrences > 0 && mirrorFirst.samples >= mirrorFirst.occurrences);
  const invalidMirror = await fetch(`${baseUrl}/api/mirror/move`, { method: 'POST', headers: { 'content-type': 'application/json' }, body: JSON.stringify({ moves: ['e2e5'] }) });
  assert.equal(invalidMirror.status, 400);
  const unseen = await postJson('/api/mirror/move', { moves: ['e2e4','e7e5','g1f3','b8c6','b1c3','g8f6','a2a3','a7a6','h2h3','h7h6','d2d3','d7d6','f1e2','f8e7','c1d2','c8d7'] });
  assert.equal(unseen.source, 'stockfish');
  assert.match(unseen.move, /^[a-h][1-8][a-h][1-8][qrbn]?$/);
  const finished = await fetch(`${baseUrl}/api/mirror/move`, { method: 'POST', headers: { 'content-type': 'application/json' }, body: JSON.stringify({ moves: ['f2f3','e7e5','g2g4','d8h4'] }) });
  assert.equal(finished.status, 400);
  passed('Mirror profile indexes the archive and plays a recorded legal move; Stockfish handles unseen positions and invalid or finished games are rejected');
  // A mirror reply must never expose the answer to an existing blind drill.
  const blockedDrill = seedMistakes[0];
  const recorded = pgnArchive.getGameById(blockedDrill.gameId);
  assert.ok(recorded);
  const replay = new Chess();
  replay.loadPgn(recorded.pgn);
  const history = replay.history({ verbose: true });
  const target = blockedDrill.fenBefore.split(' ').slice(0, 4).join(' ');
  const targetIndex = history.findIndex(move => move.before.split(' ').slice(0, 4).join(' ') === target);
  assert.ok(targetIndex >= 0);
  const preceding = history.slice(0, targetIndex).map(m => `${m.from}${m.to}${m.promotion ?? ''}`);
  const blockedResponse = await fetch(`${baseUrl}/api/mirror/move`, { method: 'POST', headers: { 'content-type': 'application/json' }, body: JSON.stringify({ moves: preceding }) });
  assert.equal(blockedResponse.status, 409);
  const blockedBody = await blockedResponse.json();
  assert.equal(blockedBody.move, undefined);
  passed('Mirror cannot reveal a blind-drill position');
  // Simulate a new analysis arriving during the asynchronous profile lookup.
  const { mirrorMove } = await import('./mirrorOpponent.js');
  const originalGetAllCached = gameAnalyzer.getAllCached;
  let checks = 0;
  gameAnalyzer.getAllCached = (() => ++checks === 1 ? [] : [{ mistakes: [{ fenBefore: new Chess().fen() }] }]) as typeof gameAnalyzer.getAllCached;
  try { await assert.rejects(mirrorMove([]), /blind drill/i); }
  finally { gameAnalyzer.getAllCached = originalGetAllCached; }
  assert.ok(checks >= 2);
  passed('Mirror rechecks for newly analyzed drills after waiting for the profile');

  const badImport = await fetch(`${baseUrl}/api/pgn/import`, { method: 'POST', headers: { 'content-type': 'application/json' }, body: JSON.stringify({ pgn: '[Event "First"]\n\n1. e4 e5\n\n[Event "Bad"]\n\n1. e4 e9' }) });
  assert.equal(badImport.status, 400);
  const afterBadImport = await requestJson('/api/overview');
  assert.equal(afterBadImport.totalCustomGames, overview.totalCustomGames);
  const malformedImport = await fetch(`${baseUrl}/api/pgn/import`, { method: 'POST', headers: { 'content-type': 'application/json' }, body: JSON.stringify({ pgn: 123 }) });
  assert.equal(malformedImport.status, 400);
  passed('Invalid multi-game imports are atomic; malformed inputs are rejected');

  // 1b. Gemini coach layer: no key -> local fallback; fake provider -> Gemini path;
  // a provider answer that names an engine move is rejected before it reaches the UI.
  const coachStatus = await requestJson('/api/coach/status');
  assert.equal(coachStatus.provider, 'gemini');
  assert.equal(coachStatus.configured, false);
  assert.equal(coachStatus.spoilerSafe, true);
  assert.match(coachStatus.knowledgeEngine, /Stockfish/);
  assert.match(coachStatus.reason ?? '', /No server-side Gemini key/i);
  assert.match(coachStatus.hint ?? '', /GEMINI_API_KEY/);
  const localCoach = await postJson('/api/coach/ask', {
    question: 'What should I study this week?',
    history: [],
  });
  assert.equal(localCoach.source, 'local');
  assert.equal(localCoach.configured, false);
  assert.ok(localCoach.answer.length > 40);
  assert.match(localCoach.answer, /^Darrel — /);
  assert.equal(localCoach.suggestions.length, 4);
  assertNoSolution(localCoach, 'local coach answer');
  passed('Coach status and no-key local fallback stay spoiler-free');
  progressStore.resetMistake(seedMistakes[0].id);
  const beforeProgress = await postJson('/api/coach/ask', { question: 'Am I improving?', history: [] });
  progressStore.recordSuccess(seedMistakes[0].id, true);
  const afterProgress = await postJson('/api/coach/ask', { question: 'Am I improving?', history: [] });
  assert.equal(afterProgress.knowledge.masteredCount, beforeProgress.knowledge.masteredCount + 1);
  progressStore.resetMistake(seedMistakes[0].id);
  passed('Coach answers immediately reflect changed training progress');

  const fakeGeminiFetch = (text: string): typeof fetch =>
    (async () =>
      new Response(
        JSON.stringify({
          candidates: [{ content: { parts: [{ text }] }, finishReason: 'STOP' }],
        }),
        { status: 200, headers: { 'content-type': 'application/json' } },
      )) as unknown as typeof fetch;
  const fakeEnv = {
    GEMINI_API_KEY: 'self-test-key',
    GEMINI_MODEL: 'gemini-self-test',
    GEMINI_MIN_INTERVAL_MS: '0',
  };
  const geminiService = createCoachService({
    env: fakeEnv,
    fetchImpl: fakeGeminiFetch(
      'STUDY',
    ),
  });
  const geminiAnswer = await geminiService.ask({ question: 'What should I study this week?' });
  assert.equal(geminiAnswer.source, 'gemini');
  assert.equal(geminiAnswer.status, 'ok');
  assert.equal(geminiAnswer.configured, true);
  assert.match(geminiAnswer.answer, /Stockfish-verified cases/i);
  assertNoSolution(geminiAnswer, 'Gemini coach answer');
  passed('Gemini intent maps to a locally generated Stockfish-based answer');
  let discoveryCallsOnSuccess = 0;
  const noDiscoveryFetch = (async (input: RequestInfo | URL) => {
    if (String(input).endsWith('/models')) { discoveryCallsOnSuccess++; return new Response('{}'); }
    return fakeGeminiFetch('STUDY')(input);
  }) as typeof fetch;
  assert.equal((await createCoachService({ env: fakeEnv, fetchImpl: noDiscoveryFetch }).ask({ question: 'study' })).source, 'gemini');
  assert.equal(discoveryCallsOnSuccess, 0);
  passed('Configured Gemini models are attempted without waiting for model discovery');

  const whitespaceSettings = createCoachService({ env: { GEMINI_API_KEY: '  ', ADAPT_GEMINI_API_KEY: 'fallback-key', GEMINI_MODEL: '  ', GEMINI_MIN_INTERVAL_MS: '  ' }, fetchImpl: fakeGeminiFetch('STUDY') });
  assert.equal(whitespaceSettings.status().configured, true);
  assert.equal(whitespaceSettings.status().model, 'gemini-flash-latest');
  assert.equal(whitespaceSettings.status().minIntervalMs, 700);
  assert.equal((await whitespaceSettings.ask({ question: 'study' })).source, 'gemini');
  passed('Whitespace-only Gemini settings do not suppress usable fallback keys or defaults');

  const explanationService = createCoachService({ env: fakeEnv, fetchImpl: fakeGeminiFetch('WHY') });
  assert.deepEqual(await explanationService.classifyExplanation('Why is that move best?'), { intent: 'WHY', source: 'gemini', status: 'ok' });
  const poisonedExplanation = createCoachService({ env: fakeEnv, fetchImpl: fakeGeminiFetch('Play Qh5!') });
  assert.deepEqual(await poisonedExplanation.classifyExplanation('Why is that move best?'), { intent: 'WHY', source: 'local', status: 'spoiler_rejected' });
  const explanationQuota = createCoachService({ env: { ...fakeEnv, GEMINI_DAILY_CALL_BUDGET: '1' }, fetchImpl: fakeGeminiFetch('WHY') });
  const sharedBudget = await Promise.all([explanationQuota.classifyExplanation('Why?'), explanationQuota.ask({ question: 'study' })]);
  assert.equal(explanationQuota.status().callsToday, 1);
  assert.equal(sharedBudget.filter(a => a.source === 'gemini').length, 1);
  const intentOnly = await postJson('/api/coach/explanation-intent', { question: 'Why is that move best?' });
  assert.deepEqual(intentOnly, { intent: 'WHY', source: 'local', status: 'disabled' });
  assertNoSolution(intentOnly, 'explanation classifier');
  passed('Revealed-move topic classifier shares the Gemini budget and rejects provider prose without exposing solutions');

  const limited = createCoachService({ env: { ...fakeEnv, GEMINI_DAILY_CALL_BUDGET: '1' }, fetchImpl: fakeGeminiFetch('STUDY') });
  const concurrent = await Promise.all([limited.ask({ question: 'study' }), limited.ask({ question: 'training' })]);
  assert.equal(concurrent.filter(a => a.source === 'gemini').length, 1);
  assert.equal(concurrent.filter(a => a.status === 'quota').length, 1);
  passed('Concurrent coach requests cannot exceed the daily budget');
  const changedEnv = { ...fakeEnv, GEMINI_BASE_URL: 'https://one.invalid/v1', GEMINI_MODEL: 'gemini-first' };
  const calledUrls: string[] = [];
  const changedFetch = (async (input: RequestInfo | URL) => {
    calledUrls.push(String(input));
    return String(input).endsWith('/models') ? new Response('{}', { status: 200 }) : fakeGeminiFetch('STUDY')(input);
  }) as typeof fetch;
  const changingProvider = createCoachService({ env: changedEnv, fetchImpl: changedFetch });
  await changingProvider.ask({ question: 'study' });
  changedEnv.GEMINI_BASE_URL = 'https://two.invalid/v1';
  await changingProvider.ask({ question: 'study' });
  assert.ok(calledUrls.some(url => url.includes('two.invalid') && url.includes('gemini-first')));
  passed('Changed provider settings invalidate cached coach answers and discovery');
  let generationCalls = 0;
  const failedModelFetch = (async (input: RequestInfo | URL) => {
    if (String(input).endsWith('/models')) return new Response('{}', { status: 200 });
    generationCalls++;
    return new Response('{}', { status: 404 });
  }) as typeof fetch;
  const limitedFallback = createCoachService({ env: { ...fakeEnv, GEMINI_DAILY_CALL_BUDGET: '1' }, fetchImpl: failedModelFetch });
  const limitedFallbackAnswer = await limitedFallback.ask({ question: 'study' });
  assert.equal(limitedFallbackAnswer.status, 'quota');
  assert.equal(generationCalls, 1);
  assert.equal(limitedFallback.status().callsToday, 1);
  const secretStatus = createCoachService({ env: { ...fakeEnv, GEMINI_BASE_URL: 'https://user:secret@example.invalid/private' } }).status();
  assert.doesNotMatch(JSON.stringify(secretStatus), /secret|example\.invalid/);
  passed('Provider fallback respects the generation budget and status hides private endpoint details');

  // A retired configured model should be replaced by a model the key can use.
  const discoveryFetch = ((input: RequestInfo | URL) => {
    const url = String(input);
    if (url.endsWith('/models')) {
      return Promise.resolve(
        new Response(
          JSON.stringify({
            models: [
              { name: 'models/gemini-discovered-flash', supportedGenerationMethods: ['generateContent'] },
              { name: 'models/gemini-embedding', supportedGenerationMethods: ['embedContent'] },
              { name: 'models/gemini-preview', supportedGenerationMethods: ['generateContent'] },
            ],
          }),
          { status: 200, headers: { 'content-type': 'application/json' } },
        ),
      );
    }
    if (!url.includes('gemini-discovered-flash')) {
      return Promise.resolve(
        new Response(JSON.stringify({ error: { message: 'model not found' } }), {
          status: 404,
          headers: { 'content-type': 'application/json' },
        }),
      );
    }
    return Promise.resolve(
      new Response(
        JSON.stringify({
          candidates: [
            {
              content: { parts: [{ text: 'PROGRESS' }] },
              finishReason: 'STOP',
            },
          ],
        }),
        { status: 200, headers: { 'content-type': 'application/json' } },
      ),
    );
  }) as unknown as typeof fetch;
  const discoveryService = createCoachService({ env: fakeEnv, fetchImpl: discoveryFetch });
  const discovered = await discoveryService.ask({ question: 'Am I improving?' });
  assert.equal(discovered.source, 'gemini');
  assert.equal(discovered.model, 'Gemini (discovered model)');
  assert.match(discovered.answer, /Current recall/i);
  assert.equal(discoveryService.status().lastProviderError, null);
  passed('Gemini discovers a supported model after a retired alias 404s');
  let modelCalls = 0;
  const retired400Fetch = ((input: RequestInfo | URL) => {
    if (String(input).endsWith('/models')) return Promise.resolve(new Response('{}', { status: 200 }));
    modelCalls++;
    if (modelCalls === 1) return Promise.resolve(new Response(JSON.stringify({ error: { message: 'unknown model; play e4' } }), { status: 400 }));
    return Promise.resolve(new Response(JSON.stringify({ candidates: [{ content: { parts: [{ text: 'STUDY' }] } }] }), { status: 200 }));
  }) as unknown as typeof fetch;
  const retired400Service = createCoachService({ env: fakeEnv, fetchImpl: retired400Fetch });
  const retired400 = await retired400Service.ask({ question: 'study' });
  assert.equal(retired400.source, 'gemini');
  assert.equal(modelCalls, 2);
  assert.doesNotMatch(JSON.stringify(retired400), /play e4/i);
  passed('Retired model HTTP 400s retry safely without exposing provider error text');


  const rejectingService = createCoachService({
    env: fakeEnv,
    fetchImpl: fakeGeminiFetch('The best move is Nc3.'),
  });
  const rejected = await rejectingService.ask({ question: 'What is the answer?' });
  assert.equal(rejected.source, 'local');
  assert.equal(rejected.status, 'spoiler_rejected');
  assertNoSolution(rejected, 'rejected Gemini answer');
  passed('Coach rejects provider answers that name an engine move');
  for (const untrusted of ['Play e4 now.', 'STUDY\nPlay e4.', 'Knights move diagonally.', 'study', '{"intent":"STUDY"}']) {
    const service = createCoachService({ env: fakeEnv, fetchImpl: fakeGeminiFetch(untrusted) });
    const result = await service.ask({ question: 'What should I study this week?' });
    assert.equal(result.source, 'local');
    assert.equal(result.status, 'spoiler_rejected');
    assert.ok(!result.answer.includes(untrusted));
  }
  passed('Hard gate rejects arbitrary provider prose, moves, and malformed intents');
  const poisonedMetadataFetch = ((input: RequestInfo | URL) => {
    if (String(input).endsWith('/models')) return Promise.resolve(new Response(JSON.stringify({ models: [{ name: 'models/gemini-play-e4-now', supportedGenerationMethods: ['generateContent'] }] }), { status: 200 }));
    return Promise.resolve(new Response(JSON.stringify({ promptFeedback: { blockReason: 'Play e4 now' } }), { status: 200 }));
  }) as unknown as typeof fetch;
  const metadataService = createCoachService({ env: fakeEnv, fetchImpl: poisonedMetadataFetch });
  const metadataResponse = await metadataService.ask({ question: 'study' });
  assert.equal(metadataResponse.status, 'blocked');
  assert.doesNotMatch(JSON.stringify(metadataResponse), /play.e4/i);
  assert.doesNotMatch(JSON.stringify(metadataService.status()), /play.e4/i);
  passed('Untrusted provider metadata and safety reasons cannot bypass the intent gate');


  const invalidSearch = await fetch(`${baseUrl}/api/games?search=a&search=b`);
  assert.equal(invalidSearch.status, 400);
  const invalidHistory = await fetch(`${baseUrl}/api/coach/ask`, { method: 'POST', headers: { 'content-type': 'application/json' }, body: JSON.stringify({ question: 'study', history: [null] }) });
  assert.equal(invalidHistory.status, 400);
  const validHistory = await postJson('/api/coach/ask', { question: 'study', history: [{ role: 'coach', text: 'Welcome' }] });
  assert.ok(validHistory.answer);
  passed('Malformed query and coach history inputs are rejected without breaking valid follow-ups');

  // 2. Searchable library, next coach, game detail
  const gamesPage = await requestJson('/api/games?search=Caro&page=1&limit=5');
  assert.ok(gamesPage.total > 0);
  assert.ok(Array.isArray(gamesPage.months) && gamesPage.months.length > 0);
  assert.ok(gamesPage.games.length > 0 && gamesPage.games.length <= 5);
  const chess960Page = await requestJson('/api/games?search=Chess960&limit=5');
  assert.equal(chess960Page.total, 20);
  assert.ok(chess960Page.games.every((game: JsonRecord) => game.analyzable === false));
  await assert.rejects(gameAnalyzer.analyzeGame(chess960Page.games[0].id), /variant cannot be analyzed/i);
  const unknownReset = await fetch(`${baseUrl}/api/mistakes/does-not-exist/reset`, { method: 'POST' });
  assert.equal(unknownReset.status, 404);
  passed('Variant analyses and resets of nonexistent mistakes are rejected');
  const variantRecord = pgnArchive.getGameById(chess960Page.games[0].id)!;
  const cacheMap = (gameAnalyzer as unknown as { cache: Map<string, ReturnType<typeof gameAnalyzer.getAllCached>[number]> }).cache;
  const variantAnalysis = { ...gameAnalyzer.getAllCached()[0], gameId: variantRecord.summary.id,
    mistakes: [{ ...gameAnalyzer.getAllCached()[0].mistakes[0], gameId: variantRecord.summary.id, id: 'variant-mistake-test' }] };
  cacheMap.set(variantRecord.summary.id, variantAnalysis);
  try {
    assert.equal(gameAnalyzer.buildGameDetailResponse(variantRecord).analyzed, false);
    assert.equal(gameAnalyzer.enrichGameSummary(variantRecord).analyzed, false);
    assert.equal(gameAnalyzer.getMistakeInternalById('variant-mistake-test'), null);
    const guardedVault = await requestJson('/api/mistakes');
    assert.ok(!guardedVault.mistakes.some((m: { id: string }) => m.id === 'variant-mistake-test'));
    const guardedOverview = await requestJson('/api/overview');
    assert.equal(guardedOverview.analyzedGamesCount, overview.analyzedGamesCount);
    const originalRecords = pgnArchive.getAllRecords;
    const originalWarmup = stockfishPool.warmup;
    pgnArchive.getAllRecords = () => [variantRecord];
    stockfishPool.warmup = async () => {};
    try {
      const variantOnly = await gameAnalyzer.analyzeAllGames();
      assert.equal(variantOnly.totalMistakes, overview.mistakeStats.totalDiscovered);
      assert.equal(variantOnly.skippedVariantGames, 1);
    } finally { pgnArchive.getAllRecords = originalRecords; stockfishPool.warmup = originalWarmup; }
  } finally { cacheMap.delete(variantRecord.summary.id); }
  passed('Legacy cached variants do not enter public drills or analysis statistics');

  const getMastery = progressStore.getRecord;
  progressStore.getRecord = ((id: string) => ({ ...getMastery.call(progressStore, id), status: 'mastered' })) as typeof getMastery;
  try {
    const masteredPlan = buildLearningPlan(emptyAnalyzeAllStatus());
    assert.equal(masteredPlan.dueCount, 0);
    assert.deepEqual(masteredPlan.recommendedDrills, []);
    const masteredCoach = await createCoachService({ env: {} }).ask({ question: 'study this week' });
    assert.match(masteredCoach.answer, /No drills are due right now/);
    assert.doesNotMatch(masteredCoach.answer, /Start with the first due drill/);
    writeLearningPlanFiles(emptyAnalyzeAllStatus());
    assert.match(fs.readFileSync(path.join(DATA_DIR, 'WHAT_TO_LEARN.md'), 'utf8'), /All discovered drills are mastered/);
  } finally { progressStore.getRecord = getMastery; }
  passed('Curriculum recommendations exclude mastered positions when no drills are due');

  assert.doesNotThrow(() => assertSpoilerFree({ opponent: 'bestMove', nested: [{ opening: 'solution' }] }, 'safe'));
  assert.throws(() => assertSpoilerFree({ nested: [{ bestMove: 'e4' }] }, 'unsafe'), /bestMove/);
  const originalGetGame = pgnArchive.getGameById;
  pgnArchive.getGameById = (id: string) => {
    const record = originalGetGame.call(pgnArchive, id);
    return record ? { ...record, summary: { ...record.summary, opponentName: 'bestMove' } } : record;
  };
  try {
    const planWithReservedName = buildLearningPlan(emptyAnalyzeAllStatus());
    assert.ok(planWithReservedName.recommendedDrills.some(drill => drill.opponent === 'bestMove'));
    const safeCoach = await createCoachService({ env: {} }).ask({ question: 'study' });
    assert.match(safeCoach.answer, /your opponent/);
    assertNoSolution(safeCoach, 'coach with reserved-name opponent');
  } finally { pgnArchive.getGameById = originalGetGame; }
  passed('Spoiler guard checks field names without rejecting matching player names');


  const nextCoach = await requestJson('/api/games/next-coach');
  assert.notEqual(nextCoach.game?.analyzable, false);
  assert.ok(nextCoach.game && nextCoach.game.id);
  const seededDetail = await requestJson(`/api/games/${encodeURIComponent(firstSeedGameId)}`);
  assert.equal(seededDetail.analyzed, true);
  assert.ok(seededDetail.plies.length > 0);
  assert.ok(seededDetail.mistakes.length > 0);
  for (const challenge of seededDetail.mistakes) {
    assertChallengeIsSpoilerFree(challenge, 'GET /api/games/:id');
  }
  passed('Games list, next-coach picker, and spoiler-free game detail');

  // 3. SSE progress + done payload
  const sse = await readSseDone(`/api/games/${encodeURIComponent(firstSeedGameId)}/analyze-stream`);
  assert.ok(sse.progressCount > 0, 'Expected at least one Stockfish progress event');
  assert.equal(sse.game.analyzed, true);
  for (const challenge of sse.game.mistakes) {
    assertChallengeIsSpoilerFree(challenge, 'SSE done payload');
  }
  passed(`SSE analysis stream emitted ${sse.progressCount} progress events and a spoiler-free done payload`);

  // 4. Cross-game mistake queue is also spoiler-free
  const vault = await requestJson('/api/mistakes?status=all');
  assert.ok(vault.total >= seedMistakes.length);
  for (const challenge of vault.mistakes) {
    assertChallengeIsSpoilerFree(challenge, 'GET /api/mistakes');
  }
  const publicById = new Map<string, JsonRecord>(
    vault.mistakes.map((challenge: JsonRecord) => [String(challenge.id), challenge])
  );
  passed(`Cross-game vault: ${vault.total} positions, zero solution fields`);

  // 5. Paste PGN import: Chess.com-style headers AND bare SAN move list
  const imported = await postJson('/api/pgn/import', {
    pgn: seededDetail.pgn,
    preferredSide: 'auto',
    playerHint: 'darrelnxt',
  });
  assert.ok(imported.importedCount >= 1);
  assert.equal(imported.games[0].source, 'custom');
  assert.match(String(imported.games[0].userName).toLowerCase(), /darrelnxt/);

  const bareSanImported = await postJson('/api/pgn/import', {
    pgn: '1. f3 e5 2. g4 Qh4# 0-1',
    preferredSide: 'w',
    playerHint: 'darrelnxt',
  });
  assert.ok(bareSanImported.importedCount >= 1);
  assert.equal(bareSanImported.games[0].userColor, 'w');
  assert.equal(bareSanImported.games[0].result, '0-1');
  assert.equal(bareSanImported.games[0].userOutcome, 'loss');
  const unfinishedImported = await postJson('/api/pgn/import', { pgn: '1. d4 d5 2. c4', preferredSide: 'w' });
  assert.equal(unfinishedImported.games[0].userOutcome, 'unfinished');
  passed('PGN import preserves movetext results and marks unfinished games correctly');
  const exactSide = await postJson('/api/pgn/import', {
    pgn: '[Event "Exact names"]\n[White "sam"]\n[Black "samantha"]\n\n1. e4 e5 *', playerHint: 'sam',
  });
  assert.equal(exactSide.games[0].userColor, 'w');
  const ambiguousSide = await fetch(`${baseUrl}/api/pgn/import`, { method: 'POST', headers: { 'content-type': 'application/json' }, body: JSON.stringify({
    pgn: '[Event "Unknown names"]\n[White "Alice"]\n[Black "Bob"]\n\n1. e4 e5 *', playerHint: 'sam',
  }) });
  assert.equal(ambiguousSide.status, 400);
  assert.match((await ambiguousSide.json()).error, /Choose White or Black/);
  passed('Auto side detection prefers exact names and rejects uncertain matches');

  const fenImported = await postJson('/api/pgn/import', {
    pgn: '[Event "Position"]\n[SetUp "1"]\n[FEN "r3k2r/8/8/8/8/8/8/R3K2R b KQkq - 0 23"]\n\n23... Ra7 24. Ke2 *', preferredSide: 'b',
  });
  let firstProgress!: () => void;
  const started = new Promise<void>(resolve => { firstProgress = resolve; });
  const analysis = gameAnalyzer.analyzeGame(fenImported.games[0].id, () => firstProgress(), { persist: false });
  await started;
  let joinProgress = 0;
  const joined = gameAnalyzer.analyzeGame(fenImported.games[0].id, () => { joinProgress++; });
  await Promise.all([analysis, joined]);
  assert.ok(joinProgress > 0, 'A late subscriber should receive current analysis progress');
  const persisted = JSON.parse(fs.readFileSync(path.join(DATA_DIR, 'analysis-cache.json'), 'utf8'));
  assert.ok(persisted[fenImported.games[0].id], 'Interactive join must persist an analysis even if a batch started it');
  passed('Concurrent analysis observers receive progress from a shared job');
  const fenDetail = await requestJson(`/api/games/${encodeURIComponent(fenImported.games[0].id)}`);
  assert.equal(fenImported.games[0].moveCount, 2);
  assert.deepEqual(fenDetail.plies.map((ply: { moveNumber: number }) => ply.moveNumber), [23, 24]);
  const groups = groupMoveSheet(fenDetail.plies);
  assert.equal(groups[0].number, 23);
  assert.equal(groups[0].white, undefined);
  assert.equal(groups[0].black?.san, 'Ra7');
  assert.equal(groups[1].number, 24);
  assert.equal(groups[1].white?.san, 'Ke2');
  const clockPlies = fenDetail.plies.map((ply: object, i: number) => ({ ...ply, clock: i === 0 ? '0:09:00' : '0:08:30' }));
  assert.deepEqual(clocksAtFen(clockPlies, clockPlies[0].fenBefore), { w: null, b: null });
  assert.deepEqual(clocksAtFen(clockPlies, clockPlies[0].fenAfter), { w: null, b: '0:09:00' });
  assert.deepEqual(clocksAtFen(clockPlies, clockPlies[1].fenAfter), { w: '0:08:30', b: '0:09:00' });
  assert.deepEqual(clocksAtFen(clockPlies, new Chess().fen()), { w: null, b: null });
  passed('Clocks follow the displayed recorded position rather than a future move');
  const captures = capturedPiecesByFen('[SetUp "1"]\n[FEN "r3k2r/8/8/8/8/8/8/R3K2R b KQkq - 0 23"]\n\n23... Ra7 24. Ke2 *');
  assert.deepEqual(captures.get(fenDetail.plies[0].fenBefore), { white: [], black: [] });
  const enPassant = new Chess();
  enPassant.loadPgn('1. e4 a6 2. e5 d5 3. exd6 *');
  const capturedHistory = capturedPiecesByFen('1. e4 a6 2. e5 d5 3. exd6 *');
  assert.deepEqual(capturedHistory.get(enPassant.fen()), { white: ['p'], black: [] });
  passed('Move sheets respect FEN turns and odds positions do not invent captures');
  assert.equal(lineMoveLabel(fenDetail.plies[0].fenBefore, 0), '23...');
  assert.equal(lineMoveLabel(fenDetail.plies[0].fenBefore, 1), '24.');
  assert.equal(lineMoveLabel(fenDetail.plies[0].fenBefore, 2), '24...');
  assert.equal(lineMoveLabel(fenDetail.plies[0].fenAfter, 0), '24.');
  passed('Engine line move labels honor the starting FEN and turn');
  assert.equal(archiveWinRate({ wins: 2, losses: 1, draws: 1 }), 50);
  assert.equal(archiveWinRate({ wins: 0, losses: 0, draws: 0 }), null);
  const ratings = preferredRatingSeries([
    { month: '2025-01', rapidElo: 1200, blitzElo: 900, bulletElo: null, games: 1 },
    { month: '2025-02', rapidElo: null, blitzElo: 2000, bulletElo: null, games: 1 },
    { month: '2025-03', rapidElo: 1250, blitzElo: null, bulletElo: null, games: 1 },
  ]);
  assert.equal(ratings.label, 'Rapid');
  assert.deepEqual(ratings.points.map(p => p.value), [1200, 1250]);
  passed('Archive win rate and rating trajectory use consistent populations');
  passed('Analysis preserves the move numbers of a custom black-to-move FEN');
  const lateStart = await postJson('/api/pgn/import', {
    pgn: '[Event "Later position"]\n[SetUp "1"]\n[FEN "rnbqkbnr/pppppppp/8/8/8/8/PPPPPPPP/RNBQKBNR w KQkq - 0 23"]\n\n23. e4 e5 *', preferredSide: 'w',
  });
  const streamPath = `/api/games/${encodeURIComponent(lateStart.games[0].id)}/analyze-stream`;
  const [lateStream, joinedStream] = await Promise.all([readSseDone(streamPath), readSseDone(streamPath)]);
  assert.ok(lateStream.progressCount > 0 && joinedStream.progressCount > 0, 'Both live streams must receive progress');
  assert.ok(lateStream.game.plies.every((ply: { classification: string }) => ply.classification !== 'book'));
  passed('Concurrent live SSE clients receive progress; late-start moves are not mislabeled as book');


  const updatedMirrorProfile = await requestJson('/api/mirror/profile');
  assert.ok(updatedMirrorProfile.indexed >= mirrorProfile.indexed + 2);
  assert.ok(updatedMirrorProfile.games >= mirrorProfile.games + 2);
  passed('Mirror profile refreshes when new games are imported');

  // 6. Real live Stockfish analysis of a newly pasted custom game
  const customGameId = String(imported.games[0].id);
  const customDetail = await postJson(
    `/api/games/${encodeURIComponent(customGameId)}/analyze`,
    {}
  );
  assert.equal(customDetail.analyzed, true);
  assert.equal(customDetail.summary.source, 'custom');
  assert.ok(customDetail.plies.length > 0);
  assert.ok(customDetail.mistakes.length > 0, 'Expected Stockfish to find mistakes in the imported game');
  for (const challenge of customDetail.mistakes) {
    assertChallengeIsSpoilerFree(challenge, 'custom PGN analysis');
  }
  const overviewAfterImport = await requestJson('/api/overview');
  assert.ok(overviewAfterImport.totalCustomGames >= 2);
  assert.ok(overviewAfterImport.analyzedGamesCount > overview.analyzedGamesCount);
  passed(
    `Live Stockfish analyzed pasted PGN: ${customDetail.plies.length} plies, ${customDetail.mistakes.length} mistakes`
  );

  // 7. Choose a deterministic wrong move for the strict reveal contract
  let challengeA: SeedMistake | null = null;
  let badUci: string | null = null;
  for (const mistake of seedMistakes.slice(0, 8)) {
    if (mistake.bestMove.uci === mistake.playedMove.uci) continue;
    const candidate = await findBadCandidate(mistake);
    if (candidate) {
      challengeA = mistake;
      badUci = candidate;
      break;
    }
  }
  assert.ok(challengeA && badUci, 'Could not find a deterministic wrong candidate move');
  const publicA = publicById.get(challengeA.id);
  assert.ok(publicA, `Missing public challenge for ${challengeA.id}`);
  assertChallengeIsSpoilerFree(publicA, 'selected challenge A');

  const challengeB = seedMistakes.find(
    (m) => m.id !== challengeA!.id && m.bestMove.uci !== m.playedMove.uci
  );
  assert.ok(challengeB, 'Expected a second mistake for the solved-first-try check');

  // 7a. Replaying the original game mistake reveals nothing and consumes no try
  const same = await postJson(`/api/mistakes/${encodeURIComponent(challengeA.id)}/attempt`, {
    moveUci: challengeA.playedMove.uci,
    attemptNumber: 1,
    maxAttempts: 1,
    isPracticeRetry: true,
  });
  assert.equal(same.outcome, 'same_as_game');
  assert.ok(!('solution' in same));
  assertNoSolution(same, 'same_as_game attempt');
  passed('Original game move: no reveal, no attempt consumed');

  // 7b. Two-try mode: first wrong attempt must NOT reveal the answer
  const retry = await postJson(`/api/mistakes/${encodeURIComponent(challengeA.id)}/attempt`, {
    moveUci: badUci,
    attemptNumber: 1,
    maxAttempts: 2,
    isPracticeRetry: true,
  });
  assert.equal(retry.outcome, 'retry');
  assert.ok(!('solution' in retry));
  assertNoSolution(retry, 'retry attempt');
  assert.deepEqual(retry.candidateRefutationPvSan, [], 'Retry must not reveal a principal variation');
  assert.doesNotMatch(retry.feedbackDetail, /opponent replies/i);
  passed(`Two-try mode: ${retry.candidateMove.san} kept the best move hidden`);

  // 7c. Final failed attempt NOW unlocks the exact Stockfish solution
  const failed = await postJson(`/api/mistakes/${encodeURIComponent(challengeA.id)}/attempt`, {
    moveUci: badUci,
    attemptNumber: 2,
    maxAttempts: 2,
    isPracticeRetry: true,
  });
  assert.equal(failed.outcome, 'failed_revealed');
  assert.ok(failed.solution, 'Expected a solution after the final failure');
  assert.equal(failed.solution.bestMove.uci, challengeA.bestMove.uci);
  assert.ok(Array.isArray(failed.solution.bestPvSan));
  assert.match(failed.solution.coachExplanation, /engine lines, not guarantees/i);
  assert.doesNotMatch(failed.solution.coachExplanation, /winning a|develops cleanly|stabilizes king safety/i);
  assert.equal(failed.mastery.status, 'needs_review');
  passed(`Final failure revealed Stockfish #1 ${failed.solution.bestMove.san} and queued it for review`);

  // 7d. Default strict one-try mode reveals on the first failure
  const strictFail = await postJson(`/api/mistakes/${encodeURIComponent(challengeA.id)}/attempt`, {
    moveUci: badUci,
    attemptNumber: 1,
    maxAttempts: 1,
    isPracticeRetry: true,
  });
  assert.equal(strictFail.outcome, 'failed_revealed');
  assert.equal(strictFail.solution.bestMove.uci, challengeA.bestMove.uci);
  passed('Strict one-try mode reveals only after the first failed attempt');

  // Solving ends the drill without exposing a best line or distinguishing #1.
  const solved = await postJson(`/api/mistakes/${encodeURIComponent(challengeB.id)}/attempt`, {
    moveUci: challengeB.bestMove.uci,
    attemptNumber: 1,
    maxAttempts: 1,
    isPracticeRetry: true,
  });
  assert.equal(solved.outcome, 'great');
  assertNoSolution(solved, 'blind solve');
  assert.deepEqual(solved.candidateRefutationPvSan, []);
  assert.doesNotMatch(solved.feedbackHeadline + solved.feedbackDetail, /#1|top pick|best move/i);
  passed('Blind solve records success without revealing a best line');

  // A mate delivered on the board is represented by Stockfish as mate 0 from
  // the mated side's turn, not a positive mate distance for the mover.
  const findMistake = gameAnalyzer.getMistakeInternalById;
  const mateChallenge = {
    ...gameAnalyzer.getAllCached()[0].mistakes[0],
    id: 'test-alternative-mate', userColor: 'w' as const,
    fenBefore: '8/8/8/8/1Q6/4K3/8/3k4 w - - 0 1',
    playedMove: { uci: 'b4a3', san: 'Qa3', from: 'b4', to: 'a3' },
    bestMove: { uci: 'b4d2', san: 'Qd2#', from: 'b4', to: 'd2' },
    bestEvalUserCp: 9940, bestEvalUserMate: 1,
    evalAfterPlayedUserCp: 0, evalAfterPlayedUserMate: null, alternatives: [],
  };
  gameAnalyzer.getMistakeInternalById = (() => ({ ...findMistake.call(gameAnalyzer, challengeB.id)!, mistake: mateChallenge })) as typeof findMistake;
  try {
    const alternativeMate = await gameAnalyzer.evaluateAttempt(mateChallenge.id, { moveUci: 'b4b1', attemptNumber: 1, maxAttempts: 1 });
    assert.equal(alternativeMate.outcome, 'great');
    assertNoSolution(alternativeMate, 'alternate checkmate');
    assert.deepEqual(alternativeMate.candidateRefutationPvSan, []);
  } finally { gameAnalyzer.getMistakeInternalById = findMistake; }
  passed('Alternative checkmating moves are accepted without disclosing the engine line');

  // 8. Reset mastery endpoint, then re-verify no public route ever leaks solutions
  const reset = await postJson(`/api/mistakes/${encodeURIComponent(challengeA.id)}/reset`, {});
  assert.equal(reset.mastery.status, 'unseen');
  const finalDetail = await requestJson(`/api/games/${encodeURIComponent(challengeA.gameId)}`);
  for (const challenge of finalDetail.mistakes) {
    assertChallengeIsSpoilerFree(challenge, 'final game detail');
  }
  const finalVault = await requestJson('/api/mistakes?status=due');
  for (const challenge of finalVault.mistakes) {
    assertChallengeIsSpoilerFree(challenge, 'final due queue');
  }
  passed('Mastery reset works and all public routes remain spoiler-free');

  // 8b. Adding/changing/removing a server-only key must not require a restart.
  const { loadLocalEnv } = await import('./env.js');
  const envPath = TEST_ENV_PATH;
  const envBackup = fs.existsSync(envPath) ? fs.readFileSync(envPath) : null;
  try {
    fs.writeFileSync(envPath, 'GEMINI_API_KEY=self-test-reload-key\n', 'utf8');
    assert.ok(loadLocalEnv().includes('GEMINI_API_KEY'));
    assert.equal(process.env.GEMINI_API_KEY, 'self-test-reload-key');
    fs.writeFileSync(envPath, 'GEMINI_API_KEY=self-test-reload-key-2\n', 'utf8');
    loadLocalEnv();
    assert.equal(process.env.GEMINI_API_KEY, 'self-test-reload-key-2');
    fs.writeFileSync(envPath, '\uFEFFexport GEMINI_API_KEY="quoted-key#part" # keep comment outside the key\nGEMINI_MODEL=gemini-test # model alias\n', 'utf8');
    loadLocalEnv();
    assert.equal(process.env.GEMINI_API_KEY, 'quoted-key#part');
    assert.equal(process.env.GEMINI_MODEL, 'gemini-test');
    fs.writeFileSync(envPath, 'GEMINI_API_KEY=unquoted-key # comment\n', 'utf8');
    loadLocalEnv();
    assert.equal(process.env.GEMINI_API_KEY, 'unquoted-key');
    assert.equal(process.env.GEMINI_MODEL, undefined);
    fs.rmSync(envPath);
    fs.mkdirSync(envPath);
    assert.doesNotThrow(() => loadLocalEnv());
    assert.equal(process.env.GEMINI_API_KEY, undefined);
    fs.rmdirSync(envPath);

    fs.rmSync(envPath, { force: true });
    loadLocalEnv();
    assert.equal(process.env.GEMINI_API_KEY, undefined);
    passed('Server rereads .env add/change/remove without a restart');
  } finally {
    delete process.env.GEMINI_API_KEY;
    if (envBackup === null) fs.rmSync(envPath, { force: true });
    else fs.writeFileSync(envPath, envBackup);
    loadLocalEnv();
  }

  const elapsed = ((Date.now() - startedAt) / 1000).toFixed(2);
  console.log(`\n✅ All REST/SSE, PGN import, Stockfish 18, and anti-spoiler checks passed in ${elapsed}s.\n`);
} catch (error) {
  console.error('\n❌ Self-test failed:', error instanceof Error ? error.stack ?? error.message : error);
  process.exitCode = 1;
} finally {
  if (server) {
    server.closeAllConnections?.();
    await new Promise<void>((resolve) => server!.close(() => resolve()));
  }
  stockfishPool.shutdown();
  fs.rmSync(DATA_DIR, { recursive: true, force: true });
  process.exit(process.exitCode ?? 0);
}
