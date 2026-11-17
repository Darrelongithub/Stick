/** Gemini selects an allowlisted intent only; all visible coaching text is
 * produced locally from Stockfish analysis and archive statistics. */

import { pgnArchive } from './pgnArchive.js';
import { buildLearningPlan, emptyAnalyzeAllStatus } from './learningPlan.js';
import type {
  AnalyzeAllStatus,
  CoachAnswerResponse,
  CoachAskRequest,
  CoachSource,
  CoachStatus,
  CoachStatusResponse,
} from '../shared/types.js';

const GEMINI_API_BASE = 'https://generativelanguage.googleapis.com/v1beta';
const DEFAULT_MODEL = 'gemini-flash-latest';
const FALLBACK_MODEL = 'gemini-flash-lite-latest';
const COACH_SUGGESTIONS = [
  'Why do I lose with Black?',
  'What should I study this week?',
  'Show my worst blunders',
  'Am I improving?',
] as const;

const SAFETY_CATEGORIES = [
  'HARM_CATEGORY_HARASSMENT',
  'HARM_CATEGORY_HATE_SPEECH',
  'HARM_CATEGORY_SEXUALLY_EXPLICIT',
  'HARM_CATEGORY_DANGEROUS_CONTENT',
] as const;

const SOLUTION_MARKERS = [
  'bestMoveSan',
  'bestMoveUci',
  'bestPvSan',
  'coachExplanation',
  'playedRefutationPvSan',
  'playedRefutation',
  'alternatives',
  'bestEvalUserCp',
  'bestEvalUserMate',
  'bestMove',
  'solution',
] as const;

interface EnvLike {
  [key: string]: string | undefined;
}

interface CoachSettings {
  key: string | null;
  model: string;
  fallbackModel: string;
  baseUrl: string;
  timeoutMs: number;
  dailyCallBudget: number;
  minIntervalMs: number;
}

interface QuotaState {
  day: string;
  calls: number;
  lastAt: number;
}

interface CoachKnowledge {
  text: string;
  summary: CoachAnswerResponse['knowledge'];
  plan: ReturnType<typeof buildLearningPlan>;
  record: {
    wins: number;
    losses: number;
    draws: number;
    whiteGames: number;
    whiteScorePct: number;
    blackGames: number;
    blackScorePct: number;
    timeClasses: Array<{ name: string; games: number; scorePct: number }>;
    topOpenings: Array<{ name: string; games: number; winRate: number }>;
  };
}

interface GeminiPayload {
  candidates?: Array<{
    content?: { parts?: Array<{ text?: string }> };
    finishReason?: string;
  }>;
  promptFeedback?: { blockReason?: string };
  error?: { message?: string; status?: string };
}

interface GeminiModelsPayload {
  models?: Array<{
    name?: string;
    supportedGenerationMethods?: string[];
  }>;
}

interface DiscoveryState {
  at: number;
  models: string[];
}

const KNOWLEDGE_TTL_MS = 30_000;
const MODEL_DISCOVERY_TTL_MS = 10 * 60_000;

interface ProviderResult {
  text: string;
  status: CoachStatus;
  model: string | null;
  error?: string;
}

export interface CoachServiceOptions {
  env?: EnvLike;
  fetchImpl?: typeof fetch;
}

function utcDay(): string {
  return new Date().toISOString().slice(0, 10);
}

function integerSetting(value: string | undefined, fallback: number, min: number, max: number): number {
  const parsed = Number(value);
  if (!Number.isFinite(parsed)) return fallback;
  return Math.max(min, Math.min(max, Math.round(parsed)));
}

