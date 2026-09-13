# WISL use-case and adjacent-tool research brief

**Scope and method.** This desk research uses primary publisher sources, accessed 13 September 2026. It identifies settings where flight-log normalisation, search, replay and recurring-warning analysis could be useful. It does **not** establish user demand, procurement intent, operational endorsement or a cost baseline; no stakeholders were contacted. “Fit” statements are explicitly reasoned inferences, separate from source facts.

## Recommendation: primary scenario

**Propose Singapore Army mixed small-UAS post-flight training and maintenance review as WISL’s primary user scenario.** MINDEF says UAVs are becoming part of a soldier’s arsenal and that the Army will establish DARE to scale UAV and ground-vehicle operations across Army units [1]. The V15 is a next-generation Army mini-UAV for tactical intelligence, surveillance and reconnaissance; MINDEF says it can be set up in under ten minutes and launched from a confined space [2]. In Exercise Wallaby, 11 C4I Battalion operated V15s for tactical ISR while supporting Army training [3]. These are official capability and training facts, not proof of a WISL requirement or sponsor endorsement.

**WISL fit (inference; highest relevance).** An authorised trial could ingest historical small-UAS/GCS exports; normalise time, vehicle, warning and event fields; replay the exception window; search similar prior flights; and aggregate recurring warning patterns by vehicle, battery, firmware, location class or training profile. This gives instructors, maintainers and post-flight analysts a common evidence trail across mixed systems. A local/on-premises deployment would keep raw logs and any optional local-LLM hypothesis generation inside operator-approved data controls. The LLM must only offer evidence-linked analyst prompts, never flight-safety determinations.

The value proposition is a **testable analyst-time hypothesis**: reduce manual work opening multiple vendor logs and locating comparable events. It is not a quantified saving. Baseline review time, alert volumes, formats, retention rules, classification and approval workflows are unknown and must be measured in a controlled evaluation.

## Ranked secondary contexts

1. **Home Team/HTX public-safety operations — high secondary/comparator.** HTX says RAUS employs BVLOS drones for medium-risk operations with 24/7 coverage across southern and central Singapore [4]. Its MDOS is being developed to unite different Home Team drone systems and return live video/telemetry to a common dashboard [5]. **Inference:** WISL could be evaluated as a historical post-flight complement to this real-time platform. Do not call WISL uniquely multi-vendor: MDOS already addresses multi-system control. The differentiated question is whether post-flight normalisation, case search and recurrence analysis improve investigation workflows.

2. **RSAF UAV governance and engineering review — high.** The UAV Command says it provides governance for SAF UAV operations, raises and sustains personnel, and has an engineering/logistics group responsible for operational maintenance and engineering [6]. **Inference:** a secure post-flight evidence index and repeat-warning view aligns conceptually with those stated functions, subject to system classification and integration approval.

3. **DIS as a secure analytics/integration enabler — medium.** DIS’s Digital Ops-Tech Centre is mandated to build agile digital responses and develop data-science/AI capability [7]. **Inference:** DIS/DOTC is a credible technical stakeholder for local processing, identity/access controls or integration patterns. It is not presented by this source as an aerial-drone operator, so it should not be the lead user persona.

4. **RSN maritime unmanned-system incident learning — medium/low for the current drone-log scope.** RSN MARSEC USVs began operational patrols in January 2025; MINDEF describes autonomous navigation in congested waters and a mission-control system for patrol profiles, vessel tracking, warnings and investigations [8]. **Inference:** the replay/recurring-event approach may transfer to unmanned surface-vessel telemetry. It is adjacent to, rather than proof of, an aerial-drone use case, so it should remain a later expansion pending data-format and mission review.

## What the market already provides

WISL should not claim that flight-log analysis, replay, warnings, maintenance tracking or fleet management are new categories.

* **PX4 Flight Review** already visualises PX4 flight logs to assess general vehicle condition and interpret plots; PX4’s self-describing ULog specification documents messages from sensors, RC input, internal states and string errors [9]. WISL’s possible distinction is cross-source normalisation, searchable case history and fleet-level recurrence workflow, not basic PX4 plotting.
* **ArduPilot Mission Planner** downloads on-board DataFlash logs, manually reviews and graphs fields, and plays back recorded MAVLink telemetry logs in the HUD/map [10]. WISL must complement, not replace, detailed native diagnostic tooling.
* **DJI FlightHub 2** is a cloud-based operations-management platform. DJI says it logs Dock/manual flights, exposes status/actions/user operations, exports flight summaries and detailed logs, and raises abnormal-condition alerts. DJI also documents on-premises local-only storage, one-click operation-log export, and that FlightHub 2 does not connect non-DJI drones [11]. WISL has no automatic claim to be superior; it needs to prove a workflow benefit for authorised post-flight, cross-platform analysis.
* **DroneLogbook** imports telemetry from major suppliers/ground stations, auto-fills flight data, supports GPS/3D replay, maintenance/inspection automation, and compliance/fleet reports [12]. That is direct adjacent competition for fleet records and maintenance. WISL therefore needs a narrow, evidence-led position around analyst investigation and recurring technical warning analysis.

## Practical pilot framing

Start with a small, authorised non-operational or de-identified export set. Candidate documented inputs are PX4 `.ulg` (self-describing ULog) [9], ArduPilot DataFlash and MAVLink telemetry logs [10], and authorised DJI detailed-log/operation-log exports [11]. Preserve original files and hashes; derive a common event timeline without mutating sources; return each search result to original-file/timestamp evidence. Keep the local LLM optional, disconnected from operational decisions, and constrained to evidence-linked hypotheses such as “similar warning sequence occurred in N prior indexed flights.”

**Proposed six-month incubation route (not an existing commitment).** Ask the DVL programme sponsor to facilitate access to an appropriate Army operator/training-and-maintenance counterpart for a discovery session, data-classification review and tightly scoped sandbox. No outreach has occurred and this research does not claim DVL support. Gate continuation on: authorised access to representative exports; a named analyst workflow; a baseline comparison; and safety/security approval. If any gate fails, keep the work to synthetic/de-identified data rather than implying operational validation.

Success measures should be agreed before trial: percentage of selected log formats ingested faithfully; whether an analyst can reproduce a reported event in replay; search precision on a labelled set of recurring events; and measured review time per case against the existing workflow. Do not invent monetary, safety or staffing savings until a baseline and outcome data exist.

## Sources

See [`research-sources.json`](research-sources.json) for titles, publishers, publication dates where listed, URLs, access dates, and the exact claims used. Citations: [1]–[12].
