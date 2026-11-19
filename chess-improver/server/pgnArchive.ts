import fs from 'node:fs';
import path from 'node:path';
import crypto from 'node:crypto';
import { fileURLToPath } from 'node:url';
import AdmZip from 'adm-zip';
import { Chess } from 'chess.js';
import { writeFileAtomic } from './atomicFile.js';
import type {
  GameOutcome,
  GameSummary,
  PlayerColor,
  TimeClass,
} from '../shared/types.js';

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const REPO_ROOT = path.resolve(__dirname, '../..');
const DATA_DIR = process.env.CHESS_DATA_DIR ? path.resolve(process.env.CHESS_DATA_DIR) : path.resolve(__dirname, '../data');
const CUSTOM_GAMES_PATH = path.join(DATA_DIR, 'custom-games.json');
const DEFAULT_USERNAME = 'darrelnxt';

export interface StoredGameRecord {
  summary: Omit<
    GameSummary,
    | 'analyzed'
    | 'accuracy'
    | 'blundersCount'
    | 'mistakesCount'
    | 'inaccuraciesCount'
    | 'totalMistakesCount'
    | 'masteredMistakesCount'
  >;
  pgn: string;
}

function classifyTimeControl(tc: string): TimeClass {
  if (!tc || tc === '-') return 'rapid';
  const match = tc.match(/^(\d+)(?:\+(\d+))?/);
  if (!match) return 'rapid';
  const base = parseInt(match[1], 10);
  const inc = match[2] ? parseInt(match[2], 10) : 0;
  const estimatedTotal = base + 40 * inc;
  if (estimatedTotal < 180) return 'bullet';
  if (estimatedTotal < 600) return 'blitz';
  if (estimatedTotal <= 1800) return 'rapid';
  return 'classical';
}

function cleanOpeningName(ecoUrl?: string, openingHeader?: string, eco?: string): string {
  if (openingHeader && openingHeader !== '?') {
    return openingHeader;
  }
  if (ecoUrl) {
    const slug = ecoUrl.split('/').pop() || '';
    // Strip move numbers at the tail like -2.Nf3-d5-3.exd5
    const withoutMoves = slug.replace(/-\d+\..*$/, '').replace(/-/g, ' ').trim();
    if (withoutMoves) {
      // Shorten overly verbose prefixes nicely
      return withoutMoves
        .replace(/^Queens Pawn Opening /, "Queen's Pawn · ")
        .replace(/^Kings Pawn Opening /, "King's Pawn · ");
    }
  }
  return eco ? `Opening (${eco})` : 'Standard Chess';
}

function parseHeaders(rawPgn: string): Record<string, string> {
  const headers: Record<string, string> = {};
  let inComment = false;
  for (const line of rawPgn.split(/\r?\n/)) {
    // Comment markers are ordinary characters inside a quoted PGN tag.
    // Recognize a complete tag before stripping movetext comments.
    if (!inComment) {
      const tag = line.trim().match(/^\[(\w+)\s+"([^"\r\n]*)"\]\s*$/);
      if (tag) { headers[tag[1]] = tag[2]; continue; }
    }
    let visible = '';
    for (const ch of line) {
      if (inComment) { if (ch === '}') inComment = false; continue; }
      if (ch === ';') break;
      if (ch === '{') { inComment = true; continue; }
      visible += ch;
    }
    const trimmed = visible.trim();
    if (!trimmed) continue;
    const tag = trimmed.match(/^\[(\w+)\s+"([^"\r\n]*)"\]\s*$/);
    if (!tag) break; // A tag in movetext is not game metadata.
    headers[tag[1]] = tag[2];
  }
  return headers;
}

function estimateMoveCount(rawPgn: string): number {
  const body = rawPgn.replace(/^\[[^\]]*\]\s*/gm, '');
  const withoutComments = body.replace(/\{[^}]*\}/g, '');
  const nums = withoutComments.match(/\b(\d+)\.(?!\.)/g);
  if (!nums || nums.length === 0) return 0;
  const last = nums[nums.length - 1];
  return parseInt(last, 10) || nums.length;
}

/** Split on the next game's tag section, regardless of tag order. Ignore
 * tag-like text inside multi-line brace or semicolon comments. */
