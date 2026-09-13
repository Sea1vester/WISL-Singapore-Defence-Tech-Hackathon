# WISL: Recorded Flight Evidence for Fleet Learning

**Team:** Inessa Wong (NUS Mathematics and Computer Science) - ingestion and edge; Sylvester Lim (NUS Computer Science) - 3D visualisation, ingestion validation, platform infrastructure and cloud parsing; Isaac Sua (NUS Computer Engineering; DSO research intern) - proposed research support.<br>
**Mentor/advisor:** Unknown at time of submission draft.<br>
**Date:** 13 September 2026

## Abstract

WISL brings recorded drone logs into one searchable view so teams can investigate incidents and review recurring issues across flights. The proposed primary user is a Singapore Army small-UAS training and maintenance cell. WISL is an evidence-first post-flight pipeline: a controller-side uploader waits for a completed log, hashes and tracks it; a server-side registry parses supported formats; and a canonical L2 series supports detectors, replay, incident search and mitigation bulletins. The user interface demonstrates upload, normalised incidents, evidence queries and an optional language-model hypothesis path. It has no vehicle command channel.

The bounded all-90 simulator inventory projected 70/90 files to non-null, finite, schema-valid L2; 20 whole-path timeouts, all PX4 ULG or ArduPilot BIN, have no detector conclusion. Expectations were met for 36/90 files. A corrected targeted regression passed 12/12 files: ten original DJI CSV hazard exports and two separately labelled supplemental synthetic missions, including isolated upload, replay and query processing in 3.044 seconds for two representatives. The API suite passed 158 tests in 9.35 seconds; replay tests passed 13, UI tests passed 5, and parser tests passed 24 with 4 skipped.

These are simulator and software results, not field performance, causal diagnosis, throughput or cost claims. The original corpus has no normal control and only one exact GPS-weak mission. The operational implication is testable: an authorised team could measure whether WISL reduces time to locate, compare and review recorded evidence after an exception while retaining raw files, hashes and human decision authority in authorised settings for approved post-flight review workflows.

---

# 1. Introduction and problem statement

**User and workflow.** The proposed first user is an Army small-UAS instructor, maintainer or post-flight analyst. UAVs are becoming part of the soldier's arsenal, and MINDEF has stated the Army will establish DARE to scale UAV and ground-vehicle operations [1]. The V15 mini-UAV is publicly described as an Army tactical ISR platform, deployable from a confined space; 11 C4I Battalion operated V15s during Exercise Wallaby training [2], [3]. These facts establish a plausible context, not demand validation, endorsement or access.

After a recorded warning, loss of telemetry, anomalous track or maintenance concern, a reviewer can have several raw formats and a manual, flight-by-flight investigation. WISL proposes a post-flight evidence path: preserve raw input, normalise it, link detector observations to time and replay, then make similar stored signatures reviewable. It does not diagnose a cause from one warning and does not command an air vehicle.

**Before and after.** Repository history begins on 11 July 2026; there is no evidence in the repository of a 21 June baseline, so none is asserted. By September, the repository contains raw-log upload, a server-side parser registry, canonical persistence, deterministic incident indexing, Cesium replay, an evidence-query API, mitigation bulletins, privacy/retention primitives and an optional local-model analysis route. The shipped claim remains bounded to recorded-log review.

# 2. Prior work and competitive landscape

Flight analysis and fleet operations are established categories. PX4 Flight Review plots vehicle condition, while ULog is a self-describing message format [9]. ArduPilot Mission Planner downloads, graphs and replays DataFlash/MAVLink telemetry [10]. DJI FlightHub 2 provides cloud operations management, flight records, alerts and export; its on-premises deployment can store data locally, but FlightHub 2 does not connect other manufacturers' aircraft [11]. DroneLogbook imports diverse telemetry and provides replay, maintenance, inspection and compliance functions [12].

WISL should not claim a blank market. Its narrow potential distinction is cross-source **post-flight evidence workflow**: immutable raw provenance, an L2 schema, deterministic and inspectable observations, time-linked replay, and cautious pattern review. A recurring category is not proof of the same physical fault, and format skins of one generated mission are not independent recurrence evidence.

# 3. Technical approach

## 3.1 Recorded-log boundary and integrity

The edge uploader watches a designated controller log directory. A file is only eligible after its size is stable across scans. It computes SHA-256, retains status in a manifest and sends an authorised multipart raw upload with the digest. On the platform, supported extension checks, a bounded upload size, digest comparison, de-duplication and an upload record establish the intake boundary. The primary path keeps parsing server-side so controller extensions do not need format-specific logic.

