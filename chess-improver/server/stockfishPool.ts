import { spawn, ChildProcessWithoutNullStreams } from 'node:child_process';
import path from 'node:path';
import { fileURLToPath } from 'node:url';
import { Chess } from 'chess.js';

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const ENGINE_PATH = path.resolve(
  __dirname,
  '../node_modules/stockfish/bin/stockfish-18-lite-single.js'
);

export interface EngineLine {
  multipv: number;
  /** Score in centipawns from the side-to-move's perspective (mates mapped near +-10000) */
  cpFromTurn: number;
  /** Mate in N moves from side-to-move's perspective (+N = side to move mates, -N = side to move gets mated) */
  mateFromTurn: number | null;
  pvUci: string[];
}

export interface EngineEvalResult {
  bestMoveUci: string | null;
  lines: EngineLine[];
}

interface EvalJob {
  fen: string;
  depth: number;
  multiPv: number;
  movetimeMs?: number;
  resolve: (res: EngineEvalResult) => void;
  reject: (err: Error) => void;
}

export function mateToCp(mate: number): number {
  if (mate === 0) return -10000;
  if (mate > 0) return Math.max(2500, 10000 - mate * 60);
  return Math.min(-2500, -10000 - mate * 60);
}

class StockfishWorker {
  private proc!: ChildProcessWithoutNullStreams;
  private buffer = '';
  private ready = false;
  public busy = false;
  private lineListeners: ((line: string) => void)[] = [];
  private id: number;

  constructor(id: number) {
    this.id = id;
    this.spawnEngine();
  }

  private spawnEngine() {
    this.ready = false;
    this.buffer = '';
    this.proc = spawn(process.execPath, [ENGINE_PATH], {
      stdio: ['pipe', 'pipe', 'pipe'],
    });

    this.proc.stdout.on('data', (chunk: Buffer) => {
      this.buffer += chunk.toString('utf8');
      let nlIdx: number;
      while ((nlIdx = this.buffer.indexOf('\n')) !== -1) {
        const line = this.buffer.slice(0, nlIdx).trim();
        this.buffer = this.buffer.slice(nlIdx + 1);
        if (line) {
          for (const listener of [...this.lineListeners]) {
            listener(line);
          }
        }
      }
    });

    this.proc.on('exit', () => {
      this.ready = false;
    });
  }

  private waitForLine(predicate: (line: string) => boolean, timeoutMs = 10000): Promise<string> {
    return new Promise((resolve, reject) => {
      const timer = setTimeout(() => {
        this.removeListener(onLine);
        reject(new Error(`Stockfish worker #${this.id} timed out waiting for response`));
      }, timeoutMs);

      const onLine = (line: string) => {
        if (predicate(line)) {
          clearTimeout(timer);
          this.removeListener(onLine);
          resolve(line);
        }
      };
      this.lineListeners.push(onLine);
    });
  }

  private removeListener(fn: (line: string) => void) {
    const idx = this.lineListeners.indexOf(fn);
    if (idx !== -1) this.lineListeners.splice(idx, 1);
  }

  private send(cmd: string) {
    if (this.proc.stdin.writable) {
      this.proc.stdin.write(cmd + '\n');
    }
  }

  async ensureReady(): Promise<void> {
    if (this.ready && this.proc && !this.proc.killed) return;
    if (!this.proc || this.proc.killed || this.proc.exitCode !== null) {
      this.spawnEngine();
    }
    const uciPromise = this.waitForLine((l) => l === 'uciok', 10000);
    this.send('uci');
    await uciPromise;

    this.send('setoption name Hash value 32');
    const readyPromise = this.waitForLine((l) => l === 'readyok', 10000);
    this.send('isready');
    await readyPromise;
    this.ready = true;
  }