function splitPgnGames(input: string): string[] {
  const chunks: string[] = [];
  let lines: string[] = [];
  let inComment = false;
  let hasMovetext = false;
  for (const line of input.split(/\r?\n/)) {
    if (!inComment && hasMovetext && /^\s*\[\w+\s+"/.test(line)) {
      chunks.push(lines.join('\n').trim());
      lines = [];
      hasMovetext = false;
    }
    const isTag = !inComment && /^\s*\[\w+\s+"/.test(line);
    lines.push(line);
    if (isTag) continue;
    for (const ch of line) {
      if (inComment) { if (ch === '}') inComment = false; continue; }
      if (ch === ';') break;
      if (ch === '{') { inComment = true; continue; }
      if (!/\s/.test(ch)) hasMovetext = true;
    }
  }
  if (lines.join('\n').trim()) chunks.push(lines.join('\n').trim());
  return chunks;
}

function computeOutcome(result: string, userColor: PlayerColor): GameOutcome {
  if (result === '1-0') return userColor === 'w' ? 'win' : 'loss';
  if (result === '0-1') return userColor === 'b' ? 'win' : 'loss';
  return result === '1/2-1/2' ? 'draw' : 'unfinished';
}

/**
 * Chess.com writes Chess960 castling rights in Shredder-FEN (file letters like
 * "EBeb"). chess.js understands only KQkq. Convert the letters to kingside /
 * queenside rights relative to each king so the game can at least be indexed
 * and displayed. Drilling is still disabled for Chess960 because standard
 * chess.js cannot replay every non-standard castling move.
 */
export function normalizeChess960Fen(fen: string): string {
  const parts = fen.trim().split(/\s+/);
  if (parts.length < 4 || parts[2] === '-' || !/[A-Ha-h]/.test(parts[2])) return fen;

  const rows = parts[0].split('/');
  const expand = (rank: string) => rank.replace(/[1-8]/g, digit => '.'.repeat(Number(digit)));
  const whiteBack = expand(rows[7] ?? '');
  const blackBack = expand(rows[0] ?? '');
  const whiteKingFile = whiteBack.indexOf('K');
  const blackKingFile = blackBack.indexOf('k');
  const rights = new Set<string>();

  for (const ch of parts[2]) {
    if (ch === '-') continue;
    if ('KQkq'.includes(ch)) { rights.add(ch); continue; }
    const upper = ch.toUpperCase();
    const file = 'ABCDEFGH'.indexOf(upper);
    if (file < 0) continue;
    if (ch === upper) {
      if (whiteKingFile >= 0 && whiteBack[file] === 'R') {
        rights.add(file > whiteKingFile ? 'K' : 'Q');
      }
    } else if (blackKingFile >= 0 && blackBack[file] === 'r') {
      rights.add(file > blackKingFile ? 'k' : 'q');
    }
  }

  const normalized = ['K', 'Q', 'k', 'q'].filter((r) => rights.has(r)).join('') || '-';
  return [parts[0], parts[1], normalized, ...parts.slice(3)].join(' ');
}

function normalizePgnFenHeader(pgn: string): string {
  return pgn.replace(/^\[FEN\s+"([^"]+)"\]/im, (_line, fen: string) => {
    return `[FEN "${normalizeChess960Fen(fen)}"]`;
  });
}

function findZipPath(): string | null {
  const candidates = [
    path.join(REPO_ROOT, 'darrelnxt-2026-.zip'),
    path.resolve(process.cwd(), '../darrelnxt-2026-.zip'),
    path.resolve(process.cwd(), 'darrelnxt-2026-.zip'),
  ];
  for (const p of candidates) {
    if (fs.existsSync(p)) return p;
  }
  // Fallback: scan repo root for any *darrel*.zip
  if (fs.existsSync(REPO_ROOT)) {
    const found = fs
      .readdirSync(REPO_ROOT)
      .find((f) => f.toLowerCase().includes('darrel') && f.endsWith('.zip'));
    if (found) return path.join(REPO_ROOT, found);
  }
  return null;
}

export class PgnArchiveStore {
  constructor(private readonly customPath = CUSTOM_GAMES_PATH) {}
  private customLoadError: Error | null = null;
  private archiveGames = new Map<string, StoredGameRecord>();
  private customGames = new Map<string, StoredGameRecord>();
  private orderedIds: string[] = [];
  private loaded = false;
  revision = 0;

  ensureLoaded() {
    if (this.loaded) return;
    fs.mkdirSync(DATA_DIR, { recursive: true });
    this.loadZipArchive();
    this.loadCustomGamesFromDisk();
    this.rebuildOrder();
    this.loaded = true;
  }