The platform registry accepts the currently documented extensions `.bin`, `.csv`, `.hex`, `.hermes`, `.json`, `.ros`, `.stanag`, `.syslog`, `.tlog`, `.ulg`, `.ulog`, `.xlsx` and `.xml`. Support means an implementation path exists; it does not mean every real-world vendor export, encrypted file, firmware version or malformed log is covered. DJI detail-log accessibility can also require authorised export/decryption [11].

## 3.2 Canonical evidence and deterministic findings

Each parsed L1 payload is projected to a canonical L2 series with `flight_id`, ISO-8601 `timestamp_utc`, `position.{lat,lon,alt_m}`, `attitude.{roll_deg,pitch_deg,yaw_deg}`, `battery.{percent,voltage_v}`, `sensors` and `metadata`. Position is WGS84 degrees/metres when available; local north/east metres are deterministically projected from a configured local origin and marked `metadata.frame=local_ned`. Attitude is degrees; altitude is metres; battery percentage and volts retain those units. The current schema requires numeric values and the normaliser falls back to `0.0` for a missing numeric field rather than emitting `null`; missingness may be partly inspectable in provenance/sensors but zero is ambiguous. This is a material fidelity limitation to retire before operational use.

```json
{"flight_id":"f-123","timestamp_utc":"2026-03-18T09:42:30Z",
 "position":{"lat":1.3521,"lon":103.8198,"alt_m":38.0},
 "attitude":{"roll_deg":0.4,"pitch_deg":-1.2,"yaw_deg":92.1},
 "battery":{"percent":72.0,"voltage_v":15.2},
 "sensors":{"warning":"..."},"metadata":{"source":"dji_csv","frame":"wgs84"}}
```

Raw source provenance remains associated with the upload and canonical records. Deterministic detectors operate on this L2 boundary rather than on vendor opcode semantics. Current detector categories include low/critical battery, telemetry gap, attitude shock, frozen or last-known position, mission incomplete and operator-warning evidence. Current thresholds are **demo heuristics**, not platform-validated limits: battery low/critical at 20%/10%; 15 percentage points in 60 s; 25 m altitude step or 20 m/s vertical rate; 120 m/s air or 15 m/s ground implied lateral speed; 40/70 degrees attitude; and 15 s telemetry gap. A detector finding is an observation for triage, not a causal conclusion: GPS-weak text or a frozen position does not prove RF jamming.

Incident evidence is stored with a timestamp, detector category, signature and a records URL. The API exposes canonical record ranges and a visualisation-ready WGS84 flight path. Cesium replay follows recorded time, overlays indexed incidents, and can join later camera-frame census records. The camera census is a post-flight sidecar join, not onboard inference.

## 3.3 Search, recurrence and optional local hypotheses

`POST /v1/logs/upload` accepts the raw multipart file and optional `X-WISL-SHA256`, returning `{upload_id,status,sha256,duplicate}`. `GET /v1/uploads/{upload_id}` exposes parse/normalise status and error. `GET /v1/flights/{id}/records` returns canonical records; `GET /v1/flights/{id}/path` returns WGS84 replay samples; `POST /v1/demo/query` accepts a flight ID/question and returns deterministic evidence plus related signatures. Hash de-duplication is global to stored raw content: the same SHA-256 returns the existing upload ID rather than storing a second raw object.

SQLite records `flights -> ingest_events -> canonical_records`, with `translation_jobs` for normalised ingest state. `raw_uploads` holds raw-file provenance; `incidents` references flights; `incident_patterns` aggregates signatures; and `normalization_provenance` records parser, schema validation and value-origin metadata. In local demonstration mode, one in-process worker uses SQLite job rows for recovery and is deliberately not multi-process coordinated. The normal deployment queue is Redis. Parsing/canonicalisation/detectors do not await or call the LLM.

`POST /v1/demo/query` provides deterministic answers over a selected stored flight, its observations and matching signatures. It is useful even when the model is unavailable. Recurrence groups stored detector signatures; it must be labelled as a category-level pattern rather than independent mission or same-cause proof. A mitigation bulletin is reviewable output, not an automated fix, firmware push or command path.

