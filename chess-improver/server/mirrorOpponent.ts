import { Chess } from 'chess.js';
import { pgnArchive } from './pgnArchive.js';
import { stockfishPool } from './stockfishPool.js';
import { gameAnalyzer } from './analyzer.js';

// Only exact positions with the same side to move and castling/en-passant
// rights are comparable. Clocks do not affect legal moves.
const positionKey = (fen: string) => fen.split(' ').slice(0, 4).join(' ');
type Profile = { positions: Map<string, Map<string, number>>; games: number; skipped: number; indexed: number };
let cache: { key: string; promise: Promise<Profile> } | null = null;

export function getMirrorProfile(): Promise<Profile> {
  const records = pgnArchive.getAllRecords();
  const key = records.map(r => r.summary.id).sort().join('|');
  if (cache?.key === key) return cache.promise;
  const promise = (async () => {
    const profile: Profile = { positions: new Map(), games: 0, skipped: 0, indexed: records.length };
    for (let i = 0; i < records.length; i++) {
      const { pgn, summary } = records[i];
      if (summary.analyzable === false) { profile.skipped++; continue; }
      try {
        const chess = new Chess();
        chess.loadPgn(pgn);
        const moves = chess.history({ verbose: true });
        for (const move of moves) {
          if (move.color !== summary.userColor) continue;
          const key = positionKey(move.before);
          let counts = profile.positions.get(key);
          if (!counts) profile.positions.set(key, counts = new Map());
          const uci = `${move.from}${move.to}${move.promotion ?? ''}`;
          counts.set(uci, (counts.get(uci) ?? 0) + 1);
        }
        profile.games++;
      } catch {
        profile.skipped++;
      }
      // Keep HTTP and the rest of the app responsive while building the profile.
      if (i % 5 === 4) await new Promise<void>(resolve => setImmediate(resolve));
    }
    return profile;
  })();
  cache = { key, promise };
  promise.catch(() => { if (cache?.promise === promise) cache = null; });
  return promise;
}

export async function mirrorMove(moves: unknown) {
  if (!Array.isArray(moves) || moves.length > 300 || moves.some(m => typeof m !== 'string' || !/^[a-h][1-8][a-h][1-8][qrbn]?$/.test(m))) {
    throw new Error('Moves must be a list of legal UCI moves (maximum 300).');
  }
  const chess = new Chess();
  for (const [index, uci] of (moves as string[]).entries()) {
    try { chess.move({ from: uci.slice(0, 2), to: uci.slice(2, 4), promotion: uci[4] }); }
    catch { throw new Error('The move history contains an illegal move.'); }
    if (chess.isGameOver() && index < moves.length - 1) throw new Error('Moves continue after the game ended.');
  }
  if (chess.isGameOver()) throw new Error('The game is already over.');
  // Mirror must not be usable as an engine-answer oracle for a blind drill.
  // Conservatively block all analyzed challenge positions, even if previously
  // solved, since a fresh blind retry can be started at any time.
  const target = positionKey(chess.fen());
  const assertNotBlindDrill = () => {
    if (gameAnalyzer.getAllCached().some(a => a.mistakes.some(m => positionKey(m.fenBefore) === target))) {
      throw new Error('This position is a blind drill. Start a new mirror game to keep its answer hidden.');
    }
  };
  assertNotBlindDrill();
  const profile = await getMirrorProfile();
  // A concurrent analysis may have made this a blind drill while we waited.
  assertNotBlindDrill();
  const counts = profile.positions.get(positionKey(chess.fen()));
  const legal = new Set(chess.moves({ verbose: true }).map(m => `${m.from}${m.to}${m.promotion ?? ''}`));
  const choices = counts ? [...counts].filter(([move]) => legal.has(move)).sort((a, b) => b[1] - a[1] || a[0].localeCompare(b[0])) : [];
  if (choices.length) {
    return { move: choices[0][0], source: 'archive' as const, occurrences: choices[0][1], samples: choices.reduce((n, c) => n + c[1], 0) };
  }
  const result = await stockfishPool.evaluateFen(chess.fen(), { depth: 8, multiPv: 1, movetimeMs: 350 });
  assertNotBlindDrill();
  if (!result.bestMoveUci || !legal.has(result.bestMoveUci)) throw new Error('Stockfish could not find a legal reply.');
  return { move: result.bestMoveUci, source: 'stockfish' as const, occurrences: 0, samples: 0 };
}