function readSettings(env: EnvLike): CoachSettings {
  const rawKey = env.GEMINI_API_KEY || env.ADAPT_GEMINI_API_KEY || '';
  return {
    key: rawKey.trim() || null,
    model: (env.GEMINI_MODEL || env.ADAPT_GEMINI_MODEL_STANDARD || DEFAULT_MODEL).trim(),
    fallbackModel:
      (env.GEMINI_MODEL_FALLBACK || env.ADAPT_GEMINI_MODEL_FALLBACK || FALLBACK_MODEL).trim(),
    baseUrl: (env.GEMINI_BASE_URL || env.ADAPT_GEMINI_BASE_URL || GEMINI_API_BASE).replace(/\/+$/, ''),
    timeoutMs: integerSetting(env.GEMINI_TIMEOUT_MS, 20_000, 1_000, 60_000),
    dailyCallBudget: integerSetting(
      env.GEMINI_DAILY_CALL_BUDGET || env.ADAPT_GEMINI_DAILY_CALL_BUDGET,
      120,
      1,
      10_000,
    ),
    minIntervalMs: integerSetting(
      env.GEMINI_MIN_INTERVAL_MS || env.ADAPT_GEMINI_MIN_INTERVAL_MS,
      700,
      0,
      10_000,
    ),
  };
}

function assertSpoilerFree(value: unknown, label: string): void {
  const text = typeof value === 'string' ? value : JSON.stringify(value);
  const lowered = text.toLowerCase();
  const leaked = SOLUTION_MARKERS.find((marker) => lowered.includes(marker.toLowerCase()));
  if (leaked) throw new Error(`${label} contained forbidden solution marker: ${leaked}`);
  if (/best\s+moves?\b/i.test(text)) {
    throw new Error(`${label} named an engine answer`);
  }
}

function formatNumber(value: number): string {
  return value.toLocaleString('en-US');
}

