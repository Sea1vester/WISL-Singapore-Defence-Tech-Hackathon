# WISL — 5-Minute Pitch Script (Technical)

*(~1,030 words — denser than a standard 5-minute pace even at ~165 wpm for a technical
audience; this runs closer to 6 minutes as written, so trim the bracketed asides and the
"what's next" validation detail live if you're running long)*
*(Enabler framing / fleet-wide-leads structure preserved per NUS DVL feedback — this
pass adds real component names, endpoints, and numbers to the technical middle section)*
*(Updated for the cheap/COTS-fleet pivot: target platforms are now DJI, PX4/Auterion,
and ArduPilot, not the three named tactical platforms; "what's next" reflects the
multi-dataset validation and the vision-layer work actually done this quarter)*

**Diagrams** (source: `docs/diagrams/`) — bring these up on screen at the marked points,
don't narrate them; let the audience read while you talk over them:

| When | Diagram | What it's doing on screen |
|---|---|---|
| ~1:00, during "Where the value concentrates" | [`04-impact-matrix.svg`](docs/diagrams/04-impact-matrix.svg) | Up as you say "we're deliberately not chasing the other three" — the 2×2 makes the excluded quadrants visible instead of just asserted |
| ~2:00, during "The mechanism" | [`01-ingest-pipeline.svg`](docs/diagrams/01-ingest-pipeline.svg) | Up for the whole edge→queue→worker→schema paragraph — this is the one diagram doing real work, don't rush past it |
| ~2:50, right after "not guessed vendor opcodes" | [`03-physics-vs-opcodes.svg`](docs/diagrams/03-physics-vs-opcodes.svg) | Swap to this exactly on that line — it's the visual payoff for the sentence you just said |
| ~3:45, during "The demo, end to end" | [`02-fleet-payoff.svg`](docs/diagrams/02-fleet-payoff.svg) | Up alongside (or right before) the live replay/patterns-panel demo, as a map of what they're about to watch happen |

If you have a live screen to demo from, `02-fleet-payoff.svg` is the one diagram worth
cutting in favor of the real thing — a live screenshot or screen-share of the CesiumJS
viewer + Fleet Patterns panel is more persuasive than the abstract version, since it
proves it's real rather than describing it.

---

**[0:00 – 0:45] The honest claim**

Robotic failures are valuable data — but only if you can get to it. Today that data is trapped: locked in vendor-specific binary formats — PX4's ULog, ArduPilot's DataFlash, proprietary hex fault codes — scattered across disconnected silos, unreadable without an engineer in the loop.

WISL exists to fix exactly that: it turns transient mission failures into a permanent, queryable institutional record. We want to be precise about what that is. WISL doesn't win an engagement. It doesn't defend a site or take out a target. What it does is make the next mission better informed. That's a smaller claim than "real-time tactical advantage" — and it's the one we can actually defend.

**[0:45 – 1:45] Where the value concentrates**

That value concentrates in one specific place, and we're deliberately not chasing the other three. Losing one $2,000 DJI unit to a random crash is an expected cost of flying at that price point. Losing an expensive, small-fleet platform to a one-off failure is diagnosable the old way, with an engineer and enough time. And an expensive fleet failing systematically is rare in practice — you don't field hundreds of a multi-million-dollar UAV.

The value concentrates where cheap, large fleets fail systematically: a batch firmware bug, a bad ESC batch, a common jamming vulnerability — caught once, on one log, from one DJI, PX4, or ArduPilot unit, and propagated across the other three hundred before it happens to them too. That's why the brand catalog leads with DJI, PX4/Auterion, and ArduPilot instead of three named tactical platforms: there are enough of them, flying often enough, that a shared failure signature becomes real institutional value the moment it repeats twice.

What we're not claiming: that this rescues a single unit mid-flight, or that most crashes are mysterious enough to need reconstructing. Most aren't. The payoff sits specifically on the repeat failure, over days and weeks of fleet-wide learning.

**[1:45 – 3:30] The mechanism**

Here's the actual pipeline, live today.

On the controller, an edge process watches the log directory, SHA-256-hashes every completed file, and POSTs it as multipart form data to a `/v1/logs/upload` endpoint the moment the flight ends — no SD card, no specialist. The hash makes it idempotent: the same file is never processed twice, even across a reboot, and the server independently de-dupes on the same hash.

Ingest is asynchronous: the upload lands on a Redis queue, a worker picks it up, and the operator can poll a status endpoint that moves through `received → parsing → normalizing → detecting → ready` — typically single-digit seconds for a flight-sized log.

On the parsing side, a format registry sniffs the file — ULog, DataFlash or MAVLink telemetry log, CSV, Excel, hex codes — and maps every one of them into the same canonical schema: `position`, `attitude`, `battery`, `sensors`, `metadata`. That schema is schema-validated on the way in and is the part we treat as the actual product, not the renderer on top of it. It's what lets one operator query a DJI, a PX4 build, and an ArduPilot build through one API, without touching vendor tooling again — and it's where we think the real defensibility sits, because a forensic viewer alone is just a feature a drone-OS vendor bolts on.

On top of the canonical record, rule-based detectors run — pure threshold checks against real platform physics, not a model, and not guessed vendor opcodes. Ground speed above 120 m/s between GPS samples is flagged, because a DJI multirotor or a PX4/ArduPilot FPV build cruises well under 30 m/s; a ground rig gets a 15 m/s ceiling, because it physically cannot exceed that. A battery drop past 15 points in a minute is flagged — normal cruise drain is a few percent. A 15-second gap in an otherwise steady stream is a dropout. Same five rules, zero brand-specific code, because everything upstream already agrees on one schema.

For anything past a threshold — a narrative summary, a contributing-factor hypothesis — we route through a self-hosted language model, never a cloud API, with its output schema-validated and auto-retried against a repair prompt on failure. Same grammar-constrained discipline, applied to the layer that actually needs it.

**[3:30 – 4:30] The demo, end to end**

Once a log is `ready`, the replay client — a CesiumJS globe, real WGS84 terrain, OpenStreetMap imagery — pulls the trajectory from `/v1/flights/{id}/path` and animates the airframe along its recorded path, with incident markers dropped at the flagged timestamps and a plain-English summary alongside. Raw log in, 3D reconstruction and a readable incident report out. No specialist. That's step one, fully working.

Step two is the fleet layer, and it's the part we lead with. Every incident carries a signature — incident type plus detector — and once a signature recurs across two or more flights, it surfaces in a patterns endpoint: flight count, incident count, first seen, last seen. One call against that signature generates a mitigation bulletin: affected flights, what to check, what to brief before the next sortie — explicitly not a firmware push or a command channel, just a reviewable document. Failure log to fleet-wide fix, and every hop from upload to bulletin is the same pipeline that ran the single-flight demo, not a shortcut.

**[4:30 – 5:00] What's next, honestly**

Every piece of that loop runs today, and we've already started validating against real data instead of only synthetic: real per-flight GPS and battery telemetry, a corpus of over 1,800 actual DJI in-flight warning messages, and 554 real mission logs with labeled failures — zero false positives, and the threshold logic correctly stayed quiet on every real failure that wasn't a battery event. What's still open: a raw PX4 ULog or ArduPilot DataFlash binary file, which carries idiosyncrasies synthetic data can't surface, and a vision layer — we've pulled over 30,000 annotated camera frames to train an onboard object detector that will feed the same incident timeline as a stored camera frame.

WISL doesn't need to win the engagement to be valuable. Making the next mission better informed is enough — and owning a record no vendor can take from you is what makes that value last.

That's WISL.
