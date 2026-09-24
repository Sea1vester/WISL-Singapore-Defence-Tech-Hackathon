# Demo flow, step by step

Button names below are the ones on screen. Keep the terminal running `./sdth-telemetry/scripts/demo-console.sh` visible next to the browser the whole time; it's half the demo.

Before they arrive: server up, console open at `http://127.0.0.1:8010/demo/`, no session connected yet (press **Clear session** if one is). Have `sdth-demo/fixtures/dji_csv_gps_jamming.csv` and the three files in `sdth-demo/fixtures/perturbed/` sitting in a Finder window.

Roughly twelve minutes if you don't get interrupted. You will get interrupted; that's fine.

---

## 1. Connect a session

**Do:** Open **Session**, paste `dev-teammate-key-change-me`, press **Connect**. The Mission library fills in on the left.

**Say:** "The console never has a key baked into it. You enter one, it goes in a header on every request, and the server checks it against a list. This one's the local development key. Connecting also imports the bundled missions into this laptop's SQLite, which is why the library just populated. They're synthetic flights from our generator; each is labelled as such."

**Why it matters to them:** the first thing in the rubric is "no mocks, no stubs". The library isn't a hardcoded list in the page; it's whatever the database says after a real import.

---

## 2. Open a clean flight first

**Do:** Click **Exercise · Normal control**. Wait for the replay to load. Open **Mission analysis** at the bottom.

**Say:** "Start with the boring one. This is a nominal flight: takeoff, cruise, return, land. The detectors ran on it and found nothing. I'm showing you this first because zero incidents on a clean flight is the control. If anything lit up here we'd have a false-positive problem, and we did have one in September, which I'll come back to."

Don't linger. Fifteen seconds.

---

## 3. Open the flagged flight and press play

**Do:** Click **Supplemental GPS-weak mission**. Press **Play** in the replay. Let it run for ten seconds or so, then point at the telemetry strip.

**Say:** "Same pipeline, different log. The aircraft follows its recorded positions on the recorded clock. Altitude, battery and UTC along the bottom are straight out of the log. Track speed is the one derived number, from consecutive positions. The path in the inset is the whole route.

Everything you see here is served from our own process, including the Cesium library and the terrain. No token, no CDN, and the terrain for this area is cached on disk. Take the wifi down and this still plays."

---

## 4. Show the flag

**Do:** In **Mission analysis**, the incident list shows one **operator_warning**. Click **Replay this observation**. The replay jumps to that timestamp and pauses.

**Say:** "This is the flag. The detector is a keyword rule on the warning text the vendor writes into the log, in this case 'GPS signal weak, hovering unstable'. The incident stores the timestamped samples it fired on, and 'Replay this observation' just seeks the replay to that time. So the flag and the picture are the same moment.

I want to be careful about what this is and isn't. The generator scenario is called gps_jamming, and that word is in the filename. What we can actually see in the log is a GPS-weak warning. The system says 'warning', not 'jamming', because it can't know the cause."

**Do:** Press **What happened?**, then **Where is the evidence?**, then **Similar warnings**.

**Say:** "These three are deterministic queries against the database. No model. 'What happened' summarises the stored incidents. 'Where is the evidence' lists the samples behind them. 'Similar warnings' looks across every other flight in the store for the same signature, and it finds one: a second aircraft threw the exact same warning. That's the moment this stops being a log viewer and becomes a fleet tool."

---

## 5. Recurring patterns and the bulletin

**Do:** Click **Recurring patterns**. There's a card for the GPS-weak signature showing two flights. Press **Create review bulletin**. The console switches to **Bulletins** and the new one is at the top.

**Say:** "Patterns are rebuilt every time a flight is indexed: group incidents across all flights by signature, count aircraft. Two aircraft with the same signature is a pattern.

A bulletin is a row a person creates from a pattern. It has the evidence summary, a list of things to review, and a limitations line saying it doesn't modify any aircraft. That's deliberate. This system produces evidence for a human. It never sends a command anywhere."

If someone asks what the bulletin is for: "It's the thing a maintenance lead or a flight-safety officer would read on Monday. Two of our aircraft lost GPS confidence in the same corridor last week; here are the timestamps; go look."

---

## 6. The PDF

**Do:** Stay on the GPS-weak mission. Press **⬇ Comprehensive PDF**. It says **Building PDF…** for about fifteen seconds. Open the download.

