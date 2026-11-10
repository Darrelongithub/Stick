# Whole-video motion catalogue — work in progress

Source: tracked `output.mp4`. Full decode: 5709 frames, 24 fps, last decoded
frame at 237.917s. The earlier container-duration estimate was 237.875s.
Overview review: 119 samples, one every 2 seconds, across five sheets.
This is coverage of the entire timeline, not frame-by-frame visual approval.

## Timeline survey

| Seconds | Figures / visible activity | Adaptation considerations |
|---|---|---|
| 0–18 | All five; title poses, gestures and group stepping | Black background; title graphic, not a normal desktop shot |
| 20–26 | Orange enters desktop | Small figure, changing shot scale |
| 28–38 | Orange exaggerated stepping, lean, crouch and recovery | Clean background; first extracted sequence 31–35s |
| 40–60 | Orange reaches, places blocks, stretches upward, builds | Props and toolbar; camera changes |
| 62–70 | Orange sitting/reaching; Green approaching | Need isolate approach before overlap |
| 72–84 | Green/Orange block interaction and gestures | Overlaps, props and occlusion; not a clean single-character strip |
| 86–124 | Orange jumps, raises arms, handles blocks/tools | Useful new actions; separate each complete action and remove UI |
| 126–132 | Wide shot, Orange/Green | Too small for direct extraction at high quality |
| 134–138 | Green raises arms, reaches/extends; Orange watches | Green draft extracted; held block excluded by color key |
| 140–146 | Blue joins; jumps/moves near Orange/Green | Camera motion, vines and crossing figures |
| 148–152 | Blue prone/recovery, reaching/building, upward movement | Blue 150–151.5s draft; inspect hand edge and shot changes |
| 154–166 | Yellow jumps/steps/builds; Blue and Green also active | Yellow 156–157.2s draft; cut before shot transition |
| 168–172 | Red steps and jumps near tree/house | Red draft has feet occluded by foreground; needs repair or another source |
| 174–186 | Group building, reaching and movement | Many props/occlusions; isolate with per-shot regions |
| 188–194 | Yellow/Red gestures and stepping in closer shot | Good pose references; separate figures and carried objects |
| 196–214 | Multiple figures; crouching, reaching, leaping, TNT action | Camera cuts, overlaps and scenery; do not blindly color-key |
| 216–222 | Wide action/Blue confined behind glass | Glass effects and small scale unsuitable for clean extraction |
| 224–234 | Yellow stepping, leaning, reaching near glass | Further candidate sequence, not extracted yet |
| 234–end | Orange returns with tool; Yellow/Blue | Props, shot changes and end cut |

These labels describe visible sampled poses; they are not yet precise action
boundaries or a promise that every segment can become an independent animation.

## First multi-figure extraction drafts

| Figure | Source interval | Frames | State |
|---|---|---:|---|
| Orange | 31–35s | 96 | Silhouette draft reviewed previously; not a walk loop |
| Green | 134–135.5s | 36 | Reach/arm-raise draft; excludes held block |
| Blue | 150–151.5s | 36 | Reach/lean draft; mask edges need cleanup |
| Yellow | 156–157.2s | 29 | Step/lean draft, ends before camera transition |
| Red | 169.3–170.5s | 28 | Reference only; feet obscured, not shippable |

Outputs: `preview/reference/<figure-action>/{motion.gif,poses.png,source.json}`.
`all-figures-motion.gif` shows the five prototypes together, holding shorter
clips on their final pose; this combined preview is not synchronized source
footage. Each clip currently uses its own fixed shot crop/scale: **these are not
final matched character sizes**. Original timestamps are retained in metadata.
There is no new Red image set in the shipped pack yet.

## Reproduce

Dependencies: Pillow, PyAV, NumPy, SciPy. All output stays under ignored preview/.

```sh
python tools/catalogue_reference.py
python tools/extract_reference_motion.py
python tools/extract_reference_motion.py --character Green --start 134 --end 135.5 --roi .43 .24 .72 .90 --out preview/reference/green-reach
python tools/extract_reference_motion.py --character Blue --start 150 --end 151.5 --roi .60 .12 .96 .59 --out preview/reference/blue-reach
python tools/extract_reference_motion.py --character Yellow --start 156 --end 157.2 --roi .40 .17 .70 .77 --out preview/reference/yellow-step
python tools/extract_reference_motion.py --character Red --start 169.3 --end 170.5 --roi .40 .30 .75 .85 --out preview/reference/red-step
```

Extractor keeps the largest connected color component in a manually selected
region. This can discard disconnected hands/feet and cannot reconstruct hidden
body parts. ROI boundary checks catch some clipping, not all visual errors.
Every frame still needs visual review before pack integration. No generated
sprite or installed behavior was replaced by these experiments. Pickup/roaming
configuration stays at the pre-PR-9 baseline.

## Next work

Select complete actions and clean masks; normalize **matched body height**
across figures without altering source proportions; handle source translation
versus host movement; author entry/exit poses and 40ms tick mapping; integrate
small reviewed actions behind valid host behavior conditions. Real ShimeLinux
pickup and roaming need desktop checks before calling the result finished.