function buildCoachKnowledge(analyzeAll?: AnalyzeAllStatus): CoachKnowledge {
  const plan = buildLearningPlan(analyzeAll ?? emptyAnalyzeAllStatus());
  const archive = pgnArchive.getArchiveRecordsOnly();

  let wins = 0;
  let losses = 0;
  let draws = 0;
  const color = {
    w: { games: 0, score: 0 },
    b: { games: 0, score: 0 },
  };
  const timeClass = new Map<string, { games: number; score: number }>();
  const openings = new Map<string, { games: number; wins: number }>();

  for (const record of archive) {
    const s = record.summary;
    if (s.userOutcome === 'win') wins += 1;
    else if (s.userOutcome === 'loss') losses += 1;
    else draws += 1;

    const score = s.userOutcome === 'win' ? 1 : s.userOutcome === 'draw' ? 0.5 : 0;
    color[s.userColor].games += 1;
    color[s.userColor].score += score;

    const tc = timeClass.get(s.timeClass) ?? { games: 0, score: 0 };
    tc.games += 1;
    tc.score += score;
    timeClass.set(s.timeClass, tc);

    const opening = openings.get(s.openingName) ?? { games: 0, wins: 0 };
    opening.games += 1;
    if (s.userOutcome === 'win') opening.wins += 1;
    openings.set(s.openingName, opening);
  }

  const pct = (score: number, games: number) => Math.round((score / Math.max(1, games)) * 100);
  const record = {
    wins,
    losses,
    draws,
    whiteGames: color.w.games,
    whiteScorePct: pct(color.w.score, color.w.games),
    blackGames: color.b.games,
    blackScorePct: pct(color.b.score, color.b.games),
    timeClasses: [...timeClass.entries()]
      .map(([name, value]) => ({ name, games: value.games, scorePct: pct(value.score, value.games) }))
      .sort((a, b) => b.games - a.games),
    topOpenings: [...openings.entries()]
      .map(([name, value]) => ({
        name,
        games: value.games,
        winRate: Math.round((value.wins / Math.max(1, value.games)) * 100),
      }))
      .sort((a, b) => b.games - a.games)
      .slice(0, 4),
  };

  const topMotifs = plan.counts.byMotif
    .slice(0, 4)
    .map((motif) => `${motif.label}: ${formatNumber(motif.count)} (${formatNumber(motif.mastered)} mastered)`)
    .join('; ');
  const topDrills = plan.recommendedDrills
    .slice(0, 5)
    .map(
      (drill) =>
        `#${drill.rank} move ${drill.moveNumber} ${drill.playedMoveSan} vs ${drill.opponent} (${drill.openingName}, ${drill.phaseLabel}, ${drill.motifLabel}, ${Math.round(drill.winProbLost * 100)}% win chance lost, ${drill.focus})`,
    )
    .join('\n');
  const timeClasses = record.timeClasses
    .map((tc) => `${tc.name}: ${formatNumber(tc.games)} games, ${tc.scorePct}% score`)
    .join('; ');
  const openingSummary = record.topOpenings
    .map((opening) => `${opening.name}: ${formatNumber(opening.games)} games, ${opening.winRate}% win rate`)
    .join('; ');

  const text = [
    `Knowledge engine: ${plan.engine}. Gemini is only the conversational coach layer.`,
    `Archive: ${formatNumber(plan.totalArchiveGames)} games, ${formatNumber(plan.totalSupportedGames)} drillable, ${formatNumber(plan.totalChess960Games)} Chess960 listed-only, ${formatNumber(plan.totalCustomGames)} custom.`,
    `Analyzed games: ${formatNumber(plan.analyzedGames)}. Stockfish-verified mistakes: ${formatNumber(plan.totalMistakes)}. Due blind drills: ${formatNumber(plan.dueCount)}. Mastered: ${formatNumber(plan.masteredCount)}. First-try recall: ${plan.firstTrySolveRate}%.`,
    `Severity: blunders ${formatNumber(plan.counts.bySeverity.blunder)}, mistakes ${formatNumber(plan.counts.bySeverity.mistake)}, inaccuracies ${formatNumber(plan.counts.bySeverity.inaccuracy)}.`,
    `Phases: opening ${formatNumber(plan.counts.byPhase.opening)}, middlegame ${formatNumber(plan.counts.byPhase.middlegame)}, endgame ${formatNumber(plan.counts.byPhase.endgame)}.`,
    `Mastery: unseen ${formatNumber(plan.counts.byMastery.unseen)}, needs review ${formatNumber(plan.counts.byMastery.needs_review)}, learning ${formatNumber(plan.counts.byMastery.learning)}, mastered ${formatNumber(plan.counts.byMastery.mastered)}.`,
    `Recurring motifs: ${topMotifs || 'none yet'}.`,
    `Record: wins ${formatNumber(record.wins)}, losses ${formatNumber(record.losses)}, draws ${formatNumber(record.draws)}. White score ${record.whiteScorePct}% over ${formatNumber(record.whiteGames)} games; Black score ${record.blackScorePct}% over ${formatNumber(record.blackGames)} games.`,
    `Time classes: ${timeClasses || 'none yet'}.`,
    `Most-played openings: ${openingSummary || 'none yet'}.`,
    `Highest-priority spoiler-free drills (played moves only):\n${topDrills || 'none yet'}`,
    'Only aggregate counts and the player’s own moves are present in this knowledge block.',
  ].join('\n');

  assertSpoilerFree(text, 'Coach knowledge digest');

  return {
    text,
    plan,
    record,
    summary: {
      engine: plan.engine,
      archiveGames: plan.totalArchiveGames,
      analyzedGames: plan.analyzedGames,
      totalMistakes: plan.totalMistakes,
      dueCount: plan.dueCount,
      masteredCount: plan.masteredCount,
      firstTrySolveRate: plan.firstTrySolveRate,
    },
  };
}

