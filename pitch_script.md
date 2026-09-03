# WISL — 5-Minute Pitch Script (Technical)

*(~830 words — denser than a standard 5-minute pace; a technical audience reads this
comfortably at ~165 wpm, but trim the bracketed asides live if you're running long)*
*(Enabler framing / fleet-wide-leads structure preserved per NUS DVL feedback — this
pass adds real component names, endpoints, and numbers to the technical middle section)*

**Diagrams** (source: `docs/diagrams/`) — bring these up on screen at the marked points,
don't narrate them; let the audience read while you talk over them:

| When | Diagram | What it's doing on screen |
|---|---|---|
| ~1:00, during "Where the value concentrates" | [`04-impact-matrix.svg`](docs/diagrams/04-impact-matrix.svg) | Up as you say "we're deliberately not chasing a third" — the 2×2 makes the excluded quadrants visible instead of just asserted |
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

That value concentrates in two places, and we're deliberately not chasing a third.

First: expensive, reusable platforms — ISR drones, UGVs, loyal-wingman class — where every airframe lost to an unresolved failure is a real, diagnosable cost. That's why we're built around the Elbit Hermes 900, the Aeronautics Orbiter 4, and the ST Engineering Taurus UGV specifically, not mass-attritable swarms. It matches how a force like the SAF actually operates — fewer, costlier, reusable systems.

Second, and this is the bigger case: systematic, fleet-wide failure modes. A batch defect, a firmware bug, a common EW vulnerability — caught once, on one log, and propagated across the entire fleet before it happens again. That's the real institutional asset: not a forensic tool for one incident, but a record no vendor can take away from you.

What we're not claiming: that this rescues a swarm mid-engagement, or that most losses are mysterious enough to need reconstructing. Most aren't. The payoff sits on the smaller, costlier slice of the fleet, over days and weeks of doctrine-level learning.

**[1:45 – 3:30] The mechanism**

Here's the actual pipeline, live today.

On the controller, an edge process watches the log directory, SHA-256-hashes every completed file, and POSTs it as multipart form data to a `/v1/logs/upload` endpoint the moment the flight ends — no SD card, no specialist. The hash makes it idempotent: the same file is never processed twice, even across a reboot, and the server independently de-dupes on the same hash.

Ingest is asynchronous: the upload lands on a Redis queue, a worker picks it up, and the operator can poll a status endpoint that moves through `received → parsing → normalizing → detecting → ready` — typically single-digit seconds for a flight-sized log.

On the parsing side, a format registry sniffs the file — ULog, DataFlash or MAVLink telemetry log, CSV, Excel, hex codes — and maps every one of them into the same canonical schema: `position`, `attitude`, `battery`, `sensors`, `metadata`. That schema is schema-validated on the way in and is the part we treat as the actual product, not the renderer on top of it. It's what lets one operator query the Hermes 900, the Orbiter 4, and the Taurus UGV through one API, without touching vendor tooling again — and it's where we think the real defensibility sits, because a forensic viewer alone is just a feature a drone-OS vendor bolts on.

On top of the canonical record, rule-based detectors run — pure threshold checks against real platform physics, not a model, and not guessed vendor opcodes. Ground speed above 120 m/s between GPS samples is flagged, because Hermes 900 cruises around 60; the Taurus UGV gets a 15 m/s ceiling, because a ground vehicle can't physically exceed that. A battery drop past 15 points in a minute is flagged — normal cruise drain is a few percent. A 15-second gap in an otherwise steady stream is a dropout. Same five rules, zero platform-specific code, because everything upstream already agrees on one schema.

For anything past a threshold — a narrative summary, a contributing-factor hypothesis — we route through a self-hosted language model, never a cloud API, with its output schema-validated and auto-retried against a repair prompt on failure. Same grammar-constrained discipline, applied to the layer that actually needs it.

**[3:30 – 4:30] The demo, end to end**

Once a log is `ready`, the replay client — a CesiumJS globe, real WGS84 terrain, OpenStreetMap imagery — pulls the trajectory from `/v1/flights/{id}/path` and animates the airframe along its recorded path, with incident markers dropped at the flagged timestamps and a plain-English summary alongside. Raw log in, 3D reconstruction and a readable incident report out. No specialist. That's step one, fully working.

Step two is the fleet layer, and it's the part we lead with. Every incident carries a signature — incident type plus detector — and once a signature recurs across two or more flights, it surfaces in a patterns endpoint: flight count, incident count, first seen, last seen. One call against that signature generates a mitigation bulletin: affected flights, what to check, what to brief before the next sortie — explicitly not a firmware push or a command channel, just a reviewable document. Failure log to fleet-wide fix, and every hop from upload to bulletin is the same pipeline that ran the single-flight demo, not a shortcut.

**[4:30 – 5:00] What's next, honestly**

Every piece of that loop runs today. What's left is validating it against real vendor logs instead of synthetic ones — the messy, platform-specific idiosyncrasies in an actual ULog or DataFlash file are exactly what the normalisation layer exists to handle, and synthetic data won't surface them.

WISL doesn't need to win the engagement to be valuable. Making the next mission better informed is enough — and owning a record no vendor can take from you is what makes that value last.

That's WISL.