**Say:** "Everything in here comes from the database: the flight summary, the incident list with its evidence samples, the charts. It's ReportLab and matplotlib, no model. We had a model writing the narrative in an earlier version and took it out in the last week, because a report that reads differently every time isn't evidence."

Flip to the evidence page and point at the timestamps matching the incident you just replayed.

---

## 7. The big 3D view

**Do:** Press **Full view ↗** next to the replay heading. It opens `/replay/` in a new tab with the same flight. Toggle between **Map** and **Tabletop**. Drag to orbit, scroll to zoom. Press **Play** again.

**Say:** "Same viewer, full screen. Map is OpenStreetMap imagery on cached elevation. Tabletop is the same terrain drawn as a low-poly model, which is easier to read when you're looking at a path rather than a place. The aircraft model is oversized so you can see it; the path is at true scale.

The viewer only ever sees one endpoint, `/v1/flights/{id}/path`. It never sees raw vendor rows. That's the contract that let us swap the whole renderer once already: the first version of this was raylib, and we replaced it with Cesium in a week because the API didn't change."

Close the tab and go back to the console.

---

## 8. A fresh upload, twice

This is the step most likely to earn the "evidence the result is genuine" line in the rubric.

**Do:** Press **＋ Import a flight log**. Drag `dji_csv_gps_jamming.csv` onto the dropzone. Point at the terminal. Five lines appear: `stage=received`, `parsed`, `canonical`, `detected`, `done`, each with `ms=`. Wait for **Ready to review**.

**Say:** "This is the real pipeline on real bytes. Received is the hash and the extension gate. Parsed is the format registry picking the DJI CSV parser. Canonical is the projection into our L2 schema and the write to SQLite. Detected is the eight rules running. About forty milliseconds for a two-hundred-row file, and you can see where each millisecond went."

**Do:** Drag the same file again.

**Say:** "Same bytes. Look at the terminal: `dedup=true`, same upload id. The identity of a flight is the SHA-256 of the file. Upload it a hundred times, you get one flight. Change one byte and you get a different flight, which is what you want from evidence."

---

## 9. Let them break it

**Do:** Drag `dji_csv_perturbed_gps_weak_north2km_drop10_gap20s.csv` from the perturbed folder. Wait for ready. Open **Mission analysis**.

**Say:** "Your rubric says to shift the data north two kilometres and drop ten percent of observations. This file is that, plus a twenty-second hole cut out of the cruise. Two incidents: the GPS-weak warning still fires because the warning text survived the subsampling, and telemetry_gap fires on the hole. The random ten percent drop on its own doesn't trigger the gap detector, because one-in-ten at one hertz is a one or two second gap and the threshold is fifteen."

Then hand them the mouse. Offer the other two perturbed files (the normal control one stays clean; that's the point), an Excel or Orbiter version from `output/evidence/corpus-validation-v2/failure-fixtures/`, a file renamed to `.foo` (415 at the door), a truncated CSV (`stage=failed` in the terminal, nothing half-written), or their own DJI CSV run through `generate_perturbed_fixtures.py --input`.

---

## 10. Optional: the model

Only if Ollama is running and only if they ask.

**Do:** In **Mission analysis**, expand **AI-assisted analysis**, press **Analyze fleet records**. It streams.

**Say:** "This is the only place a model is involved, and it's fenced. It gets at most a hundred flight summaries and fifty incidents, never raw telemetry. Whatever comes back is checked: every hypothesis has to cite incident ids that were in the context we sent, or the whole answer is rejected. The panel says 'unverified' because it is. The deterministic answers you saw earlier don't depend on this at all; kill Ollama and everything else still works."

---

## 11. Close on the one that ends badly

**Do:** Click **Exercise · Recording ends airborne**. Press **Play**. Let it run to the end.

**Say:** "Last one. The log just stops with the aircraft still in the air. The mission_incomplete detector flags that: last sample airborne, no landing recorded. The incident carries the position of that last sample. We can't tell you why it stopped. We can tell you exactly where and when, and whether it's happened to another aircraft."

Stop there. Ask if they want to see the code for any of it.

---

## If something goes wrong

Server won't start: check nothing else is on 8010 (`lsof -i :8010`). Library empty after Connect: press **↻**. Replay black: the Cesium fetch failed on first run; `node sdth-replay/scripts/fetch-cesium.cjs` then restart. PDF button stuck on Building: check the terminal for a traceback and say so; the rest of the demo doesn't depend on it.