The optional analysis endpoint is local-only by configuration: a guard rejects remote endpoints and cloud-model names. The default model is local `deepseek-r1:7b` (Q4_K_M, 7.6B) on the demonstration Apple M4 machine. It is invoked only on an explicit analysis click, not during parsing or detector execution. The model sees bounded summaries (up to 100 stored-flight summaries and 50 incident evidence items), has no tools, SQL access or vehicle controls, and its cited evidence IDs are validated. A model response is an evidence-linked hypothesis for human review; factual interpretation remains human responsibility. If the model is offline, malformed or unavailable, deterministic recorded evidence and queries remain available.

## 3.4 Open integration and sovereign-data posture

The public OpenAPI contract documents raw upload/status, normalised ingest/status, flight records, path export, incident reports, patterns and mitigation bulletins. JSON/JSONL export keeps the canonical series portable. WISL is a swappable post-flight node: a system owner can stop ingestion and retain raw files, hashes and exported canonical evidence. The current demo is not an accredited air-gapped deployment: CesiumJS is externally hosted and replay imagery uses OpenStreetMap unless cached or self-hosted. A deployment decision must define authentication, key custody, retention, encryption, network boundaries, map/asset hosting and classification controls before operational data is used.

# 4. Test methodology

The submission corpus is a simulator-generated hazards-only set: 90 files = ten scenario cards x nine format skins. Before the audit, criteria were set to: (1) registry parse success; (2) L2 schema projection; (3) parseable non-decreasing timestamps and finite canonical numerics; (4) scenario-card injected conditions reaching the corresponding deterministic incident type; and (5) one representative raw multipart upload checked through persistence, replay path and incident query. The test deliberately counts multiple format exports of one scenario as one simulated mission, and requires two distinct scenario cards before treating a signature as recurrence evidence.

This method establishes parser, canonicalisation, detector and API-path behaviour against constructed inputs. It does not establish detection sensitivity/specificity, causal inference, pilot workflow benefit, robustness to adversarial telemetry, GPS denial/spoofing, RF contest, real sensor dropout, weather, night/low light, clutter, vibration, thermal stress or real encrypted/vendor logs. No normal/control mission appears in the hazards-only directory. Field drops in mocked format skins may omit fields; those losses are a format-fidelity risk requiring audit, not evidence of a platform defect.

The API suite result is 158 passed with four deprecation warnings in 9.35 s (`output/evidence/api-tests.txt`). Replay Node tests are 13 passed, UI Node tests are five passed, and parser tests are 24 passed with four skipped (`output/evidence/parser-tests.txt`). The bounded all-90 inventory parsed/projected 70/90 to non-null/finites schema-valid L2; the other 20 were explicit whole-path timeouts, all ten PX4 ULG and ten ArduPilot BIN cases, so they have no detector conclusion. Deterministic scenario expectations were met for 36/90 files. By format: DJI CSV 10/10, DJI Excel 10/10, aunav 4/10, Hermes 4/10, Orbiter 4/10, vendor hex 4/10 and ArduPilot TLOG 0/10. The corrected targeted regression audit passed all ten original DJI CSV hazard exports plus two separately labelled supplemental synthetic missions: 12/12 parsed, projected to non-null/finites schema-valid L2, met expected deterministic detection, and completed without an 8-second whole-path or 15-second detector timeout. Two isolated upload/replay/query representatives completed in 3.044 s. This is simulator and software evidence only. The original 90-file hazards corpus has no normal control or independent second GPS-weak warning mission; the supplemental normal control and GPS-weak mission stay outside that denominator.

# 5. Results, limitations and cost

**Verified qualitative result.** The repository demonstrates a record-and-review workflow: raw upload, canonical persistence, deterministic observations, incident evidence, replay, deterministic query, optional local analysis and explicit unavailable-model behaviour. The supplied code prevents the LLM route from becoming a control channel and returns deterministic evidence when it is unavailable. One corrected four-flight local analysis call returned three hypotheses in 68.329 s; all cited IDs were verified. This validates local transport, response schema and evidence-reference handling, not semantic accuracy: the text invented "early morning" and speculated about air density/turbulence absent from the supplied data. No reliable causal-analysis claim is made.

**Regression found and corrected.** DJI valid zero relative height was previously treated as false and fell back to 180 ft MSL, creating artificial altitude-spike observations around takeoff/landing. The corrected parser retains valid zero; a new takeoff/landing regression fails on the old implementation and passes in the worktree, with six parser tests passing. Therefore, prior artificial altitude spikes are not presented as flight failures.

