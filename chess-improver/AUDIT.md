# Ongoing audit

This ledger covers the current unmerged sweep only. It records concrete issues rather than counting cosmetic changes or repeated test runs as separate bugs. The full-code-reading target has **not** been met. No full archive analysis has been run as part of this sweep.

## Verified and fixed

1. An unreadable progress file could be overwritten on the next attempt. The damaged-file regression checks that its bytes survive and writes fail safely.
2. A failed progress write could still alter in-memory mastery. The write-failure regression checks the prior status and revision.
3. An unreadable custom-game file could be overwritten by a new import. The damaged-file regression checks preservation.
4. A failed custom-game write could leave an import visible in memory. The write-failure regression checks the game count and revision.
5. Progress, custom games and analysis caches were written in place and could be truncated by an interrupted write. They now use same-directory atomic replacement.
6. A corrupt runtime analysis cache could be silently replaced by new analysis. Cache loading now blocks writes when that file is unreadable or structurally invalid.
7. The self-test could overwrite a real `.env` and live data while another server was using them. Tests now use isolated temporary files; a concurrent-server hash comparison confirmed that live files remained unchanged.
8. Mirror could reveal a newly created drill position if analysis completed while the profile or engine response was pending. The blind-position check now runs after each wait as well as before it.
9. An intermediate failed drill attempt returned a candidate principal variation before the final try. The retry regression now requires an empty PV and no opponent reply in feedback.
10. Blind hints could disclose the type of the Stockfish best piece. Public challenges now use a generic scan hint; spoiler checks cover legacy seeded hints.
11. Gemini safety metadata could bypass the exact-token gate and be shown as provider prose. Adversarial metadata tests cover the response and status.
12. Gemini model discovery could expose an untrusted model name. Discovered names are no longer echoed into the UI; the metadata regression covers this path.
13. An HTTP 400 for a retired Gemini model did not trigger the intended fallback. A mocked provider test verifies retry without displaying the provider error.
14. Repeated query parameters could crash the game search handler. A malformed-query regression now expects HTTP 400.
15. Malformed conversation history could crash the Gemini path. Invalid histories are rejected while valid coach follow-ups are tested.
16. Internal callers could request analysis of an unsupported chess variant. The service now rejects it, and the seed command filters unsupported games.
17. Resetting an unknown mistake created meaningless progress. The reset endpoint now returns 404, with a regression check.
18. Auto side detection could pick a substring match over an exact player name or silently pick a side for unknown names. Import regressions cover both cases.
19. Custom FEN games beginning with Black or a later move displayed incorrect move numbers and counts. The black-to-move import and analysis regression covers both.
20. Late-start FEN games could label their first moves as opening-book moves merely because they were first in the imported fragment. The live SSE regression checks a move-23 example.
21. Full-game engine sweeps could leave interactive moves waiting behind hundreds of queued evaluations. A scheduler regression verifies that live moves pass queued background work.
22. A signal-killed Stockfish worker could be reused rather than restarted. A live worker-kill regression verifies recovery.
23. Shutting down a Stockfish pool could leave queued or active requests pending. The shutdown regression checks both and rejects later requests.
24. Missing or illegal Stockfish results could silently become a neutral evaluation. The malformed-engine regression requires an error instead.
25. A second client joining an in-flight analysis received no progress. Two live SSE clients and a late subscriber are tested.
26. If batch analysis started a game first, an interactive subscriber could receive a result that was not yet persisted. The shared-job regression checks the cache on disk.
27. A successful second guess could remain marked unseen. A mastery-store regression verifies learning followed by a clean recall and mastery.
28. The import dialog could submit old text while a slow file was still reading, and the late read could overwrite a newer preset. A browser race test checks both behaviors.
29. The promotion picker lacked accessible piece names, focus handling and keyboard cancellation. A browser test checks focus wrapping, Escape and knight promotion.
30. The vault trainer had no dialog semantics or focus trap, and could be closed while grading. Desktop/mobile browser checks cover its focus and dismissal behavior.
31. Guided-tour focus could escape its modal and the spotlight measured continuously while idle. Desktop/mobile browser checks cover tour focus, navigation and dismissal; measurements now stop after settling.
32. The analyzed-game denominator excluded custom games while its numerator included them, allowing a false “full archive analyzed” claim. The curriculum now compares against all drillable archive and custom games.
33. The move sheet grouped custom FEN games by array position rather than recorded color and move number. A Black-to-move regression checks the correct columns and numbering.
34. Captured-piece icons were guessed from the starting material, so odds positions and promotions could invent captures. They now come from recorded move history; odds and en-passant regressions cover the distinction.
35. The clock strips showed the learner's clock after a future move and did not follow replayed positions. A position-specific clock regression checks both sides and unknown positions.
36. Material advantage was suppressed for the opponent, making an opponent lead invisible. The strip now calculates the signed balance for either color.
37. Choosing a promotion removed the focused dialog button without restoring keyboard focus. Focus now returns to the destination square before the move is submitted.
38. A successful drill disclosed Stockfish's best move and principal variation before failure, including when the learner played a different strong move. Both successful outcomes now use the same generic feedback, keep engine lines private, and provide a Continue action. Endpoint and desktop/mobile vault tests cover the new flow.
39. An alternative immediate checkmate could be rejected as a failure because the terminal mate score is represented as mate zero. A two-mate position now verifies that the alternate mate is accepted.
40. The Insights win-rate denominator included pasted and unfinished games even though its record counted only finished archive games. A population regression checks the corrected denominator and empty state.
41. The home rating chart silently combined different time controls and compared unlike ratings. It now shows a labeled single series, with a mixed-time-control regression.
42. The home chart hover selected the wrong month when the chosen rating series had gaps; it now chooses the nearest plotted point.
43. Rapid and bullet rating lines had the same color, and single-point rating series were invisible. Distinct colors and data-point markers make the plotted series distinguishable.
44. An assisted solve retained a previous clean-recall streak, so non-consecutive recalls could grant mastery. A regression now verifies that an assisted solve resets the streak.
45. Multi-game imports required Event to be the first tag of every subsequent game. The importer now splits on the next tag section and ignores tags inside comments; a reordered-tag regression checks both games.
46. A contradictory PGN result header and movetext could be recorded under the wrong result. Import now rejects the conflict atomically.
47. Saved custom-game JSON containing only a game ID passed validation and could crash library operations. A structural-corruption regression checks that the file is preserved and imports are blocked.
48. MultiPV validation checked only the first engine line, allowing invalid alternative scores or a mismatch between the best move and top line. Malformed-engine tests now cover those cases.
49. Cached heuristic explanations asserted unverified chess claims such as winning material or developing cleanly. Reveal feedback now uses only stored Stockfish evaluations and labels lines as continuations rather than guarantees, including for legacy caches.
50. A malformed analysis cache could pass validation when a required move or score was missing, then crash or propagate bad data. Validation now checks the consumed fields and preserves invalid runtime files; a regression mutates a real seeded record to exercise the guard.
51. Revealed engine lines numbered every half-move as a full move and ignored Black-to-move and late-start FENs. A FEN-based numbering regression checks both sides.
52. The reveal card described every MultiPV alternative as engine-approved even when it was a losing move. It now labels them engine lines without implying they are good moves.


