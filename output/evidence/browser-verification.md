# Local browser verification — 13 September 2026

Verified in the Codex in-app browser against the actual loopback API and corrected four-flight SQLite demo:

- Connecting the development session loads four distinct original/supplemental simulation labels and the connected upload hint.
- Selecting the original GPS-weak flight shows exactly one operator-warning observation, with its recorded warning text; the previous artificial altitude-spike findings are absent.
- Embedded replay visibly displays the real map, recorded UAV/incident marker and playback controls. The duplicate full sidebar and empty-state panel are hidden. Full replay remains available separately.
- Clicking **Replay this observation** includes `2026-03-18T09:42:30.000000Z` in the replay URL. After loading, playback is paused at **00:01:30**, the expected offset from the record's 09:41:00 start.
- **Similar warnings** returns exactly the separate supplemental GPS-weak flight with the exact-warning-text match basis and a common-cause caveat.
- API checks additionally verified zero incidents for the supplemental normal control, one telemetry-gap incident for the dropout flight, an operator-warning pattern across exactly two stored flights, and creation of a review-only bulletin.

This is a functional/visual check on a local synthetic demo, not an operator usability study or a cross-browser compatibility claim. Optional model generation is documented separately in `local-model-analysis.json`; correct referenced IDs do not validate its interpretation.
