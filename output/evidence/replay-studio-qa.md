# Replay studio browser verification — 13 September 2026

Checked the running local demo at `http://127.0.0.1:8010/demo/` using the in-app browser, with the original synthetic GPS-warning flight (225 samples, 224 seconds).

- Confirmed the replay is the main screen area, with Mission analysis, Recurring patterns, Bulletins and Logs & uploads in the bar below.
- Observed the actual recorded clock advance at 12× and 1×, with the aircraft/trail moving over the map. The flight reaches 00:03:44, pauses and displays Replay complete. Play starts it again.
- Paused at approximately 9 seconds and confirmed the recorded time remained stable across subsequent interactions.
- Clicked the middle of the full-width timeline: the slider reported 50% and sought to approximately 1:52 within the 224-second recording.
- Selected Replay this observation: the viewer opened at 00:01:30 and remained paused, matching the warning's 09:42:30 UTC timestamp.
- Switched review tabs while the iframe remained mounted and playback continued.
- Used the included sample button through the actual multipart upload endpoint; the UI returned to the mission and Logs & uploads displayed Record normalized.
- Queried What happened? and received the actual operator-warning observation and a link to its recorded evidence.

The replay retains Cesium with a smooth globe surface in the embedded demo, toned map imagery, an oblique camera, accessible timeline, playback controls and recorded time/altitude. It requires external Cesium and map resources; it is not an offline imagery package or recorded onboard video.

The playback fix sets `viewer.allowDataSourcesToSuspendAnimation = false` on the constructed Viewer. This is a Viewer member, not a constructor option; see the [official Cesium Viewer documentation](https://cesium.com/learn/cesiumjs/ref-doc/Viewer.html#allowDataSourcesToSuspendAnimation). Scrub calculations now map 0–100 percent into the bounded recorded duration.

Automated checks: 15 replay tests and 5 console-contract tests passed. Browser checks above exercise the actual integration beyond those unit tests. Later corpus fixtures have separate audit evidence.

Final regression run on the updated backend: `cd sdth-telemetry/platform-api && ../../.venv/bin/python -m pytest -q` returned **161 passed**, four dependency deprecation warnings, in 5.92 seconds. Parser run: `cd sdth-telemetry/parsers && PYTHONPATH=.. ../../.venv/bin/python -m pytest -q` returned **28 passed** in 0.73 seconds. An initial parser invocation without its parent on `PYTHONPATH` failed collection; the corrected command above is the passing invocation.

The live demo was restarted with the updated backend. All nine newly audited synthetic CSV missions were imported and verified through the real upload/status/incident endpoints; the normal control produced no incidents. A repeat import confirmed checksum reuse. Per-flight evidence is in `corpus-validation-v2/live-demo-import.json`; its `duplicate_reused` flag distinguishes reuse timings from fresh processing. The new combined low-battery/recording-gap record was also opened in the browser, with moving replay and both recorded observations visible in Mission analysis.
