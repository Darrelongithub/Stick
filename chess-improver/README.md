# Coach · darrelnxt Chess Improver

A Stockfish 18 NNUE-powered study app built around `darrelnxt-2026-.zip` in the repository root. It turns real mistakes from your Chess.com games into blind, spoiler-free drills and keeps every missed position in a cross-game spaced-repetition queue. The whole interface follows the dark violet/glass **Coach** visual language from `origin/main:chess.html`, with the home page closest to that reference.

## Start it with one word

From the repository root:

```bash
cd Stick
chess
```

That starts the unified Express + Vite server on `0.0.0.0:5173` in the background and prints the URL. The `chess` command has been installed on this machine’s PATH; the launcher also lives in the repo at `./chess` and `chess-improver/bin/chess`, so it travels with the branch.

Other commands:

```bash
chess status          # server, archive and batch-analysis status
chess analyze-all     # scan every supported game with local Stockfish (optional; can take time)
chess plan            # print the generated data/WHAT_TO_LEARN.md
chess logs [-f]       # server logs
chess stop            # stop the server
chess restart         # stop + start
chess install         # reinstall the `chess` command onto PATH
chess help            # full command list
```

If you clone the repo elsewhere, run `./chess install` once to put the command on PATH. `chess` uses only relative paths from its own script location — no hardcoded absolute paths.

Manual equivalents:

```bash
cd chess-improver
npm install
npm run dev           # unified server on 0.0.0.0:5173
npm run analyze:all   # full archive scan (uses the running server if present)
npm test              # REST/SSE, PGN import, Stockfish, Gemini coach and anti-spoiler tests
npm run build         # production Vite build into dist/
npm start             # production server (requires npm run build first)
npm run seed          # regenerate data/preanalyzed-games.json
```

## Stockfish is the chess source; Gemini is only the coach

Stockfish 18 Lite NNUE evaluates positions locally and produces the learning plan. Gemini is restricted to selecting one of six exact topic tokens; its free-form text is never shown. The server generates answers from fixed templates using local Stockfish analysis and archive statistics. Unexpected output is rejected and falls back locally. This hard gate prevents Gemini from supplying chess moves or invented coaching, though Stockfish analysis itself is not infallible. Unsupported questions receive a general summary rather than an invented answer. The provider sees the question and recent user questions, not board positions or engine answers. Blind-drill solutions remain hidden until the allowed reveal.

The integration follows the Gemini patterns already used in the owner’s other repos (Adapt, The-game, Elaria, Project-AA): REST `v1beta:generateContent` with `x-goog-api-key`, rolling model aliases, a daily budget, timeout, model fallback, and a deterministic local fallback. No SDK or key is shipped to the React bundle.

### Optional server-side key

No key is required. Without one, the same spoiler-free knowledge is answered by `server/geminiCoach.ts`’s deterministic local coach, so the app still works offline.

To enable Gemini, copy `.env.example` to `.env` inside `chess-improver/` (or set real environment variables) and restart `chess`:

```dotenv
GEMINI_API_KEY=your-google-ai-studio-key
# ADAPT_GEMINI_API_KEY=alternative-name
GEMINI_MODEL=gemini-flash-latest
GEMINI_MODEL_FALLBACK=gemini-flash-lite-latest
GEMINI_TIMEOUT_MS=20000
GEMINI_DAILY_CALL_BUDGET=120
GEMINI_MIN_INTERVAL_MS=700
```

`GEMINI_API_KEY` wins; `ADAPT_GEMINI_API_KEY` is the fallback for consistency with the Adapt repo. `server/env.ts` loads `.env` server-side only, without adding a dependency, and never copies the value into Vite or any API response. `.env` is gitignored. There is no in-app key setting and no browser-side override. `GET /api/coach/status` reports whether the coach is configured and how many calls remain; `POST /api/coach/ask` accepts a question plus short chat history and returns a typed answer with source, status, knowledge summary, and suggestions.

## Play against your mirror

Choose **Mirror** in the navigation. The mirror indexes the included archive and imported games, and uses the user's selected side in each game. In an exact matching position it chooses the most frequently recorded move; in an unseen position it falls back to local Stockfish. It is an approximation, not a learned personality or a guarantee of your future moves. To protect blind drills, mirror play stops when it reaches an analyzed challenge position, even if that challenge was previously solved. The profile reports how many games were used and skipped. Chess960 games remain listed but are excluded from this standard-chess opponent. New games must be imported manually; the app does not sync Chess.com automatically. The bundled ZIP is a snapshot, not a guarantee that newer games are included.

## The archive and the learning contract

- The ZIP contains **1,128 games**. All of them are indexed and visible in **Library & Insights**.
- **1,108 standard-rules games** are engine-drillable. This includes 14 “Odds Chess” games with a custom starting FEN; `chess.js` replays those correctly.
- **20 Chess960 games** are listed but not drilled: their Shredder-FEN castling rights are normalized for display, but the bundled standard `chess.js` cannot replay every non-standard castling move. They are clearly marked and their Train button is disabled.
- The original workspace completed a full scan: **1,108 analyzed games, 5,705 verified mistakes, 0 failed**. Its analysis cache is gitignored and is not included in a fresh clone. A fresh clone starts with the bundled 14-game seed; run `./chess analyze-all` if you want to rebuild the full cache, or transfer your existing `data/analysis-cache.json` securely.
- Public endpoints send only `MistakeChallengePublic`: the position, your actual move, severity, motif, and evaluations. `bestMove`, PVs, alternatives, refutations, and explanations stay server-side.
- Replaying the original game move does **not** consume a try and does **not** reveal anything.
- With the default `1 try`, the first wrong candidate fails the drill and **then** the Stockfish best move is revealed.
- With `2 tries`, the first failure returns a refutation of your candidate while still hiding the answer; the second failure reveals it.
- Solving on the first blind attempt marks a position mastered. Previously failed positions require two clean blind recalls (`needs_review → learning → mastered`).
- Missed positions are re-drilled blind at the end of a game and remain in the Mistake Vault until mastered.

