# Corpus-validation evidence

`full-bounded-postfix/corpus-validation.json` is the completed 90-file inventory. It used `/Users/sylvesterlim/CodingFun/SDTH/.venv/bin/python` with `pyulog`, `pymavlink`, and the parser requirements installed. It completed in the recorded environment and uses an eight-second subprocess bound for each parser-to-detector path.

The submitted set has 90 files. Seventy passed parsing, L2 schema, required non-null-field, timestamp-monotonicity, and finite-canonical-value checks. Twenty hit the whole-path time limit: 10 PX4 ULG and 10 ArduPilot BIN. Scenario expectations were met for 36 files. The folder represents 10 inferred simulated missions (scenario cards), each exported in nine skins. It has no original normal control or exact GPS-weak recurrence pair.

The 20 timeouts are failures of the bounded processing check and have no negative detector result. ArduPilot TLOG parsed 10/10 but met zero scenario-card detector expectations. The detailed JSON is the source for file-level results.

`targeted-corrected/corpus-validation.json` is the focused post-fix regression: the 10 original DJI CSV exports plus two separate supplemental synthetic fixtures passed parsing, canonicalization, detector expectations, and required integrity checks (12/12). Its isolated database exercise uploaded, processed, persisted, replayed, and queried original `gps_jamming` and `gps_denied_frozen` logs in 3.04 seconds. It reported 225 replay samples and the expected `operator_warning` / `last_known_position` incidents respectively.

The supplemental files are outside the submitted corpus:

- `supplemental/normal-control/DJI/dji_csv/dji_csv_supplemental_normal_control.csv` is an injected-cue-free simulator control and produced no incidents after the DJI valid-zero fix.
- `supplemental/gps-weak-recurrence/DJI/dji_csv/dji_csv_supplemental_gps_weak_recurrence.csv` is a separate simulator mission with a distinct seed, home, and route; it produced `operator_warning` from the exact GPS-weak text.

These are simulator checks only. A GPS weak warning, frozen position, or the UI's `jamming` label does not establish an RF-jamming cause or another operational fact.

`corpus-validation.json` is a convenience copy of the final bounded inventory. `initial-environment-audit.json` preserves the earlier run before optional binary-parser dependencies were installed; it is not the final result. Progress files are retained for audit history.
