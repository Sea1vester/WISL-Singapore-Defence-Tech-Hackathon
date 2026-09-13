# Submission corpus validation

This validation concerns `/Users/sylvesterlim/CodingFun/SDTH/sdth-synth/out/hazards`, which is a hazards-only simulator corpus. It is not a field-flight evaluation.

Before execution, the audit criteria are:

1. Every corpus file must pass the application `parse_raw_log` registry.
2. Each parsed L1 record must project through `series_from_l1_payload` and validate against `CANONICAL_JSON_SCHEMA`.
3. Every canonical timestamp must parse and be non-decreasing; canonical numeric fields, including position, must be finite.
4. Checked-in scenario-card injected conditions must survive as the appropriate deterministic detector incident types. This is an implementation-path check, not confirmation of a real-world cause.
5. Exports of one scenario into several file formats count as one simulated mission. Recurrence evidence needs two distinct scenario cards in a comparable format.
6. A representative raw multipart upload must be processed with an isolated SQLite database, then checked through canonical persistence, replay-path, and incident-query endpoints. The test uses no Redis or model service.

The complete parser-to-detector audit is bounded at a chosen eight seconds per file. A timeout is a reported processing-performance failure, never a negative detection. The submitted corpus has one GPS-weak scenario only; it cannot establish recurrence of that exact warning text. A separately labelled supplemental synthetic mission is generated outside the submitted corpus for a demo comparison, and remains simulation evidence.

Run the full inventory from the repository worktree with the project virtualenv:

```sh
/Users/sylvesterlim/CodingFun/SDTH/.venv/bin/python sdth-telemetry/scripts/validate_submission_corpus.py \
  --input /Users/sylvesterlim/CodingFun/SDTH/sdth-synth/out/hazards \
  --out output/evidence/corpus-validation/full-bounded-postfix
```

Run the focused corrected regression and its isolated upload-processing check with the preserved 12-file targeted input set:

```sh
/Users/sylvesterlim/CodingFun/SDTH/.venv/bin/python sdth-telemetry/scripts/validate_submission_corpus.py \
  --input output/evidence/corpus-validation/targeted-input \
  --out output/evidence/corpus-validation/targeted-corrected --e2e
```

The generated JSON contains denominators, per-file outcomes, elapsed time, Python/platform details, and explicit limitations. In particular, a GPS weak warning or frozen position is not proof of RF jamming; detector labels remain triage labels.

## Results

The bounded full-inventory run is recorded in `output/evidence/corpus-validation/full-bounded-postfix/corpus-validation.json`. Of 90 submitted files, 70 parsed and passed the L2 schema, required-non-null, timestamp-monotonicity, and finite-number checks. Ten ArduPilot `.bin` and ten PX4 `.ulg` files exceeded the chosen eight-second whole-path audit bound; these are reported as processing-performance failures, not negative results or universal parser limits. The ten ArduPilot `.tlog` files parsed but met none of their scenario-card detector expectations.

Only DJI CSV and DJI Excel preserved all ten injected scenario expectations. The parser/detector expectation counts were: DJI CSV 10/10, DJI Excel 10/10, aunav 4/10, Hermes 4/10, Orbiter 4/10, vendor hex 4/10, and ArduPilot tlog 0/10. The 20 bounded failures have no detector conclusion.

The corrected focused regression in `output/evidence/corpus-validation/targeted-corrected/corpus-validation.json` passed all ten original DJI CSV files plus two supplemental simulator fixtures. It also completed isolated multipart upload, worker processing, L2 persistence, replay path, and incident query checks for original `gps_jamming` and `gps_denied_frozen` logs in 3.04 seconds. The supplemental normal control produced no incidents; the separate supplemental GPS-weak mission produced `operator_warning`. These fixtures sit outside the submitted corpus and are simulation-only.
