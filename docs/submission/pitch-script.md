---
marp: true
paginate: false
style: |
  section { background: #000; color: #fff; font-size: 40px; line-height: 1.35; justify-content: flex-start; padding: 64px 80px; font-family: Helvetica, Arial, sans-serif; }
  h1 { font-size: 22px; color: #8a8578; font-weight: 500; letter-spacing: .12em; text-transform: uppercase; margin: 0 0 28px; }
  strong { color: #c9a227; }
  em { color: #3ecfc2; }
---

# Hook

A drone lands after a GPS warning.
The log sits on a laptop.
The question is not what one vendor screen said.
The question is: have other flights shown the same warning?
*WISL* makes that reviewable.

---

# Problem

Our proposed user reviews completed flights
across a mixed drone fleet.
After a warning, a dropout, or an odd track,
the work is still one log, one tool, one flight.
Vendor analysers already exist.
They do not connect an observation
to evidence on another recorded flight.

---

# Solution

*WISL* brings recorded drone logs
into **one searchable view**.
Upload a completed log.
Inspect the normalised record.
Open the finding.
Replay it on the track.
Then ask what happened,
where the evidence is,
and which other flights share the warning.

---

# Differentiator

The value is the full review path:
from a recorded observation,
to another flight,
to a bulletin a person can approve.
A repeated warning is a reason to look.
It is not a diagnosis.
Optional local analysis can suggest a sentence.
The evidence still has to stand without it.

---

# Audience

First proposed application:
Army small-drone training and maintenance,
after the sortie.
Public sources show that flying is happening.
They do not show demand for *WISL*.
We are asking this programme
for supervised access to historical logs,
and an operator who can tell us
whether the workflow saves review time.

---

# Impact

We shipped upload, detectors, replay,
queries, and reviewable bulletins.
The audit used **90** simulator files
from **10** generated scenarios, not 90 missions.
A second gated set of **36** exports
includes a normal control with **zero** incidents.
We found and fixed a parser bug
that invented altitude spikes on takeoff.
These are software results, not field results.

---

# Close

Give us the logs and the reviewer.
Then we can measure the current workflow
against *WISL*, and keep what holds.
Learn from the last flight
before the next one goes out.
