# Pitch Q&A — keep in reserve

Prioritise these three answers; the meeting suggested there may be time for only one or two questions. The new `pitch-script.md` is a separate three-minute Marp narration handoff. Preserve the existing deck's visual style when aligning slides. The old five-minute `pitch_script.md` remains a historical artifact.

**What is the value proposition?** WISL connects a recorded flight observation to its timestamped evidence, related flights and a reviewable follow-up bulletin. The proposed benefit is less manual reconciliation across a mixed fleet. We have not measured operator time savings yet. Existing products already offer log analysis and fleet features; we must prove the workflow benefit rather than claim the category is unique.

**Who would actually want this?** Our primary hypothesis is the Army small-drone training or maintenance team reviewing completed missions. Pilots and reviewers use it; the organisation operating the fleet would sponsor a pilot. Public MINDEF and Home Team sources establish relevant activity, but nobody has expressed customer interest in this project. The next step needs mediated access to historical logs and an operator review, because the team currently has no outreach channel. See the cited `research-brief.md` for land, air, maritime, DIS and Home Team fit.

**Why you?** Our current strength is hands-on integration across ingestion, validation, platform infrastructure and 3D visualisation. We can show a working path and a reproducible audit, including a parser defect the audit exposed and we corrected. We do not claim operational experience, a proprietary dataset, endorsements or an established moat. The incubation ask is support that fills those gaps.

**Does local AI mean offline or trustworthy?** Inference uses a local model and validates cited evidence identifiers. That does not validate the hypothesis itself. Replay still uses external map resources, and the model receives bounded summaries rather than all raw samples. Evidence queries continue if the model is offline or returns invalid output.

**Did you detect jamming or predict a crash?** No. The demonstrated record contains a GPS-weak warning. Its simulator scenario name is not evidence of interference or a causal diagnosis. Prediction and wearables are outside the demonstrated scope.

**What is Isaac's role?** The report lists research support as a proposed role, with his user-supplied academic affiliation and DSO research internship. Do not claim unverified implementation contributions or DSO endorsement.