function localCoachAnswer(question: string, knowledge: CoachKnowledge): string {
  const q = question.toLowerCase();
  const plan = knowledge.plan;
  const record = knowledge.record;
  const topMotif = plan.counts.byMotif[0];
  const firstDrill = plan.recommendedDrills[0];
  const due = formatNumber(plan.dueCount);
  const fmt = formatNumber;

  if (/black|white|colou?r|lose|loss|side/.test(q)) {
    return `With Black you score ${record.blackScorePct}% across ${fmt(record.blackGames)} games; with White it is ${record.whiteScorePct}% across ${fmt(record.whiteGames)}. Your most-played opening is ${record.topOpenings[0]?.name ?? 'not established yet'}. Stockfish also flags ${fmt(plan.counts.byPhase.middlegame)} middlegame mistakes, which are available as blind drills.`;
  }
  if (/study|week|train|due|practice|session|plan/.test(q)) {
    return `Three things this week: 1) ${topMotif?.label ?? 'tactical recall'} drills (${fmt(topMotif?.count ?? 0)} Stockfish-verified cases), 2) the ${due} due blind positions, and 3) ${fmt(plan.counts.byPhase.endgame)} endgame mistakes. ${firstDrill ? `Start with move ${firstDrill.moveNumber} ${firstDrill.playedMoveSan} vs ${firstDrill.opponent}: ${firstDrill.focus}.` : 'Start with the first due drill.'}`;
  }
  if (/blunder|worst|mistake|hang|drop|tactic/.test(q)) {
    return `Stockfish found ${fmt(plan.counts.bySeverity.blunder)} blunders and ${fmt(plan.totalMistakes)} verified mistakes in total. ${topMotif ? `The most repeated pattern is ${topMotif.label} (${fmt(topMotif.count)} times).` : ''} ${firstDrill ? `Your costliest queued drill is move ${firstDrill.moveNumber} ${firstDrill.playedMoveSan} vs ${firstDrill.opponent}, where the game move lost ${Math.round(firstDrill.winProbLost * 100)}% win chance.` : ''} I will keep the answer hidden until you try the position blind.`;
  }
  if (/improv|rating|progress|better|master|recall/.test(q)) {
    return `Current recall: ${fmt(plan.masteredCount)} positions are mastered and first-try recall is ${plan.firstTrySolveRate}%. ${fmt(plan.counts.byMastery.needs_review)} positions need review and ${fmt(plan.counts.byMastery.learning)} are in learning. Your record is ${fmt(record.wins)} wins, ${fmt(record.losses)} losses, ${fmt(record.draws)} draws. Keep the loop blind: attempt, fail if needed, then reveal and recall cleanly twice.`;
  }
  if (/opening|repertoire|theory/.test(q)) {
    const opening = record.topOpenings[0];
    return opening
      ? `${opening.name} is your most-played line: ${fmt(opening.games)} games with a ${opening.winRate}% win rate. Stockfish sees ${fmt(plan.counts.byPhase.opening)} opening-phase mistakes, and those positions are available to review.`
      : `Opening data is still loading from the local archive. Stockfish has ${fmt(plan.counts.byPhase.opening)} opening-phase mistakes ready to turn into blind drills.`;
  }
  return `I have read ${fmt(plan.analyzedGames)} Stockfish-analyzed games and ${fmt(plan.totalMistakes)} verified mistakes. ${topMotif ? `${topMotif.label} is the loudest recurring pattern (${fmt(topMotif.count)} cases).` : ''} There are ${due} blind drills due. Ask me about your colours, this week's study, your worst blunders, openings, or whether your recall is improving.`;
}

// Gemini can only choose an intent. Its prose is never displayed: the server
// maps an exact allowlisted token to a fixed, locally generated response.
const INTENTS: Record<string, string> = Object.freeze({
  COLORS: 'black', STUDY: 'study', MISTAKES: 'blunder',
  PROGRESS: 'progress', OPENINGS: 'opening', OTHER: '',
});

function extractText(payload: GeminiPayload): string {
  const candidate = payload.candidates?.[0];
  const parts = candidate?.content?.parts ?? [];
  return parts
    .map((part) => (typeof part.text === 'string' ? part.text : ''))
    .join('')
    .trim();
}

function safetySettings() {
  return SAFETY_CATEGORIES.map((category) => ({
    category,
    threshold: 'BLOCK_MEDIUM_AND_ABOVE',
  }));
}