53. Gemini fallback attempts were not individually counted or paced, allowing a retired model to exceed the configured daily generation budget. A mocked 404 regression verifies each attempt is reserved against the budget.
54. Coach status exposed the configured provider base URL, potentially including private endpoint credentials. A regression verifies the endpoint is omitted from public status.
55. Previously cached unsupported variant games could still appear analyzed and enter the vault or overview. A synthetic legacy Chess960 cache regression checks details, drills and counts remain excluded.
56. The learning plan recommended already-mastered positions even when nothing was due. A mastery regression verifies the recommendation list is empty, and the UI explains that state.
57. After a successful import, waiting for an optional overview refresh could block opening the imported game if the refresh stalled. Refresh now runs independently of launching analysis.

58. A slow “Train due” request could replace a drill the user selected while it was loading. A browser race test now verifies that the later response is ignored.
59. An empty filtered due queue falsely claimed all mistakes had been recalled, even when other due drills existed. The empty state now distinguishes filtered results from an actually empty due queue.
60. Failed vault or library requests could also show a success-like empty state or stale results. Errors no longer render those misleading states; a browser test exercises the vault failure.
61. A failed initial curriculum request had no retry, and out-of-order polling could overwrite newer plan data. Requests are sequenced, a retry restores the plan and home summary, and browser tests cover recovery.
62. Library scan progress divided by all archive games including unsupported variants, so a completed supported scan could never reach 100%. It now uses the supported-game denominator.

63. A move-sheet or graph replay selected while Stockfish was grading could be overwritten by the pending result. Replays are now blocked while grading; a delayed-response browser regression exercises the race.
64. Replaying the recorded game mistake, which does not consume a try, nevertheless locked the try-count selector. Both trainers now leave the selector adjustable; the delayed-response browser test checks the coach.
65. Four-second curriculum polling could continually invalidate responses when each request took longer than four seconds. Polling now schedules the next request only after the previous request settles.
66. The vault board described the learner as “to move” after replaying a move or flipping the board. It now derives the side to move from the displayed FEN.
67. A time control with no finished games was reported as having a 0% win rate rather than no data. The insights card now distinguishes the empty population.

