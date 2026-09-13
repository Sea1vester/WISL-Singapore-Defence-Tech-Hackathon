# V2 fixture regeneration

`sdth-synth/` is ignored by this repository. The portable unified patch in `generator-skin-patch.diff` is required before regenerating V2 fixtures. It preserves simulator-sample warning and flight-mode fields in Hermès and Orbiter output, retains observed aunav ground fields while keeping it `GROUNDED`, and records two generator-gate corrections: controlled non-GPS warning vocabulary, and normal-cadence-only velocity coupling around intentional logger gaps.

Apply the patch from the repository root, then use the tracked generator. It emits no SITL, aunav, or vendor-hex fixture because those formats do not preserve enough airborne failure evidence for the stated V2 checks. The generator creates distinct seed/home variants, writes each scenario and injected-observable manifest, and fails closed if the existing realism/novelty gate reports an issue.

```sh
patch -p1 < output/evidence/corpus-validation-v2/generator-skin-patch.diff

PYTHONPATH=sdth-synth/src \
  /Users/sylvesterlim/CodingFun/SDTH/.venv/bin/python \
  sdth-telemetry/scripts/generate_v2_failure_fixtures.py \
  --synth-root sdth-synth \
  --normal-scenario output/evidence/corpus-validation-v2/normal_control_v2.yaml \
  --out output/evidence/corpus-validation-v2/failure-fixtures
```

The two supplemental cards at this directory define concurrent observable conditions: `battery_critical_logger_dropout.yaml` and `gps_weak_midair_end.yaml`. They are synthetic test conditions, never evidence that one condition caused the other.
