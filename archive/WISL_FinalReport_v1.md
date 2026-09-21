# WISL: Recorded Flight Evidence for Fleet Learning

**Team:** Inessa Wong (NUS Mathematics and Computer Science) - ingestion and edge; Sylvester Lim (NUS Computer Science) - 3D visualisation, ingestion validation, platform infrastructure and cloud parsing.<br>
**Date:** 20 September 2026

## Abstract

Post-flight investigation of mixed unmanned aircraft fleets is constrained by vendor-specific log formats.
After a warning, telemetry gap or anomalous track, reviewers open native tools one airframe at a time, so comparable events across platforms remain difficult to retrieve.
Established analysers already provide single-stack diagnostics: PX4 Flight Review, Mission Planner, FlightHub 2 and DroneLogbook.
The remaining gap is a common evidence path from a completed log to a timestamped observation, a replayed trajectory and other stored flights that share the same signature.

This work reports WISL, a recorded-log pipeline built between July and September 2026.
A controller-side watcher waits until a file is size-stable, hashes it and uploads the raw bytes.
A server-side registry parses supported formats into a canonical L2 series of position, attitude, battery, sensors and metadata.
Deterministic detectors index observations; replay follows recorded time; queries return stored evidence; recurring signatures produce reviewable bulletins.
An optional local model can draft a hypothesis against checked evidence identifiers.

On a 90-file simulator inventory of ten scenario cards and nine format skins, every file projected to schema-valid L2 and completed the detector path within 30 seconds; 40 of 90 files met the predeclared scenario-card expectation.
A second gated set of 36 exports met all declared expectations, and the normal control produced no incidents.
The application suite passed 161 tests.
A DJI parser defect that invented takeoff altitude spikes was identified and corrected.
These measurements characterise software behaviour on constructed inputs and specify the next evaluation on authorised historical logs plus review.

---

# 1. Problem and contribution

Small unmanned aircraft are entering routine land operations.
MINDEF has stated that UAVs are becoming part of the soldier's arsenal and that the Army will establish DARE to scale UAV and ground-vehicle use [1].
The V15 mini-UAV is described as a tactical ISR platform that can be launched from a confined space; 11 C4I Battalion operated V15s during Exercise Wallaby [2], [3].
Those facts set the operational setting in which post-flight review will occur.

The practical difficulty is format fragmentation.
A completed sortie can leave a PX4 ULog, an ArduPilot DataFlash or MAVLink log, a DJI FlightRecord export or another vendor dump, each readable only in its native analyser.
PX4 Flight Review plots vehicle condition against a self-describing ULog [9].
Mission Planner downloads, graphs and replays DataFlash and MAVLink telemetry [10].
DJI FlightHub 2 records operations, alerts and exports, and can store data on premises, while remaining a DJI-only platform [11].
DroneLogbook imports mixed telemetry for replay, maintenance and compliance [12].
Each of these tools is effective inside its intended stack.
None of them, on the evidence of their public descriptions, give a reviewer one hashed raw file, one canonical time series, one timestamped observation and a search across other stored flights that share the same signature.

WISL was built to close that gap for a first user who already reviews completed small-UAS sorties: an Army instructor, maintainer or post-flight analyst.
Work on the repository began on 11 July 2026.
By September the system ingested raw logs, parsed them through a server-side registry, persisted a canonical L2 series, indexed deterministic observations, replayed recorded tracks, answered evidence queries and emitted reviewable bulletins when a signature recurred.
That is the contribution: a working post-flight evidence path across the formats the parsers already accept.

# 2. What was built

A controller-side watcher observes a designated log directory.
A file becomes eligible only after its size is stable across scans, which avoids capturing a log that is still being written.
The watcher computes SHA-256, records status in a manifest and sends an authorised multipart upload with the digest.
The platform checks extension and size, verifies the digest, de-duplicates stored bytes and records provenance before enqueueing parse.
Parsing lives on the server so the watcher stays format-neutral.
The registry currently accepts `.bin`, `.csv`, `.hex`, `.hermes`, `.json`, `.ros`, `.stanag`, `.syslog`, `.tlog`, `.ulg`, `.ulog`, `.xlsx` and `.xml`.

Each parsed L1 payload is projected to an L2 record with `flight_id`, ISO-8601 `timestamp_utc`, WGS84 position, attitude in degrees, battery percent and volts, a sensors object and metadata.
Local north/east metres are projected from a configured origin and marked `local_ned`.
Missing numeric fields currently fall back to `0.0`, which makes a true zero indistinguishable from an absent value and is the main schema limitation carried into later work.