async function requestModel(
  settings: CoachSettings,
  model: string,
  body: unknown,
  fetchImpl: typeof fetch,
): Promise<ProviderResult & { httpStatus: number }> {
  const url = `${settings.baseUrl}/models/${encodeURIComponent(model)}:generateContent`;
  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), settings.timeoutMs);

  try {
    const response = await fetchImpl(url, {
      method: 'POST',
      headers: {
        'content-type': 'application/json',
        'x-goog-api-key': settings.key ?? '',
      },
      body: JSON.stringify(body),
      signal: controller.signal,
    });

    if (!response.ok) {
      return {
        text: '',
        status: response.status === 429 ? 'quota' : 'error',
        model,
        httpStatus: response.status,
        error: `Gemini answered HTTP ${response.status}`,
      };
    }

    const payload = (await response.json()) as GeminiPayload;
    if (payload.promptFeedback?.blockReason) {
      return {
        text: '',
        status: 'blocked',
        model,
        httpStatus: response.status,
        error: `Gemini blocked the prompt: ${payload.promptFeedback.blockReason}`,
      };
    }
    if (payload.error?.message) {
      return {
        text: '',
        status: 'error',
        model,
        httpStatus: response.status,
        error: 'Gemini returned an API error',
      };
    }
    const finishReason = payload.candidates?.[0]?.finishReason;
    if (finishReason && /SAFETY|RECITATION|BLOCKLIST|PROHIBITED/i.test(finishReason)) {
      return {
        text: '',
        status: 'blocked',
        model,
        httpStatus: response.status,
        error: `Gemini stopped with ${finishReason}`,
      };
    }
    const text = extractText(payload);
    if (!text) {
      return {
        text: '',
        status: 'empty',
        model,
        httpStatus: response.status,
        error: 'Gemini returned no usable text',
      };
    }
    return { text, status: 'ok', model, httpStatus: response.status };
  } catch (error) {
    const aborted = error instanceof Error && error.name === 'AbortError';
    return {
      text: '',
      status: 'error',
      model,
      httpStatus: 0,
      error: aborted ? 'Gemini request timed out' : 'Gemini request failed',
    };
  } finally {
    clearTimeout(timer);
  }
}

/**
 * Ask the provider which models actually support generateContent for this key.
 * Rolling aliases are convenient but Google retires model IDs without notice;
 * a cached discovery call keeps the coach working across those changes. The
 * list contains model names only, never the key or any response content.
 */
async function discoverModels(
  settings: CoachSettings,
  fetchImpl: typeof fetch,
  cache: { value: DiscoveryState | null },
): Promise<string[]> {
  const now = Date.now();
  if (cache.value && now - cache.value.at < MODEL_DISCOVERY_TTL_MS) return cache.value.models;
  if (!settings.key || typeof fetchImpl !== 'function') return [];

  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), Math.min(settings.timeoutMs, 5_000));
  try {
    const response = await fetchImpl(`${settings.baseUrl}/models`, {
      headers: { 'x-goog-api-key': settings.key },
      signal: controller.signal,
    });
    if (!response.ok) return [];
    const payload = (await response.json()) as GeminiModelsPayload;
    const names = (payload.models ?? []).flatMap((entry) => {
      const name = (entry.name ?? '').replace(/^models\//, '').trim();
      if (!name || !entry.supportedGenerationMethods?.includes('generateContent')) return [];
      if (/preview|tts|image|embedding|vision|audio|robotics|computer|deep-research/i.test(name)) return [];
      return [name];
    });
    const flash = names.filter((name) => /flash/i.test(name) && !/lite/i.test(name));
    const lite = names.filter((name) => /flash/i.test(name) && /lite/i.test(name));
    const rest = names.filter((name) => !flash.includes(name) && !lite.includes(name));
    const models = [...new Set([...flash, ...lite, ...rest])].slice(0, 8);
    cache.value = { at: now, models };
    return models;
  } catch {
    return [];
  } finally {
    clearTimeout(timer);
  }
}

