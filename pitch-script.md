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
The pilot has a log and a question:
was this an isolated event,
or have other flights shown the same warning?
*WISL* makes that question reviewable.

---

# Problem

Our proposed user is the team reviewing
completed flights across a mixed drone fleet.
Existing tools already analyse logs.
Our focus is connecting an observation
to its evidence and to other recorded flights.
We have **zero operator interviews** so far.
The need is a hypothesis we must validate.

---

# Solution

*WISL* brings recorded drone logs
into **one searchable view**,
so teams can investigate incidents
and review recurring issues across flights.
Upload a log, inspect the normalised record,
open an incident, and replay its evidence.
Then ask what happened,
where the evidence is,
and which other flights share the warning.

---

# Differentiator

The proposed value is the complete review path:
from a recorded observation,
to another flight, to a reviewable bulletin.
Optional local analysis suggests explanations
and links them to recorded evidence.
Those explanations still need human judgement.
A repeated warning does not prove a cause.
Prediction and wearables remain future work.

---

# Audience

Our first proposed application is post-flight
training and maintenance review
for Army small-drone fleets.
Public sources establish relevant drone activity;
they do not establish demand for *WISL*.
Air and Home Team fleets are further hypotheses.
We need an operator and accessible logs
to test whether the workflow saves review effort.

---

# Evidence and team

Our submission corpus contains **90 exports**
across **10 generated scenarios**.
These are synthetic and simulator records,
not 90 independent operational missions.
The audit records failures as well as passes.
*Inessa* works on ingestion and the edge pipeline.
*Sylvester* works on visualisation,
validation and platform infrastructure.
Our next proof must come from operational data.

---

# Close

We are asking for supervised access
to suitable historical logs and operator review.
That lets us compare the current workflow
with *WISL*, measure the difference,
and find what must improve.
Learn from past drone incidents
to make the next mission better informed.