Deterministic detectors then run on L2 rather than on vendor opcodes.
Indexed categories are battery low and critical, battery plunge, telemetry gap, attitude shock, GPS jump, last-known or frozen position, mission incomplete and operator-warning text.
Working thresholds for the demonstration are 20% and 10% battery, 15 points in 60 s, a 25 m altitude step or 20 m/s vertical rate, 120 m/s implied air speed or 15 m/s on the ground, 40/70 degrees of attitude, and a 15 s gap.
Incident rows store time, category, signature and a pointer back to the canonical records.
Replay follows recorded time on a WGS84 path and overlays those observations.
`POST /v1/demo/query` returns stored evidence and matching signatures.
When a signature appears on two or more flights, the patterns endpoint and a mitigation bulletin summarise the affected records for a human reviewer.
The demonstration queries are fixed: what happened on this flight, where the evidence sits in the record, and which other stored flights share the same warning text.
Hash de-duplication is global: a repeated SHA-256 returns the existing upload rather than a second raw object.
Persistence uses SQLite tables for flights, ingest events, canonical records, raw uploads, incidents, patterns and normalisation provenance; local demonstration mode runs one in-process worker, while the queued deployment uses Redis.

Two alternatives were considered and set aside.
On-controller parsing would have required every ground station to carry vendor-specific logic; a server-side registry was chosen so one acceptance matrix can be maintained.
Using a language model as the normaliser was rejected: numeric series and detector thresholds remain deterministic, and the local model is invoked only on an explicit analysis click, sees at most 100 flight summaries and 50 evidence items, and has its cited identifiers checked.
One four-flight analysis call returned three hypotheses in 68.329 s with valid cited IDs; the text also invented context that was not in the supplied samples, so the model is treated as a drafting aid on top of the deterministic path.
The public OpenAPI contract covers upload, status, records, path, incidents, patterns and bulletins; canonical JSONL is exportable.

The working path is one completed log.
An operator drops the file in the watched directory or uploads it.
WISL then returns a canonical time series, timestamped observations, a replay of the recorded track, and a bulletin if the same signature already exists on other stored flights.
A GPS-weak warning or a frozen track appears as an observation at a time on that path, ready to inspect.
Replay uses cached or hosted map imagery.

# 3. Testing and results

Criteria were declared before the corpus audit: registry parse success; L2 schema projection; parseable, non-decreasing timestamps and finite numerics; scenario-card injected conditions reaching the matching detector type; and one representative multipart upload followed through persistence, replay path and incident query.
Multiple format skins of one scenario card count as one simulated mission.
Two distinct scenario cards are required before a signature is treated as recurrence evidence.

The original inventory is hazards-only: 90 files from ten scenario cards and nine format skins.
All 90 projected to non-null, finite, schema-valid L2 and completed the detector path within a 30-second bound, with no whole-path timeouts.
Forty of 90 files met their scenario-card detector expectations.
By format, DJI CSV and DJI Excel met 10/10; several text skins met 4/10; PX4 ULG and ArduPilot TLOG met 0/10 because those native artefacts did not retain the injected conditions.
The original directory contains no normal control and only one exact GPS-weak mission.

A second, physically gated set was therefore generated: eight independently seeded failure missions and one normal control, each in four signal-preserving exports (36 files).
All 36 parsed, met L2 integrity checks, finished within the bound and met declared detector expectations.
The four normal-control exports produced no incidents.
The fixture gate checks battery-voltage consistency, ground-altitude coupling, route novelty, parser round-trip and normal-cadence velocity.
An isolated upload of one GPS-warning CSV and one frozen-position JSON reached ready status in 1.223 s, persisted 225 canonical records and returned the expected `operator_warning` and `last_known_position` observations.

The application suite passed 161 tests in 5.92 s; replay tests passed 15; UI tests passed 5; parser tests passed 28 in 0.73 s.
During validation, DJI valid zero relative height had been treated as false and replaced with 180 ft MSL, which created artificial altitude-spike observations around takeoff and landing.
The parser now retains valid zero, and a regression that fails on the old implementation is in the suite.

On one Apple M4, 16 GiB machine, four flights, 867 canonical records and three incidents occupied 1,847,296 bytes of SQLite; five sequential exact-warning queries measured 9.27, 5.82, 9.47, 14.61 and 7.60 ms.
These figures describe a warm local demonstration, not a scale or cost-to-serve study.

Taken together, the results show that constructed logs can be hashed, parsed, indexed, replayed and queried, that a normal control can remain silent, and that a real parser defect can be caught and closed.
They also show that native SITL skins of the original ten scenarios often fail to carry the injected event, which is why the expectation rate on the 90-file set is 40/90.
Field sensitivity, encrypted vendor exports, operator time and causal attribution were outside the audit.

# 4. Use and next steps

