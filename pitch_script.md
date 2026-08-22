# WISL — 5-Minute Pitch Script

*(~720 words, paced for ~5 minutes with natural delivery pauses)*
*(Revised per NUS DVL feedback: enabler framing, fleet-wide case leads, demo arc ends on the fleet payoff)*

---

**[0:00 – 0:45] The honest claim**

Robotic failures are valuable data — but only if you can actually get to it. Today that data is trapped: locked in vendor-specific binary formats, scattered across disconnected silos, unreadable without an engineer in the loop.

WISL exists to fix exactly that: it turns transient mission failures into a permanent, queryable institutional record. And we want to be precise about what that is. WISL doesn't win an engagement. It doesn't defend a site or take out a target. What it does is make the next mission better informed. That's a smaller claim than "real-time tactical advantage" — and it's the one we can actually defend.

**[0:45 – 1:45] Where the value concentrates**

That value concentrates in two places, and we're deliberately not chasing a third.

First: expensive, reusable platforms — ISR drones, UGVs, loyal-wingman class — where every airframe lost to an unresolved failure is a real, diagnosable cost. That's why we're built around the Elbit Hermes 900, the Aeronautics Orbiter 4, and the ST Engineering Taurus UGV specifically, not mass-attritable swarms. It also matches how a force like the SAF actually operates — fewer, costlier, reusable systems, not disposable ones.

Second, and this is the bigger case: systematic, fleet-wide failure modes. A batch defect. A firmware bug. A common EW vulnerability. Caught once, on one log, and propagated across the entire fleet before it happens again. That's the real institutional asset here — not a forensic tool for one incident, but a record no vendor can take away from you.

What we're explicitly not claiming: that this rescues a mass-drone swarm mid-engagement, or that most losses are mysterious enough to need reconstructing. Most aren't. The payoff sits on the smaller, costlier slice of the fleet, over days and weeks of doctrine-level learning — not inside the fight itself.

**[1:45 – 3:15] How it actually works**

Here's how that happens, live today, not a mockup.

Raw logs — PX4 ULog, ArduPilot DataFlash, hex fault codes, whatever the platform writes — get pulled off the controller automatically the moment a flight ends. No SD card, no specialist standing by. Server-side, every format gets parsed into one deterministic, vendor-agnostic record, and that normalisation layer is the part we treat as the actual product — not the renderer sitting on top of it. It's what lets one operator query one unified record across every platform in the fleet, without needing vendor permission or vendor tooling ever again. That's where we think the real defensibility sits: whoever owns that data layer is hard to route around; a forensic viewer alone is just a feature a drone-OS vendor bolts on.

On top of that, rule-based incident detection runs against real platform physics — thresholds tuned to things like Hermes 900 cruise speed and Taurus UGV's top ground speed, not guessed vendor opcodes — so a battery-critical event or a GPS dropout gets flagged automatically, not by someone reading raw fields by hand.

**[3:15 – 4:15] The demo, end to end**

So here's the actual proof: a raw flight log goes in, and comes out as a 3D reconstruction of the flight — real terrain, real path, playable live in a browser — with a plain-English incident summary a non-engineer operator can read. No specialist required. That's step one, and it's fully working today.

Step two is the fleet payoff, and it's the part we lead with: when the same incident signature recurs across multiple flights, it surfaces in a patterns view, and one click turns it into a mitigation bulletin — which airframes were affected, what to check, what to brief operators on before the next sortie. Failure log to fleet-wide fix. No specialist in the loop, at either end.

**[4:15 – 5:00] What's next, honestly**

What's left isn't a missing component — every piece of that loop runs today. What's left is validating it against real vendor logs instead of synthetic ones, because the messy, platform-specific idiosyncrasies in a real ULog or ArduPilot file are exactly what the normalisation layer exists to handle, and synthetic data won't surface them.

WISL doesn't need to win the engagement to be valuable. Making the next mission better informed is enough — and owning a record no vendor can take from you is what makes that value last.

That's WISL.