async function callGemini(
  settings: CoachSettings,
  question: string,
  history: CoachAskRequest['history'],
  _knowledge: CoachKnowledge,
  fetchImpl: typeof fetch,
  discoveryCache: { value: DiscoveryState | null },
): Promise<ProviderResult> {
  if (!settings.key) {
    return { text: '', status: 'disabled', model: null, error: 'No GEMINI_API_KEY configured' };
  }
  if (typeof fetchImpl !== 'function') {
    return { text: '', status: 'error', model: null, error: 'fetch is unavailable' };
  }

  // No board positions, answers, or free-form coaching are sent or accepted.
  // Include only user questions as context: previous model prose is untrusted.
  const context = (history ?? []).filter((entry) => entry.role === 'user')
    .slice(-3).map((entry) => entry.text.slice(0, 800));
  const body = {
    systemInstruction: { parts: [{ text: 'Classify the latest question. Return exactly one token: COLORS, STUDY, MISTAKES, PROGRESS, OPENINGS, or OTHER. No other text. Never answer the question.' }] },
    contents: [{ role: 'user', parts: [{ text: JSON.stringify({ previousQuestions: context, question }) }] }],
    generationConfig: { temperature: 0, maxOutputTokens: 32 },
    safetySettings: safetySettings(),
  };

  // Prefer models the key can actually use today, then the configured aliases.
  const discovered = await discoverModels(settings, fetchImpl, discoveryCache);
  const chain = [
    ...new Set([
      ...discovered,
      settings.model,
      settings.fallbackModel,
      DEFAULT_MODEL,
      FALLBACK_MODEL,
    ]),
  ]
    .filter(Boolean)
    .slice(0, 6);
  let last: (ProviderResult & { httpStatus: number }) | null = null;

  for (const model of chain) {
    const result = await requestModel(settings, model, body, fetchImpl);
    last = result;
    if (result.status === 'ok') return result;
    // Retired/unknown model IDs are deployment facts, not learner failures.
    // Google sometimes reports them as 400 rather than 404, so retry both.
    const retired =
      result.httpStatus === 404 ||
      (result.httpStatus === 400 && /model|not found|unsupported|unknown/i.test(result.error ?? ''));
    if (!retired) return result;
  }

  return last ?? { text: '', status: 'error', model: null, error: 'No Gemini model answered' };
}

function makeResponse(
  answer: string,
  source: CoachSource,
  status: CoachStatus,
  model: string | null,
  startedAt: number,
  configured: boolean,
  knowledge: CoachKnowledge,
  error?: string,
): CoachAnswerResponse {
  const response: CoachAnswerResponse = {
    answer,
    source,
    status,
    model,
    latencyMs: Math.max(0, Date.now() - startedAt),
    configured,
    generatedAt: new Date().toISOString(),
    knowledge: knowledge.summary,
    suggestions: [...COACH_SUGGESTIONS],
    ...(error ? { error } : {}),
  };
  assertSpoilerFree(response, 'Coach response');
  return response;
}

