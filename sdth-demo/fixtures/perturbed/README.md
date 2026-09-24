# Perturbed fixtures

Synthetic DJI FlightRecord logs perturbed for the judges' unhappy-path test: home shifted north and ~10% of observations removed at random (`*_gap20s.csv` also has a 20 s telemetry block cut mid-cruise). They are NOT auto-imported into the Mission library — the console fixture list is hardcoded in `sdth-demo/demo.js`. Upload them via the console's "Import log" dropzone (Logs view) or `POST /v1/logs/upload` — both hit the same endpoint.

To perturb a judge-supplied DJI CSV (shift + drop, optionally a gap):

```
.venv/bin/python sdth-telemetry/scripts/generate_perturbed_fixtures.py --input their_log.csv --out fixtures/perturbed [--cut-gap]
```

This writes `<stem>_perturbed.csv` plus a `<stem>_perturbed.manifest.json` sidecar; it never touches this directory's `manifest.json`.

Regenerate:

```
.venv/bin/python sdth-telemetry/scripts/generate_perturbed_fixtures.py
```

See `manifest.json` for per-file perturbation parameters, gate results, and the incident types the platform detectors observed.
