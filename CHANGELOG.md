# Changelog

Notable changes to Voxis. Version bumps are tagged in commit messages
(`vX.Y.Z: ...`); this file tracks contributions and fixes as they land.

## Unreleased

### Added
- A free/taste-tier session whose fast translation engine hits a real,
  server-confirmed problem mid-session now gets a backup voice instead of the
  session simply ending — a short notice explains what's happening. The
  backup voice never costs the session's trial minutes; it draws from the
  same daily free-voice allowance every account already has, so it can't run
  indefinitely. The server only grants it while it has real evidence of
  trouble, so a session can't trigger this on its own.

### Fixed
- A translation-engine failure with no substitute engine available could
  surface the raw upstream error text to the user (e.g. a provider's literal
  technical error payload) instead of a clear message. Now shows a plain
  status in all 23 languages; the technical detail still reaches the log.
- A long-running Qwen session carrying a lot of speech could be dropped and
  reconnected even though the connection was healthy: the WebSocket ping/pong
  keepalive (`ping_timeout=10s`) could fire before the app's own stall
  watchdogs did, if DashScope's server was still busy processing a large
  in-flight exchange. Raised to 600s per DashScope's own support-ticket
  guidance — the app's stall/no-output watchdogs already catch a genuinely
  dead connection within ~20s during active streaming (they key off actual
  traffic, not ping/pong), so this only removes the false-positive disconnect
  on healthy, busy sessions.
- A Qwen capacity error ("thread pool exhausted") that used to be retried up
  to 8 times with fast backoff is now recognized as terminal instead of
  generic-transient — it was hammering an already-saturated shared rate limit
  and prolonging the very outage it was reacting to. A terminal error now
  gets one immediate retry on a server-provided sibling connection pool
  before falling back to the alternate engine.
- On VB-CABLE setups, the volume mirror assumed the physical playback device
  sat at 0 dB. If it didn't — the common case — that device's own level
  silently capped the output under whatever the mirror computed: the display
  showed full volume with nothing left to raise while the actual level was
  quieter. Voxis now raises the physical device to full for the session and
  restores it on stop.

### Added
- The language picker now locks out any language a free-tier session cannot
  use, with a link to upgrade, instead of letting you pick it and finding out
  later — mid-session — that it does not work. Paired with a cost-control
  change: a free or taste-tier session no longer falls back to the paid engine
  under any circumstance (an outage included), it only ever uses the primary
  engine or ends the session cleanly. Paid sessions are unaffected — they
  still fail over to the backup engine when needed.
- The top bar now shows which version you're running, and flags it when a
  newer one is available — checked in the background against a small public
  manifest (`voxislive.com/app.json`) that also carries language coverage for
  the website. The check is unauthenticated and sends no user data, so it
  runs on the OSS/BYOK build too, not just the official release.
- Voxis says something when it cannot hear anything. If no sound reaches it in
  the first seconds of a Video session, it now tells you — and names the two
  things that actually cause it: nothing is playing, or you are speaking into
  your microphone, which Video mode does not translate. Until now the app stayed
  completely silent in that state; measurement across every recorded session
  showed 40% of them ended inside 30 seconds, with another attempt following a
  median 14 seconds later, i.e. people were retrying, not losing interest.
- The gap between pressing Start and the first translated word is no longer a
  blank screen: the stream shows that it is connecting, escalates if the
  handshake drags past ten seconds, and sets the expectation that the first
  translation lands a few seconds after someone speaks. The line explaining that
  delay used to appear only with the first caption — after the wait it was meant
  to explain, and never at all for anyone who gave up first.
- Release notes now cover every version you skipped, not just the running one.
  Store updates land in the background and can jump several versions at once,
  which is how 1.0.50's notes reached nobody who went from 1.0.49 to 1.0.51 in a
  single update. The card also links to the full changelog on the website.
- Translated-voice gender, chosen per direction: "Translation voice" (what you
  hear) and "My voice" (what the other person hears you as, in Meeting mode).
  Both live in Settings › Translation — it is set once for a meeting, not
  adjusted per session, so it does not belong on the main screen. Available
  on the 31 targets served by the Qwen engine — measurement showed the Gemini
  translate model ignores voice selection entirely, so on the remaining targets
  the picker says so instead of silently doing nothing. Until now every session
  used one server-default voice, which is female.
- Release notes in the app: after an update you see what changed once, in your
  own UI language, instead of having to find the Microsoft Store listing. A
  fresh install is not shown a changelog — it gets the onboarding tour.
- A ready-made list of ~31 proper nouns ships with the term box, so brand and
  product names are spelled right before anyone types anything. It can be
  switched off, and your own terms always win over a shipped one.

### Changed
- The term box moved out of General into its own Settings › Translation tab and
  is no longer called "Meeting terms": it has always applied to Video mode too.

### Fixed
- A translator session that connected but never produced any output no longer
  looped retrying the same dead connection forever: the retry counter was
  reset by time-alive alone, so a connection that stayed open past 5 seconds
  before dying with zero output kept "proving the path works" and never
  reached the threshold that hands the session to a backup engine. It now
  also requires that the session actually produced output before resetting.
  Paid plans additionally fail over to the backup engine on the very first
  dropped connection instead of riding out several retries.
- A session no longer goes permanently silent when the translation service
  starts rejecting the audio it is sent. Those rejections still count as
  "the engine is hearing us", so both self-heal watchdogs stayed disarmed: the
  session kept its connection, showed as active, produced nothing, and never
  reconnected. One field meeting lost its last 13 minutes that way. Voxis now
  treats a rejected utterance as input and reconnects itself.
- The close button of the translation-history window sits at the top right,
  like every other window, instead of next to the title.
- Meeting mode no longer translates its own outgoing voice back at you. On a PC
  with VB-Cable installed, both directions shared the one cable, so the
  translation Voxis had just sent into the call came back in as if the other
  party had said it — a third, phantom voice in your own language.
- Captions no longer run words together at a sentence boundary
  ("bekleyelim.Bu arada," instead of "bekleyelim. Bu arada,") — it affected
  a quarter of all caption lines on the Qwen engine.
- Repeated caption text is removed: both a whole line re-spoken as the next
  turn, and a clause the engine emits twice inside one line. The translated
  speech only ever said it once.
- A caption line no longer swallows 20+ seconds of speech; past a length or
  time budget it splits at the next sentence end.
- Subtitle exports (SRT/VTT) are wrapped to a readable line width — cues used
  to run off the frame, the longest being a single 548-character line.
- Subtitle timings now start from the session, not from the first translated
  word, so an export lines up with its own audio recording. A session that
  began before anyone spoke shifted every cue.
- Meeting mode keeps its two directions apart. Both translators fed one caption
  line and one transcript, so the other party's words and your own interleaved
  with no way to tell them apart. Each side is now labelled, on screen and in
  the saved transcript.
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
- Settings > **General**: a **Meeting terms** box. Names your meetings use —
  companies, products, people — can be listed one per line so the translator
  spells them correctly instead of guessing.
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
this contribution — [audio diagnostics fix](https://github.com/VoxisLive/voxislive/commit/9ee5e50c637dd8435402248777f8b959ea0c81cb).*

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
this contribution too — [runtime/storage hardening](https://github.com/VoxisLive/voxislive/commit/8cdc51eee8e68726d4c21410fa17332a1ccbf892).*
