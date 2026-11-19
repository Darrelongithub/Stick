import fs from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';
import { writeFileAtomic } from './atomicFile.js';
import type { MistakeMasteryRecord } from '../shared/types.js';

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const DATA_DIR = process.env.CHESS_DATA_DIR ? path.resolve(process.env.CHESS_DATA_DIR) : path.resolve(__dirname, '../data');
const PROGRESS_PATH = path.join(DATA_DIR, 'user-progress.json');

export class ProgressStore {
  constructor(private readonly filePath = PROGRESS_PATH) {}
  private loadError: Error | null = null;
  private records = new Map<string, MistakeMasteryRecord>();
  private loaded = false;
  revision = 0;

  private ensureLoaded() {
    if (this.loaded) return;
    fs.mkdirSync(path.dirname(this.filePath), { recursive: true });
    if (fs.existsSync(this.filePath)) {
      try {
        const raw = JSON.parse(
          fs.readFileSync(this.filePath, 'utf8')
        ) as Record<string, MistakeMasteryRecord>;
        if (!raw || typeof raw !== 'object' || Array.isArray(raw) || Object.entries(raw).some(([id, v]) =>
          !v || typeof v !== 'object' || v.mistakeId !== id ||
          !['unseen', 'needs_review', 'learning', 'mastered'].includes(v.status) ||
          ![v.totalAttempts, v.failCount, v.streak].every(n => Number.isInteger(n) && n >= 0) ||
          (v.solvedFirstTry !== null && typeof v.solvedFirstTry !== 'boolean') ||
          (v.lastAttemptAt !== null && typeof v.lastAttemptAt !== 'string'))) {
          throw new Error('Expected valid progress records');
        }
        for (const [k, v] of Object.entries(raw)) {
          this.records.set(k, v);
        }
      } catch (err) {
        this.loadError = new Error('Cannot update progress: the saved progress file could not be read. Restore it or move it aside before trying again.', { cause: err });
        console.warn('[progressStore] Could not read saved progress; writes are disabled:', err);
      }
    }
    this.loaded = true;
  }

  private persist(nextRecords: Map<string, MistakeMasteryRecord>) {
    if (this.loadError) throw this.loadError;
    const obj: Record<string, MistakeMasteryRecord> = {};
    for (const [k, v] of nextRecords.entries()) {
      obj[k] = v;
    }
    writeFileAtomic(this.filePath, JSON.stringify(obj, null, 2));
  }

  getRecord(mistakeId: string): MistakeMasteryRecord {
    this.ensureLoaded();
    return (
      this.records.get(mistakeId) ?? {
        mistakeId,
        status: 'unseen',
        totalAttempts: 0,
        failCount: 0,
        streak: 0,
        solvedFirstTry: null,
        lastAttemptAt: null,
      }
    );
  }

  recordSuccess(mistakeId: string, wasBlindFirstTry: boolean): MistakeMasteryRecord {
    this.ensureLoaded();
    const prev = this.getRecord(mistakeId);
    const now = new Date().toISOString();

    const solvedFirstTry =
      prev.solvedFirstTry !== null ? prev.solvedFirstTry : wasBlindFirstTry;
    const nextStreak = wasBlindFirstTry ? prev.streak + 1 : 0;

    let nextStatus = prev.status;
    // A solve after a wrong guess is no longer unseen, but it is not a clean
    // first-try recall either; require a clean revisit before mastery.
    if (!wasBlindFirstTry) nextStatus = 'learning';
    if (prev.failCount === 0 && wasBlindFirstTry) {
      nextStatus = 'mastered';
    } else if (wasBlindFirstTry) {
      // Previously failed: 1 clean blind solve -> 'learning', 2 clean blind solves -> 'mastered'
      nextStatus = nextStreak >= 2 ? 'mastered' : 'learning';
    }

    const updated: MistakeMasteryRecord = {
      mistakeId,
      status: nextStatus,
      totalAttempts: prev.totalAttempts + 1,
      failCount: prev.failCount,
      streak: nextStreak,
      solvedFirstTry,
      lastAttemptAt: now,
    };

    const nextRecords = new Map(this.records).set(mistakeId, updated);
    this.persist(nextRecords);
    this.records = nextRecords;
    this.revision++;
    return updated;
  }

  recordFailure(mistakeId: string): MistakeMasteryRecord {
    this.ensureLoaded();
    const prev = this.getRecord(mistakeId);
    const now = new Date().toISOString();

    const updated: MistakeMasteryRecord = {
      mistakeId,
      status: 'needs_review',
      totalAttempts: prev.totalAttempts + 1,
      failCount: prev.failCount + 1,
      streak: 0,
      solvedFirstTry: prev.solvedFirstTry !== null ? prev.solvedFirstTry : false,
      lastAttemptAt: now,
    };

    const nextRecords = new Map(this.records).set(mistakeId, updated);
    this.persist(nextRecords);
    this.records = nextRecords;
    this.revision++;
    return updated;
  }

  resetMistake(mistakeId: string): MistakeMasteryRecord {
    this.ensureLoaded();
    const reset: MistakeMasteryRecord = {
      mistakeId,
      status: 'unseen',
      totalAttempts: 0,
      failCount: 0,
      streak: 0,
      solvedFirstTry: null,
      lastAttemptAt: null,
    };
    const nextRecords = new Map(this.records).set(mistakeId, reset);
    this.persist(nextRecords);
    this.records = nextRecords;
    this.revision++;
    return reset;
  }
}

export const progressStore = new ProgressStore();
