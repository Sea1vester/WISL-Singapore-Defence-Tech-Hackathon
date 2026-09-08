# WISL — 5-Minute Pitch Script

*(Spoken, ~820 words. About 5 minutes at a slightly brisk pace.*
*Leave air on slide 6 for the live replay.)*
*(Slides 01-08 are the talk. Appendix is for questions.*
*Don't read the slide. The slide has the numbers. You have the story.)*

**Diagrams** if you're presenting with extras besides the deck:

| When | Diagram | Why |
|---|---|---|
| Slide 3, "one place" | `docs/diagrams/04-impact-matrix.svg` | Only if the 2x2 isn't already on the slide |
| Slide 4, while you walk the pipeline | `docs/diagrams/01-ingest-pipeline.svg` | Skip if it doubles the mechanism slide |
| Slide 4, "not vendor error codes" | `docs/diagrams/03-physics-vs-opcodes.svg` | Visual payoff for that line |
| Slide 6 | Live Cesium replay, or `docs/diagrams/02-fleet-payoff.svg` | Prefer the live thing |

---

**[Slide 1 | 0:00 – 0:20] Title**

Hi, we're team WISL.

One line: we give cheap drone fleets a memory.

Not during the fight.

After.

I'll explain what that actually means.

---

**[Slide 2 | 0:20 – 0:55] The claim**

When a drone fails, that failure is useful.

Most of the time you just can't get to it.

The log is sitting on the controller, in a format only that brand knows how to read.

DJI dumps a spreadsheet.

PX4 writes one kind of file.

ArduPilot writes another.

Fly mixed fleets, which people do because these things are cheap, and those logs never talk to each other.

That's the gap.

WISL takes a mission that already happened and turns it into a record you can actually search later.

Same shape, whole fleet, and it stays with you.

We're quite clear about what this is not.

We're not real-time.

We don't defend a site.

We don't hit a target.

We can't catch a drone while it's falling.

What we can do is make sure the next mission already knows what went wrong on this one.

Smaller claim than "we win the fight".

That's the one we can stand behind.

---

**[Slide 3 | 0:55 – 1:35] Where it pays off**

And that value sits in one place.

We're not chasing the other three.

Lose one two-thousand-dollar DJI to a random crash?

That's just the cost of flying at that price.

Lose an expensive platform to a one-off?

You already have an engineer who can go look.

Expensive fleets failing the same way across hundreds of units?

Almost never happens.

The interesting case is cheap and systematic.

Bad firmware batch.

Bad motor-controller batch.

Jamming that shows up on more than one unit.

You catch it once, on one log, and you warn the rest of the fleet before it happens to them too.

That's why we lead with DJI, PX4, and ArduPilot.

There are enough of them that the same failure actually repeats.

Most crashes aren't mysterious.

The payoff is the one that happens twice.

---

**[Slide 4 | 1:35 – 2:40] The mechanism**

So what does that look like.

This is running today.

I'm not going to read the table.

After the flight, something on the controller watches the log folder, hashes the file, and uploads it.

No pulling the SD card.

Same file never gets processed twice.

A worker figures out the format and maps it into one common record: position, attitude, battery, sensors, metadata.

That common record is the actual product.

The globe is just how we show it.

Once everything's in one shape, you can ask about a DJI, a PX4, and an ArduPilot through the same interface.

On top of that we run simple checks against physics, not guessed vendor error codes.

120 metres a second between GPS points isn't the drone going supersonic.

That's a GPS jump.

Ground vehicle is capped at 15.

Battery through the failsafe bands.

A climb the airframe can't actually do.

A 15-second hole in the stream.

Same rules for every brand, because everything upstream already agrees on the schema.

If we need a written summary, that goes through a model we host ourselves, not a cloud API.

---

**[Slide 5 | 2:40 – 3:10] What we actually ran**

I want to be honest about what we've actually run.

This slide is the receipt.

The live demo is two DJI controller logs.

Both raise the same GPS-weak warning.

Once that shows up on two flights, it counts as a pattern.

On disk we also parse three PX4 ULogs, two ArduPilot DataFlash files, and one MAVLink tlog.

Real recorded files, with tests.

Vision is a sidecar.

We can attach camera frames and a ground-object count to the replay clock.

We have not fine-tuned the detector.

We're not going to stand here and say we have.

---

**[Slide 6 | 3:10 – 4:20] The demo**

End to end, this is what you're looking at.

I'll talk over it.

Raw log goes in.

A few seconds later: path on a globe, markers where things went wrong, plain-English write-up.

That's step one, and it works.

Step two is the part we actually care about.

Every incident gets a signature.

The moment that shows up on two or more flights, it surfaces as a pattern.

From that we generate a briefing note: what was affected, what to check, what to tell the next team before they fly.

It's not a firmware push.

It's not a command to the drone.

It's a document a person can read.

Failure log in, fleet-wide note out.

Same pipeline.

No shortcut behind the demo.

---

**[Slide 7 | 4:20 – 4:40] Future expansion**

The loop runs today.

What's still open is the vision fine-tune.

After that, landing-zone occupancy: take the ground-object count and combine it with altitude from the same record.

We're not claiming boxes on the globe.

That needs camera data we don't have on the log yet.

---

**[Slide 8 | 4:40 – 5:00] Close**

WISL doesn't need to win the engagement.

If the next sortie is better informed, that's enough, and that's the claim we can defend.

That's WISL.

Happy to take questions.

Appendix is behind this if you want architecture, detectors, or the datasets.

---

**If they ask (appendix, don't pre-empt)**

- Architecture: upload is hashed so the same file isn't processed twice.
  Status moves received, parsing, normalizing, detecting, ready.
  Patterns are signatures that recur on at least two flights.
  Bulletin is a briefing document, not a vehicle command.
- Why thresholds: they're explainable, they're the same across brands, and they sit on published failsafe bands.
  The model is reserved for the write-up and the optional ground-object count.
- Why not named tactical platforms: cheap large fleets are where a systematic failure actually repeats often enough for a shared record to be worth keeping.
- PX4 / ArduPilot: parsers and tests exist on real files.
  Three ULogs, two DataFlash, one tlog.
- Cloud: only the narrative layer uses a model, and that model is self-hosted.
- Vision: HUD and census are wired.
  Fine-tune has not been run.
  Nothing runs on the airframe.
  No boxes on the globe.
- Dataset slides A3-A5: those are offline looks at real logs and warning messages.
  They are not the ingest demo.
  Don't treat them as proof that `/v1/logs/upload` ate 554 missions.