## Right-now full archive analysis

`chess analyze-all` (or `npm run analyze:all`) triggers a local batch job over **every supported archive and custom game**. It uses the running server’s Stockfish pool when available, streams progress to `/api/admin/analyze-all/status`, and writes:

- `data/analysis-cache.json` — compact full Stockfish analysis cache (gitignored, tens of MB).
- `data/learning-plan.json` — machine-readable, spoiler-free curriculum (gitignored).
- `data/WHAT_TO_LEARN.md` — gitignored human-readable “what am I supposed to learn” summary with the highest-priority drills.
- `data/analyze-all-progress.json` — resumable progress snapshot (gitignored).

The **Home** view polls the learning plan while the scan runs, shows a live progress/ETA bar, and immediately lists the due drills. The Mistake Vault and Library update as soon as the scan finishes. No solution fields are ever written into the plan or markdown.

## Pasting a new PGN

Use **+ Import games** in the pill nav. You can paste a Chess.com-style PGN, upload a `.pgn`/`.txt` file, or try one of the built-in samples. Choose Auto / White / Black; Auto detects `darrelnxt` from the headers when present. Multiple `[Event "..."]` blocks in one paste are imported as separate custom games. The app immediately opens the first imported game and streams a live Stockfish analysis.

## Main views

- **Home** — the `chess.html`-style landing: ambient violet orbs, sticky pill nav, sync strip, Gemini-intent/local-facts coach card with ask input and chips, a task-first training summary, a six-column bento dashboard (rating journey, today’s training, recurring mistakes, openings, latest game, insights), accent swatches, and the full ranked curriculum below.
- **Coach** — interactive board with click and drag moves, promotion picker, Violet / Midnight / Linen board palettes, evaluation bar, tactical arrows, clocks/captured material, live SSE analysis progress, a theme-only hint, game-move preview, PV/refutation stepping, practice-the-best-move, a PGN move sheet, and an end-of-game blind re-drill.
- **Mistake Vault** — cross-game spaced-repetition queue with mastery, severity, motif, and phase filters. Every card is a blind drill; solution fields are never present before failure.
- **Library & Insights** — searchable/filterable 1,128-game archive, custom PGN library, rating trajectory, opening performance, motif weaknesses, phase split, and time-control stats.

## Visual system

The interface is a dark, editorial **Coach** theme: near-black violet `#06050A`, off-white `#F3F1F8`, muted `#8F8BA0`, violet `#8B7CFF` / `#CFC7FF`, warm mistake `#FF6B57`, and cool `#4CC9F0`. Glass cards use blurred gradients, hairline white borders, inset highlight edges, soft ambient orbs, a cursor spotlight, and SVG grain. Fraunces display type, Inter body type, JetBrains Mono numerals, and Plus Jakarta Sans accents are bundled locally with Fontsource.

Design tokens live in `src/index.css` as CSS variables, with `.glass-nav`, `.coach-card`, `.ask`, `.home-focus`, `.card`, `.premium-card`, `.premium-tile`, and `.swatches` utilities. The four accent swatches update `--a` / `--a2` across both the new CSS and the legacy Tailwind utilities. The three board palettes are **Violet** (default), **Midnight**, and **Linen**; pieces are ivory and near-black with violet detail. `prefers-reduced-motion: reduce` removes animation and transition delays.

## Where to click

A first-run guided tour opens on every fresh browser profile and can be replayed with the **?** button, the **How to use · 60 sec** button in the curriculum, or **60-sec tour** on Home. The numbered navigation follows the learning loop: **1 Home → 2 Coach → 3 Mistake Vault → 4 Library & Insights**. Coach also shows a compact “Find a better move → click/drag a piece → answer after final miss only” strip above the board, and the evaluation graph has a hover tooltip plus an explicit “click line to replay · pins to train” cue.

The no-spoiler contract is unchanged: none of the navigation, tour text, tooltips, hints, coach answers, or public API payloads name Stockfish’s best move before the final failed attempt.

## Data & persistence

- `data/preanalyzed-games.json` — 14 recent October 2026 games pre-analyzed by real Stockfish (67 mistakes) for an instant first session.
- `data/analysis-cache.json` — runtime cache for every other archive game or pasted PGN (gitignored).
- `data/custom-games.json` — imported PGNs (gitignored).
- `data/user-progress.json` — per-mistake mastery records (gitignored).
- `data/WHAT_TO_LEARN.md` — gitignored, spoiler-free curriculum generated from the current local cache. The tracked root-level `WHAT_TO_LEARN.md` is a historical snapshot.
- `.env` — optional server-only Gemini key (gitignored); `.env.example` documents every setting.

The self-test snapshots and restores runtime data files, so `npm test` does not leave imported games, altered mastery, or a partial full-archive cache behind. It also exercises the coach status, no-key local fallback, mocked Gemini intent selection and rejection of arbitrary provider text.