  private loadZipArchive() {
    const zipPath = findZipPath();
    if (!zipPath) {
      console.warn('[pgnArchive] Could not locate darrelnxt-2026-.zip');
      return;
    }

    const zip = new AdmZip(zipPath);
    const entries = zip
      .getEntries()
      .filter((e) => e.entryName.endsWith('.pgn'))
      .sort((a, b) => a.entryName.localeCompare(b.entryName));

    for (const entry of entries) {
      const monthMatch = entry.entryName.match(/(\d{4}-\d{2})/);
      const fallbackMonth = monthMatch ? monthMatch[1] : '2026-01';
      const text = entry.getData().toString('utf8');
      const chunks = text.trim().split(/\r?\n\r?\n+(?=\[Event )/);

      for (const raw of chunks) {
        const trimmed = raw.trim();
        if (!trimmed) continue;
        const headers = parseHeaders(trimmed);
        const variant = headers.Variant || 'Standard';
        const isChess960 = variant.toLowerCase().includes('chess960');
        const isUnsupportedVariant =
          Boolean(headers.Variant) && variant !== 'Standard' && !isChess960;
        // Chess960 is indexed and visible in the library, but not engine-drillable.
        const pgn = isChess960 ? normalizePgnFenHeader(trimmed) : trimmed;
        const analyzable = !isChess960 && !isUnsupportedVariant;

        const link = headers.Link || '';
        const linkId = link.split('/').pop();
        const id =
          linkId && /^\d+$/.test(linkId)
            ? `cc-${linkId}`
            : `arc-${crypto.createHash('sha1').update(trimmed).digest('hex').slice(0, 12)}`;

        const white = headers.White || 'White';
        const black = headers.Black || 'Black';
        const userColor: PlayerColor =
          black.toLowerCase() === DEFAULT_USERNAME.toLowerCase() ? 'b' : 'w';
        const whiteElo = headers.WhiteElo && /^\d+$/.test(headers.WhiteElo) ? parseInt(headers.WhiteElo, 10) : null;
        const blackElo = headers.BlackElo && /^\d+$/.test(headers.BlackElo) ? parseInt(headers.BlackElo, 10) : null;

        const userName = userColor === 'w' ? white : black;
        const userElo = userColor === 'w' ? whiteElo : blackElo;
        const opponentName = userColor === 'w' ? black : white;
        const opponentElo = userColor === 'w' ? blackElo : whiteElo;

        const date = headers.UTCDate || headers.Date || `${fallbackMonth.replace('-', '.')}.01`;
        const month = date.slice(0, 7).replace('.', '-');
        const utcTime = headers.UTCTime || headers.StartTime || '00:00:00';
        const result = headers.Result || '*';
        const timeControl = headers.TimeControl || '600';
        const timeClass = classifyTimeControl(timeControl);
        const eco = headers.ECO || '';
        const baseOpeningName = cleanOpeningName(headers.ECOUrl, headers.Opening, eco);
        const openingName = isChess960 ? `Chess960 · ${baseOpeningName}` : baseOpeningName;
        const termination = headers.Termination || '';
        const moveCount = estimateMoveCount(trimmed);
        if (moveCount < 2) continue;

        this.archiveGames.set(id, {
          pgn,
          summary: {
            id,
            source: 'archive',
            month,
            date,
            utcTime,
            white,
            black,
            whiteElo,
            blackElo,
            userColor,
            userName,
            userElo,
            opponentName,
            opponentElo,
            result,
            userOutcome: computeOutcome(result, userColor),
            timeControl,
            timeClass,
            eco,
            openingName,
            termination,
            moveCount,
            link: link || undefined,
            variant,
            analyzable,
          },
        });
      }
    }
  }

  private loadCustomGamesFromDisk() {
    if (!fs.existsSync(this.customPath)) return;
    try {
      const raw = JSON.parse(fs.readFileSync(this.customPath, 'utf8')) as StoredGameRecord[];
      if (!Array.isArray(raw) || raw.some(item => {
        if (!item || typeof item.pgn !== 'string' || !item.summary) return true;
        const s = item.summary;
        const requiredText = [s.id, s.month, s.date, s.utcTime, s.white, s.black, s.userName,
          s.opponentName, s.result, s.timeControl, s.eco, s.openingName, s.termination];
        return requiredText.some(value => typeof value !== 'string') || s.source !== 'custom' ||
          !['w', 'b'].includes(s.userColor) || !['bullet', 'blitz', 'rapid', 'classical'].includes(s.timeClass) ||
          ![s.whiteElo, s.blackElo, s.userElo, s.opponentElo].every(value => value === null || (typeof value === 'number' && Number.isFinite(value))) ||
          !Number.isInteger(s.moveCount) || s.moveCount < 0;
      })) {
        throw new Error('Expected an array of valid saved game records');
      }
      for (const item of raw) {
        // Older imports could lose a result supplied in the movetext.
        if (!item.summary.result || item.summary.result === '*') {
          try { const game = new Chess(); game.loadPgn(item.pgn); item.summary.result = game.getHeaders().Result || '*'; } catch { /* retain stored metadata */ }
        }
        item.summary.userOutcome = computeOutcome(item.summary.result, item.summary.userColor);
        this.customGames.set(item.summary.id, item);
      }
    } catch (err) {
      this.customGames.clear();
      this.customLoadError = new Error('Cannot import games: the saved custom games file could not be read. Restore it or move it aside before trying again.', { cause: err });
      console.warn('[pgnArchive] Could not read saved games; imports are disabled:', err);
    }
  }

  private saveCustomGamesToDisk(games: Map<string, StoredGameRecord>) {
    if (this.customLoadError) throw this.customLoadError;
    writeFileAtomic(this.customPath, JSON.stringify(Array.from(games.values()), null, 2));
  }

  private rebuildOrder() {
    const all = [
      ...Array.from(this.customGames.values()),
      ...Array.from(this.archiveGames.values()),
    ];
    all.sort((a, b) => {
      // Custom pasted games appear right at the top when recently imported, otherwise sort by date+time desc
      if (a.summary.source !== b.summary.source) {
        return a.summary.source === 'custom' ? -1 : 1;
      }
      const keyA = `${a.summary.date} ${a.summary.utcTime}`;
      const keyB = `${b.summary.date} ${b.summary.utcTime}`;
      return keyB.localeCompare(keyA);
    });
    this.orderedIds = all.map((g) => g.summary.id);
  }

  getAllRecords(): StoredGameRecord[] {
    this.ensureLoaded();
    return this.orderedIds
      .map((id) => this.customGames.get(id) ?? this.archiveGames.get(id))
      .filter((x): x is StoredGameRecord => Boolean(x));
  }

  getArchiveRecordsOnly(): StoredGameRecord[] {
    this.ensureLoaded();
    return Array.from(this.archiveGames.values()).sort((a, b) => {
      const keyA = `${a.summary.date} ${a.summary.utcTime}`;
      const keyB = `${b.summary.date} ${b.summary.utcTime}`;
      return keyB.localeCompare(keyA);
    });
  }

  getGameById(id: string): StoredGameRecord | undefined {
    this.ensureLoaded();
    return this.customGames.get(id) ?? this.archiveGames.get(id);
  }

  getCounts() {
    this.ensureLoaded();
    const allArchive = Array.from(this.archiveGames.values());
    return {
      archive: allArchive.length,
      supported: allArchive.filter((r) => r.summary.analyzable !== false).length,
      chess960: allArchive.filter((r) => r.summary.variant?.toLowerCase().includes('chess960')).length,
      custom: this.customGames.size,
    };
  }

  /**
   * Imports one or more games from pasted PGN text (or bare SAN moves!).
   */
  importPgnText(
    rawInput: string,
    preferredSide: 'auto' | 'w' | 'b' = 'auto',
    playerHint?: string
  ): StoredGameRecord[] {
    this.ensureLoaded();
    const cleaned = rawInput.trim();
    if (!cleaned) {
      throw new Error('Please paste a PGN or move list first.');
    }

    const chunks = splitPgnGames(cleaned);

    const imported: StoredGameRecord[] = [];
    const now = new Date();
    const todayDot = now.toISOString().slice(0, 10).replace(/-/g, '.');
    const todayMonth = now.toISOString().slice(0, 7);
    const nowTime = now.toISOString().slice(11, 19);

    for (const chunk of chunks) {
      const text = chunk.trim();
      if (!text) continue;

      const chess = new Chess();
      try {
        chess.loadPgn(text);
      } catch (err) {
        throw new Error(
          `Invalid PGN moves: ${err instanceof Error ? err.message : 'Unable to parse PGN'}`
        );
      }

      const history = chess.history({ verbose: true });
      if (history.length < 2) {
        throw new Error('PGN must contain at least 1 full move (2 plies).');
      }

      const headers = parseHeaders(text);
      if (headers.Variant && headers.Variant !== 'Standard') {
        throw new Error('Only standard-chess PGNs can be imported for analysis.');
      }
      const white = headers.White || (preferredSide === 'b' ? 'Opponent' : DEFAULT_USERNAME);
      const black = headers.Black || (preferredSide === 'b' ? DEFAULT_USERNAME : 'Opponent');

      let userColor: PlayerColor = 'w';
      if (preferredSide === 'w' || preferredSide === 'b') {
        userColor = preferredSide;
      } else {
        const target = (playerHint?.trim() || DEFAULT_USERNAME).toLowerCase();
        const whiteName = white.toLowerCase();
        const blackName = black.toLowerCase();
        const whiteExact = whiteName === target;
        const blackExact = blackName === target;
        const whiteMatch = whiteName.includes(target);
        const blackMatch = blackName.includes(target);
        if (whiteExact !== blackExact) userColor = whiteExact ? 'w' : 'b';
        else if (!whiteExact && whiteMatch !== blackMatch) userColor = whiteMatch ? 'w' : 'b';
        else throw new Error('Could not uniquely identify your side. Choose White or Black for this import.');
      }

      const whiteElo =
        headers.WhiteElo && /^\d+$/.test(headers.WhiteElo) ? parseInt(headers.WhiteElo, 10) : null;
      const blackElo =
        headers.BlackElo && /^\d+$/.test(headers.BlackElo) ? parseInt(headers.BlackElo, 10) : null;

      const parsedResult = chess.getHeaders().Result || '*';
      if (headers.Result && parsedResult !== headers.Result) {
        throw new Error('PGN result header conflicts with the movetext result.');
      }
      if (!['1-0', '0-1', '1/2-1/2', '*'].includes(parsedResult)) {
        throw new Error('PGN result must be 1-0, 0-1, 1/2-1/2, or *.');
      }
      const result = parsedResult;
      const timeControl = headers.TimeControl || '600';
      const eco = headers.ECO || '';
      const openingName = cleanOpeningName(headers.ECOUrl, headers.Opening, eco);
      const date = headers.UTCDate || headers.Date || todayDot;
      const month = /^\d{4}[.-]\d{2}/.test(date) ? date.slice(0, 7).replace('.', '-') : todayMonth;
      const utcTime = headers.UTCTime || nowTime;

      const hash = crypto
        .createHash('sha1')
        .update(`${text}::${userColor}`)
        .digest('hex')
        .slice(0, 10);
      const id = `pgn-${hash}`;

      const canonicalPgn = text.includes('[White ') ? text : chess.pgn();

      const record: StoredGameRecord = {
        pgn: canonicalPgn,
        summary: {
          id,
          source: 'custom',
          month,
          date,
          utcTime,
          white,
          black,
          whiteElo,
          blackElo,
          userColor,
          userName: userColor === 'w' ? white : black,
          userElo: userColor === 'w' ? whiteElo : blackElo,
          opponentName: userColor === 'w' ? black : white,
          opponentElo: userColor === 'w' ? blackElo : whiteElo,
          result,
          userOutcome: computeOutcome(result, userColor),
          timeControl,
          timeClass: classifyTimeControl(timeControl),
          eco,
          openingName: openingName === 'Standard Chess' ? 'Pasted PGN Study' : openingName,
          termination: headers.Termination || 'Imported PGN',
          moveCount: Number(history[history.length - 1].before.split(' ')[5]) - Number(history[0].before.split(' ')[5]) + 1,
          link: headers.Link || undefined,
          variant: 'Standard',
          analyzable: true,
        },
      };

      imported.push(record);
    }

    // Commit only after all games validate; a bad later game must not leave
    // earlier games silently imported in memory.
    const nextGames = new Map(this.customGames);
    for (const record of imported) nextGames.set(record.summary.id, record);
    this.saveCustomGamesToDisk(nextGames);
    this.customGames = nextGames;
    this.rebuildOrder();
    this.revision++;
    return imported;
  }
}

export const pgnArchive = new PgnArchiveStore();
