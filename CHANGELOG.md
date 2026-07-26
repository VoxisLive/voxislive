# Changelog

Notable changes to Voxis. Version bumps are tagged in commit messages
(`vX.Y.Z: ...`); this file tracks contributions and fixes as they land.

## Unreleased

### Fixed
- The "Original audio (while speaking)" control on VB-CABLE setups now ducks
  the original speaker, not the background music — a same-day regression had
  it scaling the whole ambient mix uniformly instead.
- The "Translation volume" slider no longer plays quieter than its displayed
  percentage (it was being applied twice, effectively squaring the setting).
- Translated audio playback could be briefly delayed by a slow UI frame; UI
  updates now run off the audio-delivery thread.
- Closing the app while the floating overlay window was open could leave the
  process running in the background instead of exiting.
- History now loads noticeably faster (cached session summaries instead of
  re-parsing every transcript on every open).

### Added
- Both language pickers now show a permanent explanatory line — it's no
  longer ambiguous that the outgoing-language field only applies in Meeting
  mode.

### Fixed
- Word drops at translated-caption turn boundaries; captions now stream
  smoothly and stay in sync with the translated speech (superseded an
  earlier client-side word-pacing engine that caused the drops).
- Source-language captions are now paired to the correct translation turn
  using the model's actual simultaneous-interpretation lag, instead of
  drifting onto an earlier or later turn during continuous narration.
- A `TypeError` in `IncomingPipeline`'s text-sync callback signature that
  could interrupt a Meeting session.

### Added
- Settings > **Saving** tab: transcript folder, audio recording, and
  automatic TXT/SRT/VTT export formats (generated alongside the JSON on
  every save) are now grouped in one place; quick TXT/SRT/VTT export
  buttons also appear right after saving a transcript, without opening
  History.
- Automatic background pruning of old transcript folders (keeps the newest
  500 sessions / 90 days).

### Removed
- The OpenAI translation engine has been fully removed from the client (it
  was already disabled server-side; this removes the remaining client-side
  code path).

### Fixed
- Audio device diagnostics now reflect the device and signal actually being
  tested: output test tone, system-audio meter, and microphone meter are
  independent instead of conflated into one indicator. Raw audio activity is
  also distinguished from detected speech, so music/system sounds are no
  longer shown as speech.
- Translated-speech playback catch-up (WSOLA time-compression) is now shared
  between the Gemini and Qwen engines instead of being Qwen-only, so a long
  translated turn on either engine stays closer to the live captions.

### Added
- Meeting mode: an opt-in **"Listen to my translation"** monitor plays the
  outgoing translated speech through the user's own headphones in addition to
  the virtual microphone, so a speaker can verify what the other side hears.
- A language-swap control to exchange the two translation targets in one step.

*Thanks to [Vladimir Vorobyov (@uladzemer)](https://github.com/uladzemer) for
this contribution — [audio diagnostics fix](https://github.com/DavutAkca/voxislive/commit/9ee5e50c637dd8435402248777f8b959ea0c81cb).*

### Fixed
- A crash partway through starting a Video/Game or Meeting session could leak
  the capture device, player, or translator instead of releasing them.
- Engine failover from OpenAI to Gemini now retargets the capture's sample
  rate (16 kHz vs 24 kHz), instead of playing the source 1.5x slow after the
  swap.
- A translated turn with no text yet (only the source line captured) was
  silently dropped from the transcript instead of being kept as source-only.
- Session key/secret storage (`BYOK` keys, the per-install secret, saved
  transcripts) now writes through unique temp files under a lock, closing a
  race where two concurrent writes could clobber each other's staging file.
- `SECURITY.md` now discloses the hash-verified model downloads (speaker
  labeling, local TTS voices) the open-source build performs on first use,
  instead of claiming it makes no outbound calls of its own.
- `LICENSE` was missing several sections of the PolyForm Noncommercial 1.0.0
  text it references (Distribution License, Notices, Changes and New Works
  License, Patent License); restored to the complete, official text.

### Added
- An advanced, opt-in "allow multiple app instances" setting (Windows only,
  off by default) for users who explicitly want more than one Voxis process
  running at once.
- A `Quality` GitHub Actions workflow: the pytest suite and ruff run on every
  push and pull request against `main` (Python 3.11 and 3.13, Windows).

*Thanks to [Vladimir Vorobyov (@uladzemer)](https://github.com/uladzemer) for
this contribution too — [runtime/storage hardening](https://github.com/DavutAkca/voxislive/commit/8cdc51eee8e68726d4c21410fa17332a1ccbf892).*
