import type { AnalyzeAllProgress, AnalyzeAllStatus, AnalyzeAllResult } from '../shared/types.js';
import { gameAnalyzer } from './analyzer.js';
import { emptyAnalyzeAllStatus, writeLearningPlanFiles } from './learningPlan.js';
import { stockfishPool } from './stockfishPool.js';

const PORT = Number(process.env.PORT || 5173);
const BASE_URL = `http://127.0.0.1:${PORT}`;

async function serverIsUp(): Promise<boolean> {
  try {
    const response = await fetch(`${BASE_URL}/api/health`, {
      signal: AbortSignal.timeout(1200),
    });
    return response.ok;
  } catch {
    return false;
  }
}

async function driveRunningServer(): Promise<void> {
  console.log(`[chess] Found a running Chess Improver server on port ${PORT}; using its Stockfish pool.`);

  const startResponse = await fetch(`${BASE_URL}/api/admin/analyze-all`, {
    method: 'POST',
    signal: AbortSignal.timeout(10_000),
  });
  if (!startResponse.ok) {
    throw new Error(`Could not start batch analysis (HTTP ${startResponse.status})`);
  }
  const start = (await startResponse.json()) as { started: boolean; status: AnalyzeAllStatus };
  console.log(
    start.started
      ? '[chess] Full-archive analysis started.'
      : '[chess] Full-archive analysis was already running.'
  );

  let lastPercent = -1;
  // eslint-disable-next-line no-constant-condition
  while (true) {
    const statusResponse = await fetch(`${BASE_URL}/api/admin/analyze-all/status`, {
      signal: AbortSignal.timeout(10_000),
    });
    if (!statusResponse.ok) {
      throw new Error(`Could not read batch status (HTTP ${statusResponse.status})`);
    }
    const status = (await statusResponse.json()) as AnalyzeAllStatus;

    if (status.percent !== lastPercent) {
      console.log(
        `[chess] ${status.percent}% · ${status.processed}/${status.total} games · ` +
          `${status.analyzed} newly analyzed · ${status.totalMistakes} mistakes · ETA ${status.etaSeconds ?? '—'}s`
      );
      lastPercent = status.percent;
    }

    if (!status.running) {
      if (status.error) throw new Error(status.error);
      console.log('[chess] Full-archive analysis complete. data/WHAT_TO_LEARN.md and the Mistake Vault are updated.');
      return;
    }

    await new Promise((resolve) => setTimeout(resolve, 5000));
  }
}

async function runDirectly(): Promise<void> {
  console.log('[chess] No server detected; analyzing directly with local Stockfish 18 NNUE.');
  const startedAt = new Date().toISOString();
  let lastProgress: AnalyzeAllProgress | null = null;
  let lastPercent = -1;

  const result: AnalyzeAllResult = await gameAnalyzer.analyzeAllGames((progress) => {
    lastProgress = progress;
    if (progress.percent !== lastPercent && (progress.percent % 5 === 0 || progress.percent === 100)) {
      console.log(
        `[chess] ${progress.percent}% · ${progress.processed}/${progress.total} games · ` +
          `${progress.analyzed} newly analyzed · ${progress.totalMistakes} mistakes · ETA ${progress.etaSeconds ?? '—'}s`
      );
      lastPercent = progress.percent;
    }
  });

  const finalStatus: AnalyzeAllStatus = {
    ...emptyAnalyzeAllStatus(),
    ...(lastProgress ?? {}),
    running: false,
    startedAt,
    finishedAt: new Date().toISOString(),
    message: 'Full archive analysis complete',
    error: null,
    result,
    percent: 100,
  };
  writeLearningPlanFiles(finalStatus);

  console.log(
    `[chess] Complete: ${result.analyzedGames} newly analyzed, ${result.skippedGames} cached, ` +
      `${result.skippedVariantGames} Chess960 indexed, ${result.failedGames} failed, ` +
      `${result.totalMistakes} total mistakes in ${result.durationSeconds}s.`
  );
  console.log('[chess] Wrote chess-improver/data/analysis-cache.json and chess-improver/data/WHAT_TO_LEARN.md');
}

async function main() {
  try {
    if (await serverIsUp()) {
      await driveRunningServer();
    } else {
      await runDirectly();
    }
  } catch (err) {
    console.error('[chess] Full-archive analysis failed:', err instanceof Error ? err.message : err);
    process.exitCode = 1;
  } finally {
    stockfishPool.shutdown();
    process.exit(process.exitCode ?? 0);
  }
}

void main();
