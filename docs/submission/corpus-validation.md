# Submission corpus validation

This validation concerns `/Users/sylvesterlim/CodingFun/SDTH/sdth-synth/out/hazards`, a hazards-only simulator corpus. It is not a field-flight evaluation, a claim about RF causes, or evidence of operational performance. The 90 original files were never modified.

Before execution, the audit criteria were:

1. Every input must return an L1 payload through the application `parse_raw_log` registry.
2. Every L1 record must project through `series_from_l1_payload`, validate against `CANONICAL_JSON_SCHEMA`, retain required scalar fields, have a parseable non-decreasing timestamp, and contain only finite canonical numbers.
3. A scenario-card condition is compared with the corresponding deterministic detector output. A match verifies this software path for the simulated record; it does not establish a physical cause.
4. A separate coarse observable-input inventory reports whether a normalized record visibly contains an input related to a rule. It is not a detector predicate, independent ground truth, or detector-accuracy measurement. Missing observables are neither detector negatives nor hits.
5. Multiple format skins of one scenario count as one simulated mission, not recurrence. The original corpus has ten scenario cards and no normal control.
6. Per-file processing is contained in a subprocess. The reported 30-second whole-path bound is an audit-choice performance guard, not a parser service limit. A timeout is a processing failure with no detector conclusion.
7. A representative multipart upload is processed with an isolated SQLite database and then checked through persistence, replay-path, and incident-query endpoints. It uses no Redis or model service.

## Reproduction

Use the repository virtual environment. This is the final full-inventory command and explicitly sets the audit bound:

```sh
PYTHONPATH=sdth-telemetry/platform-api:sdth-telemetry \
  /Users/sylvesterlim/CodingFun/SDTH/.venv/bin/python \
  sdth-telemetry/scripts/validate_submission_corpus.py \
  --input /Users/sylvesterlim/CodingFun/SDTH/sdth-synth/out/hazards \
  --out output/evidence/corpus-validation-v2/original90 \
  --timeout-s 30
```

The V2 fixtures are separately labelled and are not part of the 90-file submission. `sdth-synth/` is ignored in this checkout; first apply the retained field-preservation patch at `output/evidence/corpus-validation-v2/generator-skin-patch.diff`, then generate and audit the fixtures:

```sh
PYTHONPATH=sdth-synth/src \
  /Users/sylvesterlim/CodingFun/SDTH/.venv/bin/python \
  sdth-telemetry/scripts/generate_v2_failure_fixtures.py \
  --synth-root sdth-synth \
  --normal-scenario output/evidence/corpus-validation-v2/normal_control_v2.yaml \
  --out output/evidence/corpus-validation-v2/failure-fixtures

PYTHONPATH=sdth-telemetry/platform-api:sdth-telemetry \
  /Users/sylvesterlim/CodingFun/SDTH/.venv/bin/python \
  sdth-telemetry/scripts/validate_submission_corpus.py \
  --input output/evidence/corpus-validation-v2/failure-fixtures \
  --out output/evidence/corpus-validation-v2/failure-fixtures-audit \
  --timeout-s 30 --e2e
```

## Results

The complete original-corpus evidence is [`corpus-validation.json`](../../output/evidence/corpus-validation-v2/original90/corpus-validation.json). All 90 of 90 files parsed, projected to schema-valid L2, retained required non-null canonical values, had monotonic timestamps and finite numeric fields. The run took 130.96 seconds on macOS 15.7.4 / Python 3.13.6. There were zero whole-path and detector timeouts at the stated 30-second audit bound.

Forty of 90 format exports met all their scenario-card detector expectations. The generated report's coarse-observable inventory is intentionally only a record-content diagnostic; it cannot establish that missing outcomes are detector gaps or that the original simulations faithfully represent injected events. Native SITL and TLOG artifacts did not preserve scenario-card injections sufficiently for broad failure conclusions. Unsupported or missing-observable cases remain inconclusive.

By parser/format, the full-expectation counts were DJI CSV 10/10, DJI Excel 10/10, aunav 4/10, Hermes 4/10, Orbiter 4/10, vendor hex 4/10, ArduPilot BIN 4/10, PX4 ULG 0/10, and ArduPilot TLOG 0/10. The formerly time-bounded BIN and ULG members now returned detector outputs under the stated audit bound; those outputs do not retroactively validate their scenario-card failure causes.

The original corpus is ten simulated missions rendered through nine formats, and has no normal control. It cannot show recurrence of an exact warning text. GPS-related labels remain triage outputs: a weak GPS warning or stable reported position does not prove jamming, spoofing, or any other cause.

The V2 fixture evidence is [`corpus-validation.json`](../../output/evidence/corpus-validation-v2/failure-fixtures-audit/corpus-validation.json), with source cards and injected-event manifest in [`fixture-manifest.json`](../../output/evidence/corpus-validation-v2/failure-fixtures/fixture-manifest.json). It contains eight independently seeded synthetic failure missions and one independently seeded synthetic normal-control mission, each in four signal-preserving format exports: 36 files total. All 36 parsed, met all L2 integrity checks, completed within the bound, and met their declared detector expectations. The normal control's four exports produced no incidents. The two added multi-condition recordings retain explicit independent observations in the manifest: low battery plus a timestamp gap; and an exact GPS-weak warning plus a recording ending airborne. They are concurrent observables, never causal claims.

Before audit, all nine V2 missions passed the generator's realism/novelty gate, which checks battery/voltage consistency, ground/altitude coupling, route novelty against its reference profile, parser round-trips, and normal-cadence velocity consistency. The separate canonical audit checks finite numbers and monotonic timestamps. The intentional logger-dropout interval has no observed instantaneous velocity, so that rule does not compare an average gap displacement with a single-sample velocity; timestamp continuity and the other physical checks still apply. This gate is simulator quality control, not field validation.

The isolated upload/worker/replay/query check processed one V2 GPS-warning CSV and one V2 frozen-position JSON in 1.223 seconds. Both returned HTTP 202 then ready status, persisted 225 canonical records, returned a 225-sample replay path and HTTP 200 incidents. The incident query returned `operator_warning` for the GPS-warning fixture and `last_known_position` for the frozen-position fixture. This is application-path evidence only.

For a recurrence demonstration, use the original `gps_jamming` scenario and the separately seeded `gps_jamming_022` V2 scenario as two distinct *simulated* missions; do not count their other format exports as extra missions. The V2 CSV suitable for the live library is [`dji_csv_gps_jamming_022.csv`](../../output/evidence/corpus-validation-v2/failure-fixtures/gps_jamming_022/DJI/dji_csv/dji_csv_gps_jamming_022.csv). Its exact warning is retained as text but does not establish a GPS-interference cause.
