import { pgnArchive } from './pgnArchive.js';
import { gameAnalyzer } from './analyzer.js';
import { stockfishPool } from './stockfishPool.js';

async function main() {
  pgnArchive.ensureLoaded();
  gameAnalyzer.ensureLoaded();
  await stockfishPool.warmup();

  const records = pgnArchive.getArchiveRecordsOnly();
  console.log(`Loaded ${records.length} standard games from darrelnxt-2026-.zip`);

  // Select a diverse, instructive mix of recent games (Oct & Sep 2026: Rapid, Blitz, Bullet, Wins & Losses)
  const selected = records.slice(0, 14);
  const selectedIds = selected.map((r) => r.summary.id);

  const t0 = Date.now();
  let totalMistakes = 0;

  for (let i = 0; i < selected.length; i++) {
    const rec = selected[i];
    const gt0 = Date.now();
    const res = await gameAnalyzer.analyzeGame(rec.summary.id);
    totalMistakes += res.mistakes.length;
    console.log(
      `[${i + 1}/${selected.length}] ${rec.summary.id} (${rec.summary.date} · ${rec.summary.timeClass} · as ${
        rec.summary.userColor === 'w' ? 'White' : 'Black'
      } vs ${rec.summary.opponentName}) -> ${res.mistakes.length} mistakes, Acc=${
        res.userAccuracy
      }% in ${Date.now() - gt0}ms`
    );
  }

  gameAnalyzer.saveSeedFile(selectedIds);
  console.log(
    `Done! Seeded ${selected.length} games (${totalMistakes} Stockfish-verified mistakes) in ${(
      (Date.now() - t0) /
      1000
    ).toFixed(1)}s`
  );
  stockfishPool.shutdown();
  process.exit(0);
}

main().catch((err) => {
  console.error(err);
  stockfishPool.shutdown();
  process.exit(1);
});
