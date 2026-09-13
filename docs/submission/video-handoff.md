# WISL demonstration video handoff

**Deliverable:** `WISL_Demo.mp4`, MP4, maximum 2:00. Create an unlisted backup link after export.<br>
**Purpose:** show recorded-log WISL system behaviour only. The report carries the problem statement, market and architecture. Do not add a pitch, a talking-head introduction, concept animation or architecture walkthrough.

## Required opening card (0:00-0:05)

On screen, plain text:

> WISL - Recorded Flight Evidence for Fleet Learning<br>
> Inessa Wong | Sylvester Lim | Isaac Sua<br>
> Mentor/advisor: Unknown at time of submission<br>
> 13 September 2026

Use a screen capture of the actual local system behind or immediately after the card. Do not use stock aircraft footage.

## Recording prerequisites

1. Run the current local demo system and use the checked synthetic/SITL fixture(s) only.
2. Keep the browser address bar, terminal or a small system-status inset visible briefly enough to establish that the application is running locally.
3. Use exact on-screen labels listed below. Every accelerated segment needs the label **"SPEED-UP: recorded UI wait shortened"** for its full duration.
4. Do not show secrets, API keys, personal locations, real personnel data or external network credentials.
5. Fill the mentor/advisor line before recording; use the report’s explicit unknown status only if the organiser accepts it.
6. Capture at 1920x1080. Use the product UI at readable scale; do not crop out status/error messages.

## Shot list and voiceover (target 2:00)

| Time | Actual screen footage and required label | Voiceover / captions |
|---|---|---|
| 0:00-0:05 | Opening card above. | None or a single ambient cue. |
| 0:05-0:14 | Local demo status and fixture directory. Label: **"LOCAL DEMO - synthetic/SITL recorded logs"**. Show a selected normal-control fixture before upload. | "This is WISL running locally with synthetic or SITL recorded logs. It is a post-flight review tool." |
| 0:14-0:24 | Upload the actual normal-control fixture and show ready status with no incidents. Label: **"NOMINAL CONTROL - synthetic/SITL, 0 indexed incidents"**. | "This nominal control reaches a recorded review state without an indexed incident." |
| 0:24-0:37 | Upload the actual logger-dropout fixture. Show accepted/upload status and checksum if visible. Label: **"RAW LOG UPLOAD - recorded synthetic/SITL fixture"**. | "The system accepts a completed recorded log, preserves upload provenance, and waits for server-side parsing." |
| 0:37-0:50 | Show completed normalisation and the failure flight record/detail view. Label: **"NORMALISED RECORD - deterministic evidence"**. If processing is sped up, add the required speed-up label. | "The parsed record becomes a common evidence series. A detector label is an observation for review, not a diagnosis." |
| 0:50-1:05 | Open the logger-dropout incident list and click the timestamp/evidence. Label: **"DROP-OUT EVIDENCE - timestamp linked"**. | "Each finding links a type, time and recorded evidence. The reviewer can inspect the source record before deciding what it means." |
| 1:05-1:20 | Open actual Cesium replay; scrub to the selected dropout timestamp and use the incident jump or timeline marker. Label: **"RECORDED REPLAY - synthetic/SITL path"**. | "Replay follows recorded time and places the observation in the flight path. This is not a live aircraft feed." |
| 1:20-1:32 | Switch from the dropout record to the original GPS-weak flight; ensure the supplemental GPS-weak mission is already ingested. Run the deterministic same-warning query using the actual exact-text preset. Label: **"DETERMINISTIC QUERY - exact warning text"**. Keep the answer and caveat visible. | "This query matches exact stored warning text. Broad pattern categories remain a review cue, not proof of the same cause." |
| 1:32-1:41 | Show recurring pattern/bulletin screen. Label: **"REVIEWABLE BULLETIN - no automated fix"**. | "When a stored signature recurs, WISL prepares a reviewable bulletin. It never pushes a fix or commands a vehicle." |
| 1:41-1:50 | Request optional local analysis and show the actual local response, including evidence IDs and limitations. Record the full wait first (the measured trial took 68 seconds); if compressed into this slot, show **SPEED-UP: recorded UI wait shortened** throughout the compressed footage. Label: **"OPTIONAL LOCAL ANALYSIS - hypothesis for human review"**. | "Optional local analysis is bounded and evidence-linked. It is a hypothesis for human review, not a diagnosis." |
| 1:50-1:56 | Stop the local model or show the actual unavailable response, then keep deterministic evidence visible. Label: **"LOCAL MODEL OFFLINE - deterministic evidence remains available"**. | "If the model is unavailable, recorded evidence and deterministic queries still work." |
| 1:56-2:00 | Actual UI static end frame: incident evidence and replay visible. Label: **"POST-FLIGHT REVIEW ONLY - human decision required"**. | No sales claim. End on the visible product state. |

## Capture and editorial rules

- Use only footage of the actual app, local terminal, fixture chooser and replay. Any synthetic/SITL input must remain labelled when first shown and at replay.
- Do not present UI labels such as `jamming`, GPS weak or frozen position as a causal finding. Keep the deterministic-evidence caveat in frame or narration.
- Show a successful LLM answer only if it visibly includes evidence IDs and limitations; otherwise do not simulate one. Always show the actual offline/unavailable fallback after the successful clip, or extend that fallback if successful model output is unavailable.
- No narration about mission need, buyers, competitive landscape, architecture, value, TRL, field testing, cost or endorsements.
- If an API wait is cut, retain start/end status and show the speed-up label continuously. Do not cut away a failure.
- Export H.264 MP4, verify total duration <= 120 seconds, then upload to the approved unlisted host and add its URL to the submission checklist.

## Editor acceptance checklist

- [ ] Opening title/team/mentor/date card is present.
- [ ] Every screen is actual system footage; all synthetic/SITL and sped-up material is labelled on screen.
- [ ] Upload, normalisation, incident evidence, recorded replay, deterministic query, recurring bulletin and model-offline fallback each appear.
- [ ] No vehicle commands, live feed or causal diagnosis is implied.
- [ ] Duration is <=2:00 and filename is exactly `WISL_Demo.mp4`.
- [ ] An unlisted backup link is available after export.
