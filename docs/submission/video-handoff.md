# WISL demonstration video handoff

**Deliverable:** `WISL_Demo.mp4`, MP4, maximum 2:00. Create an unlisted backup link after export.<br>
**Purpose:** show recorded-log WISL system behaviour only. The report carries the problem statement, market and architecture. Do not add a pitch, a talking-head introduction, concept animation or architecture walkthrough.

## Required opening card (0:00-0:07)

On screen, plain text:

> WISL - Recorded Flight Evidence for Fleet Learning<br>
> Sylvester Lim | Inessa Wong<br>
> Mentor/advisor: none<br>
> 20 September 2026

Use a screen capture of the actual local system behind or immediately after the card. Do not use stock aircraft footage.

## Recording prerequisites

1. Start `./sdth-telemetry/scripts/demo-console.sh`, open `http://127.0.0.1:8010/demo/`, and connect through **Session**. The Mission library fills from the bundled fixtures, including the audited exercise set and both supplemental missions. Select records through **Flight library**; **Import log** opens **Logs & uploads**. Keep the large replay visible above the **Mission analysis** bar.
2. Keep the browser address bar, terminal or a small system-status inset visible briefly enough to establish that the application is running locally.
3. Use exact on-screen labels listed below. Every accelerated segment needs the label **"SPEED-UP: recorded UI wait shortened"** for its full duration.
4. Do not show secrets, API keys, personal locations, real personnel data or external network credentials.
5. Mentor/advisor is none. Put that on the card. Do not invent a name.
6. Capture at 1920x1080. Use the product UI at readable scale; do not crop out status/error messages.

## Shot list and voiceover (target 2:00)

Spoken copy lives in [`demo-pitch-vo.md`](demo-pitch-vo.md).
Use that track.
Keep the on-screen labels below.

| Time | Actual screen footage and required label | Voiceover / captions |
|---|---|---|
| 0:00-0:07 | Opening card above. | "Hey, we're WISL, and we're building a post-flight evidence pipeline for mixed drone fleets." |
| 0:07-0:12 | Connected local console, library populated. Label: **"LOCAL DEMO - synthetic recorded logs"**. | "Here's our system running locally on an M4 laptop with DJI drone logs." |
| 0:12-0:22 | Open the normal-control mission. Mouse over the empty incident feed. Label: **"NOMINAL CONTROL - 0 indexed incidents"**. | "Starting with an uneventful control flight, the log parses cleanly, and the detector engine flags zero incidents." |
| 0:22-0:55 | **Supplemental GPS-weak mission**. Play, Map to Tabletop, scrub to the warning. Label: **"RECORDED REPLAY - synthetic path"**. | "Next is a degraded sortie where the drone logged a GPS-weak warning, came home, and landed. The 3D replay toggles between map orientation and a local tabletop view. Scrubbing right to the marker highlights the exact warning string straight from the airframe, normalized so other stored airframes line up." |
| 0:55-1:20 | **What happened?** then **Similar warnings**. Label: **"DETERMINISTIC QUERY - exact warning text"**. Keep the answer visible. | "Instead of digging through raw tables, we can query what happened. The platform pulls exact evidence rows and instantly flags that another stored flight threw this exact same warning." |
| 1:20-1:32 | **Recurring patterns**, then create the review bulletin. Replay stays visible. Label: **"REVIEWABLE BULLETIN - no automated fix"**. | "When a signature shows up across multiple sorties, WISL drafts a human-review bulletin to alert maintainers - never issuing automated vehicle commands." |
| 1:32-1:46 | Stay on **Supplemental GPS-weak mission**. Click **Comprehensive PDF**. Record **Building PDF…** in the source take. **Grok bot: hard-cut that ~15s wait.** Jump to the open PDF in Preview, show a page, cut back. No SPEED-UP slate on this jump. Label: **"COMPREHENSIVE PDF - recorded evidence report"**. | "Same record, written out as a PDF the reviewer can keep." |
| 1:46-1:55 | **Analyze fleet records** with Ollama `deepseek-r1:7b` actually ready. Keep evidence IDs and limitations visible. Do not fake an answer. If the wait is cut, **"SPEED-UP: recorded UI wait shortened"** for the whole cut. Label: **"OPTIONAL LOCAL ANALYSIS - hypothesis for human review"**. | "Optional local analysis on this laptop. It suggests a reading from the stored evidence. A person still decides." |
| 1:55-2:00 | Open **Exercise · Recording ends airborne**. Play 3D. Label: **"POST-FLIGHT REVIEW ONLY - human decision required"**. | "Second recorded path. The log ends while the aircraft is still airborne. Post-flight review, keeping the human operator firmly in the loop." |

## Capture and editorial rules

- Use only footage of the actual app, local terminal, fixture chooser and replay. Any synthetic/SITL input must remain labelled when first shown and at replay.
- Do not present UI labels such as `jamming`, GPS weak or frozen position as a causal finding. Keep the deterministic-evidence caveat in frame or narration.
- Show a successful LLM answer only if it visibly includes evidence IDs and limitations; otherwise do not simulate one.
- The Comprehensive PDF wait is a mandatory hard cut: keep the click on **Comprehensive PDF**, jump straight to the open PDF in Preview, and remove the **Building PDF…** wait (about 15 seconds) entirely. Do not put a SPEED-UP slate on this jump; it should read as click → report.
- No narration about mission need, buyers, competitive landscape, architecture, value, TRL, field testing, cost or endorsements.
- If an API wait is cut, retain start/end status and show the speed-up label continuously. Do not cut away a failure.
- Export H.264 MP4, verify total duration <= 120 seconds, then upload to the approved unlisted host and add its URL to the submission checklist.

## Editor acceptance checklist

- [ ] Opening title/team/mentor/date card is present.
- [ ] Every screen is actual system footage; all synthetic/SITL and sped-up material is labelled on screen.
- [ ] Upload, normalisation, incident evidence, recorded replay, deterministic query, recurring bulletin and the Comprehensive PDF report each appear.
- [ ] The ~15 s **Building PDF…** wait is hard-cut out; no spinner, progress bar or SPEED-UP slate remains on that jump.
- [ ] No vehicle commands, live feed or causal diagnosis is implied.
- [ ] Duration is <=2:00 and filename is exactly `WISL_Demo.mp4`.
- [ ] An unlisted backup link is available after export.