**What is not claimed.** No field flight, operational user study, normal control baseline, accredited security evaluation or reliability estimate is reported. The 90-file corpus is not a 90-flight operational evaluation. A warning label is not an attribution of jamming, sabotage, weather or component failure. A broad signature recurrence does not establish the same defect or independent physical missions.

**Measured local footprint, not a benchmark.** One Apple M4/16 GiB local state held four flights, 867 canonical records and three incidents in a 1,847,296-byte SQLite database; the local model file was 4,683,075,440 bytes. Five sequential exact-warning query trials measured 9.27, 5.82, 9.47, 14.61 and 7.60 ms. This single warm demonstration run is not a scale, throughput or cost-to-serve benchmark. No credible hardware unit cost, analyst-time saving or procurement baseline is available.

# 6. CONOPS, secondary applications and risks

**Primary mission thread.** After a small-UAS training sortie, a designated operator moves the completed controller log into the watched directory. The edge uploader waits for file stability, hashes it and transfers it to an authorised endpoint. A reviewer opens the persisted flight, sees time-linked rule observations, scrubs the 3D replay and opens recorded evidence. For a repeat signature, the reviewer compares source evidence across the permitted cases and may create a mitigation bulletin for human approval. The system remains silent in flight because it is post-flight only; an upload/parser/model failure must show status and preserve the source file for retry or manual review. Training burden is limited to selecting/uploading a log, reading evidence links and understanding that labels/hypotheses are not diagnoses.

Secondary applications are RSAF UAV governance/engineering review, where the public UAV Command has governance and maintenance roles [6], and Home Team/HTX historical review. HTX's MDOS already aims to unite drone systems and live telemetry [4], [5]; WISL must be framed as a possible post-flight complement, never as a unique multi-vendor control capability. RSN USV telemetry is a later adjacent extension, not current aerial-drone scope [8]. DIS/DOTC is a plausible integration stakeholder for local data/AI design, not a primary operator [7]. Other NATO sovereign buyers are a secondary market hypothesis, unvalidated here.

Show-stopper risks are access to representative authorised logs; classification and data-governance constraints; parser drift/encrypted exports; false confidence in labels or LLM text; lack of a normal baseline; inability to demonstrate independent recurrence; and dependency on externally hosted replay assets. Each must be retired with gated evidence, not prose.

# 7. Defensibility

The present defensibility is modest and must not be overstated. Open-source flight tools and commercial fleet-management products already provide log visualisation, replay and maintenance. WISL's defensible direction is an audited integration layer: raw hashes plus canonical evidence, a reviewed local deployment posture, deterministic observations accessible without a model, replay-to-evidence links and data/threshold knowledge accumulated under an authorised operator programme. That moat does not exist yet without sustained, governed real-log evaluation. No cost-to-parity estimate is credible without an integration scope and authorised data access.

# 8. Incubation plan: next six months

**Proposed route, not a commitment.** Request that the DVL programme sponsor facilitate an introduction to an appropriate Army small-UAS training/maintenance counterpart. No outreach has occurred and no sponsor or operator support is claimed. Month 1 gates are a discovery session, classification/data-flow review and permission to use either de-identified representative exports or synthetic data only. If those gates fail, development remains on synthetic/SITL material.

Months 2-3: agree a written data contract, format acceptance matrix and normal-case evaluation set; implement a provenance/fidelity report that shows retained, derived and missing fields by parser; test parser drift, corrupted logs, duplicate upload/retry and model-offline failure. Months 4-5: run a shadow post-flight study on a small authorised set, with pre-specified analyst tasks and a manual current-workflow comparator. Measure completion time, evidence retrievability, false-review burden and cases blocked by missing fields. Month 6: decide whether to pursue a limited sandbox continuation based on security approval, data fidelity, independent mission evidence and measured workflow value.

The team covers software, ingestion and visualisation. The stated research-support role is proposed; no DSO contribution or endorsement is claimed. The immediate asks are operator workflow feedback, an approved test data route and a test environment. Formal TRL entry/exit is not claimed because the required field evidence and programme assessment are absent.

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

# Appendix A. Validation artefacts and reproducibility

The completed independent validation artefacts are `docs/submission/corpus-validation.md` and `output/evidence/corpus-validation/corpus-validation.json`. The corpus command is documented in the former. The report builder is `scripts/build_wisl_final_report.py`; it creates the companion PDF from the text and report layout. This appendix is excluded from the ten-page body budget.
