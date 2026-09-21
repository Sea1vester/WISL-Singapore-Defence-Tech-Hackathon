# Natural voiceover script (WISL 2-minute demo)

Hard cap: **2:00**.
Label synthetic or sped-up material **on screen at the moment it appears**.
Do not read the labels as a disclaimer speech.

## Grok bot: PDF wait (mandatory cut)

Record the click on **Comprehensive PDF** and the full **Building PDF…** wait (about 15 seconds).
That wait is raw footage only.
In the final 2:00 edit, delete it.

Hard cut so the PDF looks instant:

1. Keep the click on **Comprehensive PDF** (one or two frames of the button is enough).
2. Jump straight to the open PDF in Preview.
3. Do not leave the spinner, progress bar, or **Building PDF…** label in the cut.
4. Do not put a `SPEED-UP` slate on this jump. It should read as click → report.
5. Show the actual PDF pages (Supplemental GPS-weak comprehensive report), then cut back to the console.

The local-model wait is a different cut: that one may stay labeled `SPEED-UP: recorded UI wait shortened`.

## 0:00–0:07 · Title card and intro

On screen:

WISL - Recorded Flight Evidence for Fleet Learning
Sylvester Lim | Inessa Wong
Mentor/advisor: none
20 September 2026

Voiceover:
Hey, we're *WISL*, and we're building a post-flight evidence pipeline for mixed drone fleets.

## 0:07–0:22 · Test environment and nominal control

On screen: `LOCAL DEMO - synthetic recorded logs`

Voiceover:
Here's our system running locally on an M4 laptop with DJI drone logs.

On screen: `NOMINAL CONTROL - 0 indexed incidents`

Action: Click into the nominal control mission, mouse over the empty incident feed.

Voiceover:
Starting with an uneventful control flight, the log parses cleanly, and the detector engine flags zero incidents.

## 0:22–0:55 · Degraded flight and 3D visualisation

On screen: `RECORDED REPLAY - synthetic path`

Action: Open **Supplemental GPS-weak mission**, press Play on the 3D track, trace altitude/battery.

Voiceover:
Next is a degraded sortie where the drone logged a GPS-weak warning, came home, and landed.

Action: Switch view from Map to Tabletop mode, zoom in slightly on the low-poly terrain/buildings.

Voiceover:
The 3D replay toggles between map orientation and a local tabletop view.

Action: Click Replay this observation, or scrub straight to the warning marker.

Voiceover:
Scrubbing right to the marker highlights the exact warning string straight from the airframe, normalized so other stored airframes line up.

## 0:55–1:20 · Query engine and fleet recurrence

On screen: `DETERMINISTIC QUERY - exact warning text`

Action: Click Ask this mission → What happened?, then click Similar warnings.

Voiceover:
Instead of digging through raw tables, we can query what happened.
The platform pulls exact evidence rows and instantly flags that another stored flight threw this exact same warning.

## 1:20–1:32 · Recurring patterns and bulletin

On screen: `REVIEWABLE BULLETIN - no automated fix`

Action: Click Recurring patterns → Create review bulletin.

Voiceover:
When a signature shows up across multiple sorties, *WISL* drafts a human-review bulletin to alert maintainers - never issuing automated vehicle commands.

## 1:32–1:46 · Comprehensive PDF

Stay on **Supplemental GPS-weak mission** so the findings column is visible.

On screen: `COMPREHENSIVE PDF - recorded evidence report`

Action: Click **Comprehensive PDF**.
Record the **Building PDF…** wait in the source take.
Grok bot: hard-cut that wait (about 15 seconds) out of the final video.
Open the downloaded `{flight-id}-comprehensive-report.pdf` in Preview.
Show the first page, then scroll one page of findings / evidence.
Cut back to the console.

Voiceover:
Same record, written out as a PDF the reviewer can keep.

## 1:46–1:55 · Local model

On screen: `OPTIONAL LOCAL ANALYSIS - hypothesis for human review`

Prereq: Ollama is serving `deepseek-r1:7b` at `http://127.0.0.1:11434`.
Restart `./sdth-telemetry/scripts/demo-console.sh` if it was started while Ollama was down.
Mission analysis should show the local model as ready.

Action: Expand AI-assisted analysis.
Click **Analyze fleet records**.
Keep the actual answer, evidence IDs, and limitations on screen.
Do not fake a model answer.
A live run has taken about a minute.
If that wait is cut, keep `SPEED-UP: recorded UI wait shortened` on for the whole cut.

Voiceover:
Optional local analysis on this laptop.
It suggests a reading from the stored evidence.
A person still decides.

## 1:55–2:00 · Second replay and closing

Action: Open **Exercise · Recording ends airborne**.
Press Play on the 3D track.

Voiceover:
Second recorded path.
The log ends while the aircraft is still airborne.

On screen: `POST-FLIGHT REVIEW ONLY - human decision required`

Action: Hold that tabletop or map replay to the 2:00 mark.

Voiceover:
Post-flight review, keeping the human operator firmly in the loop.

Export `WISL_Demo.mp4`, H.264, **≤2:00**.
Unlisted backup link after export.