export function createCoachService(options: CoachServiceOptions = {}) {
  const env = options.env ?? (process.env as EnvLike);
  const fetchImpl = options.fetchImpl ?? globalThis.fetch;
  const quota: QuotaState = { day: utcDay(), calls: 0, lastAt: 0 };
  const answerCache = new Map<string, { response: CoachAnswerResponse; at: number }>();
  const discoveryCache: { value: DiscoveryState | null } = { value: null };
  let lastProviderError: string | null = null;
  let previousKey: string | null | undefined;
  let knowledgeCache: { key: string; value: CoachKnowledge; at: number } | null = null;

  function rollQuota(): void {
    const today = utcDay();
    if (today !== quota.day) {
      quota.day = today;
      quota.calls = 0;
      quota.lastAt = 0;
      answerCache.clear();
    }
  }

  /** Reuse the aggregate Stockfish digest for 30s; it is the expensive part of ask(). */
  function getKnowledge(analyzeAll?: AnalyzeAllStatus): CoachKnowledge {
    const key = `${analyzeAll?.running ?? false}|${analyzeAll?.processed ?? 0}|${analyzeAll?.percent ?? 0}`;
    const now = Date.now();
    if (knowledgeCache && knowledgeCache.key === key && now - knowledgeCache.at < KNOWLEDGE_TTL_MS) {
      return knowledgeCache.value;
    }
    const value = buildCoachKnowledge(analyzeAll);
    knowledgeCache = { key, value, at: now };
    return value;
  }

  function status(): CoachStatusResponse {
    rollQuota();
    const settings = readSettings(env);
    const configured = Boolean(settings.key);
    return {
      provider: 'gemini',
      configured,
      model: settings.model,
      baseUrl: settings.baseUrl,
      dailyCallBudget: settings.dailyCallBudget,
      callsToday: quota.calls,
      minIntervalMs: settings.minIntervalMs,
      localFallback: true,
      knowledgeEngine: 'Stockfish 18 Lite NNUE (local)',
      spoilerSafe: true,
      reason: configured
        ? lastProviderError
          ? `Server key found; last provider attempt: ${lastProviderError}`
          : 'Server key found; Gemini will be tried on the next question.'
        : 'No server-side Gemini key is configured.',
      hint: configured
        ? undefined
        : 'Add GEMINI_API_KEY to chess-improver/.env and refresh; the deterministic local coach stays active.',
      lastProviderError,
    };
  }

  async function ask(
    request: CoachAskRequest,
    analyzeAll?: AnalyzeAllStatus,
  ): Promise<CoachAnswerResponse> {
    const startedAt = Date.now();
    const question = String(request?.question ?? '').trim().slice(0, 800);
    if (!question) {
      throw new Error('A question is required');
    }

    rollQuota();
    const settings = readSettings(env);
    // Changing a key must never reuse an answer or provider error from the old key.
    if (previousKey !== settings.key) {
      answerCache.clear();
      discoveryCache.value = null;
      lastProviderError = null;
      previousKey = settings.key;
    }
    const knowledge = getKnowledge(analyzeAll);
    const cacheKey = [
      question.toLowerCase(),
      knowledge.summary.totalMistakes,
      knowledge.summary.dueCount,
      knowledge.summary.masteredCount,
      settings.model,
      Boolean(settings.key),
    ].join('|');
    // A follow-up depends on its conversation, not just its text.
    const cacheable = !request.history?.length;
    const cached = cacheable ? answerCache.get(cacheKey) : undefined;
    if (cached && Date.now() - cached.at < 5 * 60 * 1000) {
      return { ...cached.response, latencyMs: 0, generatedAt: new Date().toISOString() };
    }

    if (!settings.key) {
      const response = makeResponse(
        localCoachAnswer(question, knowledge),
        'local',
        'disabled',
        null,
        startedAt,
        false,
        knowledge,
        'No server-side Gemini key configured. Add GEMINI_API_KEY to chess-improver/.env and refresh; the deterministic local coach is active.',
      );
      if (cacheable) answerCache.set(cacheKey, { response, at: Date.now() });
      return response;
    }

    if (quota.calls >= settings.dailyCallBudget) {
      return makeResponse(
        localCoachAnswer(question, knowledge),
        'local',
        'quota',
        null,
        startedAt,
        true,
        knowledge,
        `Daily Gemini budget (${settings.dailyCallBudget}) reached.`,
      );
    }
    const waitMs = Math.max(0, settings.minIntervalMs - (Date.now() - quota.lastAt));
    if (waitMs > 3_000) {
      return makeResponse(
        localCoachAnswer(question, knowledge),
        'local',
        'throttled',
        null,
        startedAt,
        true,
        knowledge,
        'Local pacing backlog; used the local coach instead.',
      );
    }
    if (waitMs > 0) await new Promise<void>((resolve) => setTimeout(resolve, waitMs));
    quota.calls += 1;
    quota.lastAt = Date.now();

    const result = await callGemini(settings, question, request.history, knowledge, fetchImpl, discoveryCache);
    if (result.status !== 'ok' || !result.text) {
      lastProviderError = result.error ?? 'Gemini was unavailable; used the local coach.';
      return makeResponse(
        localCoachAnswer(question, knowledge),
        'local',
        result.status,
        result.model,
        startedAt,
        true,
        knowledge,
        lastProviderError,
      );
    }

    // Exact allowlist is the hard gate: arbitrary model text, including plausible
    // but incorrect advice or disguised moves, is never sent to the browser.
    if (!Object.hasOwn(INTENTS, result.text)) {
      lastProviderError = 'Gemini returned an unrecognized intent; used the local coach.';
      return makeResponse(localCoachAnswer(question, knowledge), 'local', 'spoiler_rejected', result.model, startedAt, true, knowledge, lastProviderError);
    }
    lastProviderError = null;
    const response = makeResponse(
      localCoachAnswer(INTENTS[result.text], knowledge),
      'gemini', 'ok', result.model, startedAt, true, knowledge,
    );
    if (cacheable) answerCache.set(cacheKey, { response, at: Date.now() });
    return response;
  }

  return { status, ask };
}

export const coachService = createCoachService();