  async evaluate(
    fen: string,
    depth: number,
    multiPv: number,
    movetimeMs?: number
  ): Promise<EngineEvalResult> {
    await this.ensureReady();

    this.send(`setoption name MultiPV value ${multiPv}`);
    const readySync = this.waitForLine((l) => l === 'readyok', 6000);
    this.send('isready');
    await readySync;

    const latestByPv = new Map<number, { depth: number; line: EngineLine }>();

    return new Promise<EngineEvalResult>((resolve, reject) => {
      const timer = setTimeout(() => {
        this.removeListener(onLine);
        try {
          this.proc.kill('SIGKILL');
        } catch {
          // ignore
        }
        this.spawnEngine();
        reject(new Error(`Stockfish search timed out on FEN: ${fen}`));
      }, 15000);

      const onLine = (line: string) => {
        if (line.startsWith('info ') && line.includes(' score ') && line.includes(' pv ')) {
          const depthMatch = line.match(/\bdepth\s+(\d+)/);
          const pvIdxMatch = line.match(/\bmultipv\s+(\d+)/);
          const cpMatch = line.match(/\bscore\s+cp\s+(-?\d+)/);
          const mateMatch = line.match(/\bscore\s+mate\s+(-?\d+)/);
          const pvMovesMatch = line.match(/\bpv\s+(.+)$/);

          if (depthMatch && pvMovesMatch && (cpMatch || mateMatch)) {
            const d = parseInt(depthMatch[1], 10);
            const mpv = pvIdxMatch ? parseInt(pvIdxMatch[1], 10) : 1;
            const mateFromTurn = mateMatch ? parseInt(mateMatch[1], 10) : null;
            const cpFromTurn =
              mateFromTurn !== null
                ? mateToCp(mateFromTurn)
                : parseInt(cpMatch![1], 10);
            const pvUci = pvMovesMatch[1].trim().split(/\s+/);

            const prev = latestByPv.get(mpv);
            if (!prev || d >= prev.depth) {
              latestByPv.set(mpv, {
                depth: d,
                line: {
                  multipv: mpv,
                  cpFromTurn,
                  mateFromTurn,
                  pvUci,
                },
              });
            }
          }
        } else if (line.startsWith('bestmove ')) {
          clearTimeout(timer);
          this.removeListener(onLine);
          const parts = line.split(/\s+/);
          const rawBest = parts[1] && parts[1] !== '(none)' ? parts[1] : null;
          const lines = Array.from(latestByPv.values())
            .map((v) => v.line)
            .sort((a, b) => a.multipv - b.multipv);

          resolve({
            bestMoveUci: rawBest ?? lines[0]?.pvUci[0] ?? null,
            lines,
          });
        }
      };

      this.lineListeners.push(onLine);
      this.send(`position fen ${fen}`);
      if (movetimeMs) {
        this.send(`go depth ${depth} movetime ${movetimeMs}`);
      } else {
        this.send(`go depth ${depth}`);
      }
    });
  }

  shutdown() {
    try {
      this.send('quit');
      this.proc.kill();
    } catch {
      // ignore
    }
  }
}

export class StockfishPool {
  private workers: StockfishWorker[];
  private queue: EvalJob[] = [];

  constructor(size = 2) {
    this.workers = Array.from({ length: size }, (_, i) => new StockfishWorker(i + 1));
  }

  async warmup(): Promise<void> {
    await Promise.all(this.workers.map((w) => w.ensureReady()));
  }

  evaluateFen(
    fen: string,
    opts: { depth?: number; multiPv?: number; movetimeMs?: number } = {}
  ): Promise<EngineEvalResult> {
    // Handle terminal positions synchronously via chess.js
    const chess = new Chess(fen);
    if (chess.isGameOver()) {
      if (chess.isCheckmate()) {
        return Promise.resolve({
          bestMoveUci: null,
          lines: [{ multipv: 1, cpFromTurn: -10000, mateFromTurn: 0, pvUci: [] }],
        });
      }
      return Promise.resolve({
        bestMoveUci: null,
        lines: [{ multipv: 1, cpFromTurn: 0, mateFromTurn: null, pvUci: [] }],
      });
    }

    const depth = opts.depth ?? 10;
    const multiPv = opts.multiPv ?? 1;

    return new Promise<EngineEvalResult>((resolve, reject) => {
      this.queue.push({
        fen,
        depth,
        multiPv,
        movetimeMs: opts.movetimeMs,
        resolve,
        reject,
      });
      this.drain();
    });
  }

  private drain() {
    while (this.queue.length > 0) {
      const idleWorker = this.workers.find((w) => !w.busy);
      if (!idleWorker) break;

      const job = this.queue.shift()!;
      idleWorker.busy = true;
      idleWorker
        .evaluate(job.fen, job.depth, job.multiPv, job.movetimeMs)
        .then(job.resolve)
        .catch(job.reject)
        .finally(() => {
          idleWorker.busy = false;
          this.drain();
        });
    }
  }

  shutdown() {
    for (const w of this.workers) w.shutdown();
  }
}

export const stockfishPool = new StockfishPool(2);
