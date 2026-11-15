# AGENTS.md

## Behaviour

- Resolve Daily Calm from the current home feed's `todays-daily-calm` pack on
  every playback request. Never substitute an older session or the programme's
  first guide.
- Respect Calm's account lock flags before returning audio.
- Keep credentials and stream URLs out of logs and entity state.
- Declare runtime requirements only in `manifest.json`; the test task installs
  them from there.
