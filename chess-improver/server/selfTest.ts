import assert from 'node:assert/strict';
import fs from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';
import type { Server } from 'node:http';
import type { AddressInfo } from 'node:net';
import { Chess } from 'chess.js';

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const DATA_DIR = path.resolve(__dirname, '../data');
const SEED_PATH = path.join(DATA_DIR, 'preanalyzed-games.json');

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

const WATCHED_FILES = [
  'user-progress.json',
  'custom-games.json',
  'analysis-cache.json',
  'learning-plan.json',
  'WHAT_TO_LEARN.md',
  'analyze-all-progress.json',
].map((name) => path.join(DATA_DIR, name));
WATCHED_FILES.push(path.resolve(__dirname, '../.env'));

const snapshots = WATCHED_FILES.map((filePath) => ({
  filePath,
  bytes: fs.existsSync(filePath) ? fs.readFileSync(filePath) : null,
}));

function restoreWatchedFiles() {
  for (const snapshot of snapshots) {
    if (snapshot.bytes === null) {
      fs.rmSync(snapshot.filePath, { force: true });
    } else {
      fs.writeFileSync(snapshot.filePath, snapshot.bytes);
    }
  }
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
const { progressStore } = await import('./progressStore.js');
const { pgnArchive } = await import('./pgnArchive.js');

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
  const limited = createCoachService({ env: { ...fakeEnv, GEMINI_DAILY_CALL_BUDGET: '1' }, fetchImpl: fakeGeminiFetch('STUDY') });
  const concurrent = await Promise.all([limited.ask({ question: 'study' }), limited.ask({ question: 'training' })]);
  assert.equal(concurrent.filter(a => a.source === 'gemini').length, 1);
  assert.equal(concurrent.filter(a => a.status === 'quota').length, 1);
  passed('Concurrent coach requests cannot exceed the daily budget');

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
    if (url.includes('gemini-self-test')) {
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
  assert.equal(discovered.model, 'gemini-discovered-flash');
  assert.match(discovered.answer, /Current recall/i);
  assert.equal(discoveryService.status().lastProviderError, null);
  passed('Gemini discovers a supported model after a retired alias 404s');

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

  // 2. Searchable library, next coach, game detail
  const gamesPage = await requestJson('/api/games?search=Caro&page=1&limit=5');
  assert.ok(gamesPage.total > 0);
  assert.ok(Array.isArray(gamesPage.months) && gamesPage.months.length > 0);
  assert.ok(gamesPage.games.length > 0 && gamesPage.games.length <= 5);
  const chess960Page = await requestJson('/api/games?search=Chess960&limit=5');
  assert.equal(chess960Page.total, 20);
  assert.ok(chess960Page.games.every((game: JsonRecord) => game.analyzable === false));
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

  // 7e. Solving blind with Stockfish's #1 move unlocks the full line
  const solved = await postJson(`/api/mistakes/${encodeURIComponent(challengeB.id)}/attempt`, {
    moveUci: challengeB.bestMove.uci,
    attemptNumber: 1,
    maxAttempts: 1,
    isPracticeRetry: true,
  });
  assert.equal(solved.outcome, 'best');
  assert.ok(solved.solution);
  assert.equal(solved.solution.bestMove.uci, challengeB.bestMove.uci);
  passed(`Blind solve recognized ${solved.solution.bestMove.san}`);

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
  const envPath = path.resolve(__dirname, '../.env');
  const envBackup = fs.existsSync(envPath) ? fs.readFileSync(envPath) : null;
  try {
    fs.writeFileSync(envPath, 'GEMINI_API_KEY=self-test-reload-key\n', 'utf8');
    assert.ok(loadLocalEnv().includes('GEMINI_API_KEY'));
    assert.equal(process.env.GEMINI_API_KEY, 'self-test-reload-key');
    fs.writeFileSync(envPath, 'GEMINI_API_KEY=self-test-reload-key-2\n', 'utf8');
    loadLocalEnv();
    assert.equal(process.env.GEMINI_API_KEY, 'self-test-reload-key-2');
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
  restoreWatchedFiles();
  process.exit(process.exitCode ?? 0);
}