In the intended thread, a designated operator places a completed controller log in the watched directory after a small-UAS training sortie.
The watcher hashes and transfers it.
A reviewer opens the stored flight, inspects time-linked observations, scrubs the recorded track and compares any recurring signature before issuing a bulletin for human approval.
RSAF UAV Command's published governance and engineering role [6], and HTX work to unite Home Team drone systems [4], [5], are adjacent settings in which the same post-flight path could be tried.
RSN unmanned surface-vessel telemetry is a later transfer, not present scope [8].

The main unknowns are access to representative authorised logs, classification and retention rules, parser drift on real firmware, and whether reviewers actually retrieve evidence faster than they do today.
Over the next six months the priority is a gated evaluation, not product scale.
Month 1 is a discovery session and a data-flow review, with permission to use de-identified exports or to remain on synthetic material.
Months 2-3 produce a format acceptance matrix and a provenance report of retained, derived and missing fields, plus tests for corruption, duplicate upload and model-offline behaviour.
Months 4-5 run a shadow review on a small authorised set against the current manual workflow, measuring completion time, retrievability and false-review burden.
Month 6 decides on a limited sandbox from those measurements.
The immediate request is an introduction to an Army small-UAS training or maintenance counterpart, an approved test-data route and a named reviewer workflow.

# References

[1] MINDEF, "Speech by Minister for Defence, Dr Ng Eng Hen, at The Committee of Supply 2025 on 3 March 2025," 4 Mar. 2025. [Online]. Available: https://www.mindef.gov.sg/news-and-events/latest-releases/04mar25_speech3/

[2] MINDEF, "Fact Sheet: Latest Suite of Headquarters Sense and Strike Platforms," 30 Jun. 2021. [Online]. Available: https://www.mindef.gov.sg/news-and-events/latest-releases/30jun21_fs2/

[3] MINDEF, "Fact Sheet: Exercise Wallaby 2023," 9 Oct. 2023. [Online]. Available: https://www.mindef.gov.sg/news-and-events/latest-releases/09oct23_fs/

[4] HTX, "Robotics, Automation and Unmanned Systems," updated 10 Sep. 2026. [Online]. Available: https://www.htx.gov.sg/who-we-are/what-we-do/our-expertise/robots-automation-and-unmanned-systems

[5] HTX, "Unity in flight: Transforming drone control through MDOS," 2024. [Online]. Available: https://www.htx.gov.sg/whats-happening/all-news---events/all-news/2024/featured-news--unity-in-flight--transforming-drone-control-through-mdos

[6] RSAF, "Unmanned Aerial Vehicle Command," updated 19 Jan. 2026. [Online]. Available: https://www.rsaf.gov.sg/rsaf-forces/commands/unmanned-aerial-vehicle-command/

[7] MINDEF, "Fact Sheet: The Digital and Intelligence Service," 28 Oct. 2022. [Online]. Available: https://www.mindef.gov.sg/news-and-events/latest-releases/28oct22_fs/

[8] MINDEF, "The Republic of Singapore Navy's Unmanned Surface Vessels Progressively Operationalised to Enhance Maritime Security," 4 Feb. 2025. [Online]. Available: https://www.mindef.gov.sg/news-and-events/latest-releases/04feb25_fs/

[9] PX4 Autopilot, "Log Analysis using Flight Review" and "ULog File Format." [Online]. Available: https://docs.px4.io/v1.15/en/log/flight_review and https://docs.px4.io/main/en/dev_log/ulog_file_format

[10] ArduPilot, "Downloading and Analyzing Data Logs in Mission Planner" and "Telemetry Logs." [Online]. Available: https://ardupilot.org/planner/docs/common-downloading-and-analyzing-data-logs-in-mission-planner.html and https://ardupilot.org/planner/docs/mission-planner-telemetry-logs.html

[11] DJI Enterprise, "DJI FlightHub 2," "DJI FlightHub 2 On-Premises - FAQ," and DJI Developer, "Cloud API: Log Export," 19 Mar. 2025. [Online]. Available: https://enterprise.dji.com/flighthub-2; https://enterprise.dji.com/fh2-on-premises/faq; https://developer.dji.com/doc/cloud-api-tutorial/en/debug/log-export.html

[12] DroneLogbook, "Features - DroneLogbook - Simplifying Drone Operations." [Online]. Available: https://www.dronelogbook.com/hp/1/features.html

# Appendix A. Validation artefacts

Frozen artefacts: `output/evidence/corpus-validation-v2/original90/corpus-validation.json` and `output/evidence/corpus-validation-v2/failure-fixtures-audit/corpus-validation.json`.
They record the original hazards-only corpus and the gated failure-plus-control set.
The PDF is produced by `scripts/build_wisl_final_report.py`.
This appendix is excluded from the five-page body.
