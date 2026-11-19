import fs from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';
import type { MistakeMasteryRecord } from '../shared/types.js';

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const DATA_DIR = path.resolve(__dirname, '../data');
const PROGRESS_PATH = path.join(DATA_DIR, 'user-progress.json');

class ProgressStore {
  private records = new Map<string, MistakeMasteryRecord>();
  private loaded = false;
  revision = 0;

  private ensureLoaded() {
    if (this.loaded) return;
    fs.mkdirSync(DATA_DIR, { recursive: true });
    if (fs.existsSync(PROGRESS_PATH)) {
      try {
        const raw = JSON.parse(
          fs.readFileSync(PROGRESS_PATH, 'utf8')
        ) as Record<string, MistakeMasteryRecord>;
        for (const [k, v] of Object.entries(raw)) {
          this.records.set(k, v);
        }
      } catch (err) {
        console.warn('[progressStore] Could not parse user-progress.json:', err);
      }
    }
    this.loaded = true;
  }

  private persist() {
    const obj: Record<string, MistakeMasteryRecord> = {};
    for (const [k, v] of this.records.entries()) {
      obj[k] = v;
    }
    fs.writeFileSync(PROGRESS_PATH, JSON.stringify(obj, null, 2), 'utf8');
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
    const nextStreak = wasBlindFirstTry ? prev.streak + 1 : prev.streak;

    let nextStatus = prev.status;
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

    this.records.set(mistakeId, updated);
    this.revision++;
    this.persist();
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

    this.records.set(mistakeId, updated);
    this.revision++;
    this.persist();
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
    this.records.set(mistakeId, reset);
    this.revision++;
    this.persist();
    return reset;
  }
}

export const progressStore = new ProgressStore();