68. PGN tag-like text inside a movetext comment could override player, variant or result metadata. The parser now reads the tag section only, with a multiline-comment regression.
69. An invalid PGN Result tag was accepted and silently treated as unfinished. The importer now rejects results outside the four PGN values, with an atomic-import regression.
70. Chess960 castling-right normalization indexed compressed FEN ranks as if they were eight characters and could discard mixed standard rights. Sparse-rank and mixed-rights regressions cover the conversion; variants remain undrillable.
71. A MultiPV request could return fewer lines than requested without error even when enough legal moves existed. A mocked-engine regression now rejects incomplete line sets.
72. The generated curriculum said there were no mistakes when all discovered drills were mastered. A saved-markdown regression checks the accurate empty state.
73. Batch analysis progress could include legacy cached unsupported-variant mistakes in its total. An isolated, mocked one-record batch regression checks the total without running an archive scan.

74. Engine-line validation checked only the first move, allowing an illegal later PV move to become a truncated continuation. A mocked-engine regression now rejects illegal continuation moves.
75. Cache validation accepted a malformed challenge FEN or an illegal claimed best move, which could crash a drill or present wrong chess. Corrupt-file regressions now preserve both cases instead of loading them.
76. If the initial archive overview failed, the header stayed on “Loading” and the user had no obvious recovery action. A mobile browser regression verifies the error and retry flow.
77. Changing Gemini's base URL or model without changing the key could reuse an answer and model-discovery cache from the old provider. A mocked-provider regression verifies reconfiguration takes effect.
78. When every drill was mastered, the local study coach told the user to start a nonexistent due drill. A mastery regression now checks the correct no-due guidance.

79. Saving a PGN and closing the import dialog left the overview and an already-open library stale; even “View in library” did not reload the mounted list. A browser regression verifies that successful saves refresh both, including when the dialog is closed.

80. The curriculum spoiler guard searched serialized text and rejected legitimate player or opening names matching a forbidden field name. Regressions verify those values are accepted while nested solution fields remain blocked.
81. PGN header parsing treated semicolons and braces inside quoted tag values as comments, corrupting names and breaking side detection. An isolated import regression now covers both characters.

82. Common `.env` syntax such as `export`, a byte-order mark, quoted values followed by comments, or inline comments could corrupt a Gemini key or model name. Reload tests now cover these forms.
83. An unreadable `.env` could crash coach requests or server startup, and a previously loaded key could remain in use. A regression verifies graceful fallback and removal of file-managed values.
84. Whitespace-only primary Gemini settings could suppress a valid fallback key or produce blank model names and incorrect pacing. Mocked provider tests verify fallback and defaults.
85. Gemini model discovery was a mandatory preliminary request even when the configured model worked, adding latency and potentially preferring an unintended model. A mocked test verifies the configured model is tried first, while retired-model discovery still works.

86. The coach built an unused text digest that could reject a legitimate opponent or opening name containing a spoiler-marker word. The stale digest was removed, and coach-visible metadata now safely falls back for such names; an isolated regression verifies that coaching still works.

## Revealed-move coach

Added a post-failure question interface for engine scores, comparisons and saved continuations. Gemini only classifies the question via an exact-token gate; answers are assembled from the already-revealed Stockfish data. Tests cover the shared provider budget, untrusted prose rejection, no-key fallback, and desktop/mobile reveal flow. This feature is not counted as an additional verified bug.

## Validation so far

TypeScript, production build, the REST/SSE/Stockfish/spoiler self-test and production dependency audit have passed. Desktop and mobile browser checks have covered the import dialog, vault, guided tour and promotion picker. Gemini provider calls have only been mocked; no real key was available. Changes remain on the current branch and have not been merged.

## Full-reading tracking

A complete reading means reviewing every first-party chess app source, configuration, launcher, and relevant documentation file; dependency lockfile internals, generated datasets, and third-party dependencies are not application code. **Completed full readings: 1.**

The first pass was completed across the preceding audit continuation and this pass: all files under `server`, `shared`, `src` and `bin`, the root launcher, app configuration, `.env.example`, `.gitignore`, README and historical curriculum document were reviewed. The code-reading target of 20 is not met; this count does not imply all bugs have been found.

Second reading in progress: reviewed archive parsing and persistence, analysis and attempt grading, engine worker scheduling, mirror opponent, API routes, environment loading, curriculum generation, Gemini, the board, application shell, client API, sound, import modal, library, learning-plan and solution-replay views, guided tour, PGN headers and curriculum generation. It is not yet a complete second reading.
