# What to say at the code check

This is the version to read the night before, not the version to read off during. Once you've gone through the demo a few times the words will come out on their own. Numbers are from the repo on 24 Sep. If the terminal shows something different on the day, trust the terminal.

## Opening

Start with the problem, not the stack. Something like:

"A small unit flying cheap drones from three or four vendors ends up with a pile of logs in four or five formats and no way to ask 'has this happened before'. WISL takes those recorded logs, whatever the format, and turns them into evidence you can query. It parses everything into one schema, runs a fixed set of detectors, shows you the flight in 3D at the moment something went wrong, and when the same signature shows up on a second aircraft it writes a bulletin for a human to review. None of the numbers come from a model. There is a local model, but it can only propose an explanation, and it has to point at evidence that already exists."

That's about thirty seconds. Then start the demo.

## While the demo runs

Follow the runbook order. Normal control first, then the GPS-weak mission, replay to the observation, ask the three questions, open Recurring patterns, make a bulletin, download the PDF. What matters is what you say over the top of it.

Point at the terminal early. Every upload prints five lines, received, parsed, canonical, detected, done, each with a time in milliseconds. A two-hundred-row DJI CSV takes about forty milliseconds start to finish. Parsing is seven of those, the canonical write about twenty, the detectors another seven. Say those numbers out loud; assessors like hearing that you know where the time goes.

The normal control is worth a sentence of its own. Zero incidents on a clean flight is the result you're showing, not the absence of one. If the detectors fired on that file we'd have a false-positive problem, and we did have one earlier, which I'll come back to.

Then do a fresh upload in front of them. Import log, drop `dji_csv_gps_jamming.csv`, watch the five lines appear. Drop the same file a second time. The terminal says `dedup=true` and returns the same upload id. The identity of a flight is the SHA-256 of its bytes; the flight id is literally the first twenty characters of the hash. Same bytes, same flight, forever.

On the PDF, mention that it's ReportLab reading straight from the database. There's no model call in it. We used to have one and took it out in the last week because we wanted the report to be the same every time.

Somewhere in here, say plainly what the system doesn't do. Post-flight only. Thirteen file extensions across nine vendor families. The thresholds are demonstration values we chose, not certified ones. Terrain is cached for three regions and outside those you get a flat globe, because we'd rather show nothing than invent ground.

## When they want to break it

The rubric literally says "shift north 2 km, randomly remove 10% of observations". Tell them we read that and built it. The perturbed files are in `sdth-demo/fixtures/perturbed/`, and they're not in the Mission library on purpose, so uploading one is a fresh ingest they get to watch.

You need three outcomes in your head:

The normal control, shifted two kilometres north with ten percent of rows dropped, 215 rows down to 197. No incidents. Dropping one row in ten at one hertz leaves gaps of a second or two, nowhere near the fifteen-second telemetry-gap threshold, and the implied speed between surviving samples stays sane.

The GPS-weak flight with the same treatment, 225 down to 202. One `operator_warning`. The warning is a text field in the log, and the row carrying it survived the drop. If a judge asks what happens if that exact row gets dropped, the honest answer is the warning would be missed. The synthetic flight repeats the warning text across the degraded window, so in practice several rows carry it.

The same flight with a twenty-second block cut out mid-cruise, 202 down to 182. `operator_warning` plus one `telemetry_gap`. The gap detector fires on the cut and not on the random drop, which is the point of having two files.

If they bring their own DJI CSV, the script does the same thing live:

```
.venv/bin/python sdth-telemetry/scripts/generate_perturbed_fixtures.py --input their.csv --north-m 2000 --drop-frac 0.10 --cut-gap
```

It prints what the detectors saw. Then upload the output and let them compare against the terminal.

Other things you can invite them to try. Upload one of the Excel, Hermes or Orbiter versions of the same scenarios from `output/evidence/corpus-validation-v2/failure-fixtures/`. Rename a file to `.foo` and watch it get a 415 at the door. Truncate a CSV with `head` and watch `stage=failed` with the parser's error; nothing gets half-written because the canonical rows go in as one transaction. Type the API key wrong and get a 401.

If they ask how much we've run through it: 126 synthetic logs across the nine formats, all of them projected to valid L2 inside the thirty-second bound, and 36 of 36 gated exports matched what their scenario cards said should happen. Separately we pulled public real logs off the internet and ran those for a false-positive check.

## The architecture conversation

Have `ARCHITECTURE.md` open for the diagram, but talk from the code. Go through the pipeline in the order the bytes travel.

The edge side is the folder watcher in `sdth-ingestion pipeline`. It waits until a file stops growing, hashes it, uploads the raw bytes with the hash in a header, and keeps a manifest so a restart doesn't re-send or lose anything. It knows nothing about formats. That was a deliberate choice: adding a vendor should be a server change, not something you push to a controller in the field.

Parsing is `parsers/registry.py`. Extension first, then a sniff of the content, then one of the parsers. DJI CSV and Excel, PX4 ULog through pyulog, ArduPilot bin and tlog through pymavlink, and text parsers for Hermes, Orbiter, aunav and a vendor hex format. Whatever goes in, what comes out is one L1 payload shape.

Then `canonical_series.py` turns L1 into L2, which is the schema every downstream piece is written against. UTC timestamp, position with a frame tag, attitude, battery, a sensors bag and a metadata bag that records where each value came from. Logs that only have local NED coordinates get projected from a reference origin and tagged as such so nobody mistakes them for GPS. The schema validation here earned its keep: it's how we found that the DJI parser was treating a genuine 0.0 metre altitude as missing data and backfilling it, which produced fake takeoff spikes in the replay.

`detectors.py` is the biggest file and the one they'll probably want to read. Eight rules, all on L2. Battery low and critical at twenty and ten percent. Battery plunge, fifteen points in sixty seconds. Telemetry gap, fifteen seconds of silence. Attitude shock at forty and seventy degrees. GPS jump, which is really an implied-velocity check: over 120 metres a second in the air or 15 on the ground, or a 25 metre step between samples. Last-known-position, roughly thirty seconds of unchanging pose. Mission incomplete, meaning the log ends with the aircraft still airborne. And operator warning, a keyword match on the warning text vendors write into the log, things like GPS, failsafe, motor, compass, return-to-home, link lost. Each incident stores the L2 samples it fired on in a JSON column. That's what "Where is the evidence?" reads and what the PDF prints.

Above that sits the fleet layer in `incidents.py` and `bulletins.py`. When a flight is re-indexed its rule incidents are deleted and rewritten in one transaction, then the patterns table is rebuilt across all flights by signature. Two flights with the same signature is a pattern. A bulletin is a row a human creates from a pattern and signs off. Nothing in the system ever sends a command to an aircraft.

`privacy.py` strips the operator's home coordinates before anything is persisted and writes an audit row saying it did. Retention runs on every ingest.

The replay is CesiumJS served from our own process, no Ion token. It only ever sees `/v1/flights/{id}/path`, which is a stable contract we control, never raw vendor rows. Terrain and OpenStreetMap tiles for the three demo regions are cached on disk.

The model path is in `demo_api.py`. It sends at most a hundred flight summaries and fifty incidents to a local Ollama instance, and when the answer comes back `_validate_model_response` throws it away if any hypothesis cites an incident id that wasn't in the context we sent. Timeouts fall back to the deterministic answer. The console labels the whole panel as unverified.

Finally the generator, `sdth-synth`, which isn't in the repo because its output is three gigabytes. It integrates a scenario card into a flight with a simple kinematic model and wind, then vendor "skins" write native-looking files. Two gates: one for physical sanity, one that refuses any home within fifty kilometres of a real reference location. The scenario cards are our ground truth for what the detectors should find.

Tests: 197 in the platform, 30 for the parsers, 27 for the replay, 5 for the console. Run them if they ask; it takes eight seconds.

## The "why" questions

These come up in some form every time. Short answers, then stop talking.

Why parse on the server and not the controller? Because the controller might be a phone. Keeping the edge dumb means a new vendor is a server deploy, and we keep the original bytes for audit. The cost is that uploads are bigger than they'd be if we pre-parsed.

Why hash-based identities? Re-ingesting is idempotent, duplicates collapse globally, and if someone edits a log it becomes a different flight, which is what you want from evidence.

Why not let the model do the parsing? We did, in July. It made up values. Not often, but it only has to happen once. We swapped in real parsers with schema validation and pushed the model to the edge of the system where it can only suggest, not assert.

Why SQLite? Because you can run it right now on this laptop with one command, and the same schema runs under the Redis and Compose deployment we built for the two-laptop demo in August. We haven't hit a size where SQLite is the problem.

Why synthetic data? We couldn't get rights to a real failure corpus of any size. Scenario cards give us ground truth, which real logs don't. Everything synthetic is labelled synthetic, and the real logs we did get were used to hunt false positives rather than to demo.

Why cache Cesium and tiles locally? So the replay works with the wifi off, and so we're never quietly fetching terrain for a location we haven't vetted.

If they want to see you change something, change a threshold in `detectors.py`, hit `POST /v1/flights/{id}/index-incidents`, and show the incident list move. That takes under a minute and covers the "can modify the system live" line in the rubric.

They will ask who built what. Answer with file names, not areas.

## The story of the three months

They want to know the system changed because of what you learned, not just that it grew. Seventy-odd commits over 21 active days from 11 July to 21 September. The shape of it:

July was the prototype. SQLite, Ollama, and parsers for ulg, bin, tlog, csv and xlsx. The model was doing the normalising, and that's the version that invented values.

The big week was 22 August. In one push we did the unified parser contract, deterministic L2 persistence, incident indexing across missions, operator-location redaction with an audit trail, mitigation bulletins, the secure controller upload, and a two-laptop demo over Tailscale. We also wrote a raylib replay that week and threw it away for Cesium three days later.

Early September was the mentor feedback about cheap drones. We refocused, added the two UXO-related detectors (mission incomplete and last known position) and rebuilt the replay UI.

Mid-September was the synthetic corpus with its gates, the audit that found the DJI zero-altitude bug, and a relabelling. A mentor pointed out that a file called `gps_jamming` reads as a causal claim when all we can actually see is a GPS-weak warning. So the library now says "Exercise" and the docs say "the filename is not a diagnosis".

The last week was cleanup you can verify: PDF without the model, false-positive fixes after running real public logs, a coverage audit of those logs, local Cesium and tile caching, and the per-stage timing lines you've been watching.

The before-and-after files are in `output/evidence/`: `demo-console-live-before-altitude-fix.json` next to `demo-console-live.json`. Superseded work, including the collaboration brief with Orcrist that we dropped and the old report pipeline, is in `archive/`.

## Bonus points

The mission thread is: a watcher on the controller sees a finished log, hashes it and uploads it; the platform produces evidence; a human reads a bulletin and decides. The uploader survives restarts. Operator locations are redacted. The replay works offline for cached areas. Out of scope, and say so before they ask: live GCS links, anything running on the aircraft, automated fixes, and accreditation.

## When you don't know

Say "let me show you" and open the file. Never guess a number.
