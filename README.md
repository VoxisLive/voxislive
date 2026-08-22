# Voxis Live

**[English]** | **[Türkçe](README.tr.md)** | **[Deutsch](README.de.md)**

![GitHub stars](https://img.shields.io/github/stars/VoxisLive/voxislive?style=social)
![License](https://img.shields.io/badge/license-PolyForm%20Strict%201.0.0-blue)

> Real-time voice translation for Windows — translate any video, game, or meeting and hear it in your own language, live.
>
> Brand: **Voxis** · Site: **[voxislive.com](https://voxislive.com)** · Get the app: **[Microsoft Store](https://voxislive.com)**

> [!WARNING]
> **This repository does not provide a way to run Voxis.** It is a curated, read-only excerpt of the engine's audio-handling code, published so anyone can verify how audio is captured, transmitted, and stored — see [Source transparency](#source-transparency) below. **Only trust downloads from [voxislive.com](https://voxislive.com), the Microsoft Store listing, or this repository at `github.com/VoxisLive/voxislive`.** Copies of this repository have been found on other GitHub accounts, some redirecting to installers hosted elsewhere — those are **not official** and may be malicious. If a fork or clone claims you can build and run Voxis from it, that claim is false; report it to [support@voxislive.com](mailto:support@voxislive.com).

---

## Overview

Browser-tab dubbers can only translate audio playing inside one Chrome tab. Voxis reads **Windows system audio directly**, so it works on anything your PC plays — native games, desktop Zoom/Teams/Discord calls, any local video player — not just what's open in a browser tab.

Voxis captures Windows system audio (from videos, games, or calls), streams it to a cloud speech-to-speech translation model, and plays back spoken translation in real time while the speaker is talking — a native **simultaneous interpreter**, not a speech-to-text → translate → text-to-speech chain.

Two operating modes:

- **Video / Game** — one-way incoming translation; the original audio is ducked while the translation speaks.
- **Meeting** — two-way: the other party's voice is translated into your language, and your voice is translated into their language and fed into the call as a virtual microphone.

Every session can be saved and exported as **TXT / SRT / VTT**, and past sessions stay searchable in the in-app History panel.

---

## Source transparency

We don't ask you to take "we don't record your conversations" on faith. This repository publishes a small, **explicitly allowlisted** excerpt of the real Voxis engine — copied verbatim from the shipping source, not rewritten for show — covering exactly the chain your audio moves through:

```
system audio ──► capture ──► local VAD gate ──► translation session ──► player
             (process_loopback.py,     (vad.py,       (base_translator.py,     (audio_io.py,
              session_duck.py,          filters non-    translator.py —          mix_core.py)
              win_audio.py)             speech locally) the ONLY network hop)
```

What these files let you verify:

- **`app/base_translator.py`** is the shared session state machine both of our translation engines use for the network round-trip — connect, send audio, receive translated audio, reconnect on failure. It is the one place audio leaves the device. Read it end to end: there is no second channel, no background upload, no logging of what was said.
- **`app/translator.py`** is a concrete, complete example of that connection (our Gemini integration) — not a stub.
- **`app/vad.py`** shows that silence never reaches the network at all; only detected speech is sent.
- **`app/audio_recorder.py`** shows that local audio recording is opt-in, off by default, and **impossible to enable in Meeting mode** — that check is in the code, not just a setting.
- **`app/transcript_store.py`** shows transcripts are written to your own disk and nowhere else unless you explicitly export or share one.
- **`app/report_scrub.py`** shows exactly what gets redacted (keys, tokens, emails, local usernames) before an optional problem report ever leaves your device.
- **`app/i18n.py`** is the actual on-screen text the app shows about this — including the privacy explainer it displays in-app.

`docs/PRIVACY.md`, `docs/TERMS.md`, and the rest of `docs/` are the plain-language versions of the same claims.

**What isn't here, and why:** the orchestration layer, the UI, our paid translation-engine integrations, quality tuning, and account/billing code are not published. None of it changes how audio is handled — the mechanism above is the same regardless of which engine is active — and publishing it would hand a competitor our tuning and business logic for no transparency benefit. `scripts/check_release_hygiene.py` is the mechanical gate that keeps this boundary from drifting; every file tracked in this repository has to be named explicitly in it.

This repository is licensed under **[PolyForm Strict 1.0.0](LICENSE)**: you can read it and cite it, but it does not grant a right to redistribute it, fork it, or build derivative works from it. See [License](#license--polyform-strict-100).

---

## Architecture (published files)

| Module | What it shows |
| --- | --- |
| `app/process_loopback.py` | Driverless WASAPI loopback capture; excludes Voxis's own audio output so it never re-translates itself |
| `app/session_duck.py`, `app/win_audio.py` | How other applications are ducked and how output endpoints are switched — no audio is copied elsewhere in the process |
| `app/audio_io.py`, `app/mix_core.py` | Device capture, the stereo player, and the look-ahead limiter |
| `app/vad.py` | Local Silero VAD gate — silence is filtered out before anything is sent |
| `app/base_translator.py` | The shared translation-session state machine — the single network egress point |
| `app/translator.py` | A complete, concrete translation-engine connection (Gemini) |
| `app/audio_recorder.py` | Optional local dual-track recording — opt-in, Video/Game mode only |
| `app/transcript_store.py` | Local-only transcript persistence and TXT/SRT/VTT export |
| `app/report_scrub.py` | Client-side redaction applied before an optional problem report is sent |
| `app/i18n.py` | The actual in-app status and privacy-explainer text |
| `app/paths.py` | Where local data (transcripts, models) actually lives on disk |

A handful of `tests/` files exercise these modules directly (`test_mix_core.py`, `test_ring.py`, `test_player_volume.py`, `test_audio_test_tone.py`, `test_speech_gate.py`, `test_session_duck.py`, `test_report_scrub.py`, `test_transcript_export.py`, `test_audio_recorder.py`) and run in CI on every push — see the badge-worthy [Quality workflow](.github/workflows/quality.yml). They're included for reading and as a second, executable form of the same claims, not as an invitation to build the full application from this tree.

---

## Meeting mode setup (two-way translation)

This section is for people using the installed app, not for building from source.

**Goal:** you speak Turkish → the other side hears English; the other side speaks English → you hear Turkish.

| Direction | What it does | Requirement |
| --- | --- | --- |
| **Incoming** (you hear them in your language) | Listens to system audio, translates, plays to your headphones | No extra install |
| **Outgoing** (your voice goes out translated) | Translates your mic, feeds a virtual microphone | A virtual microphone (VB-CABLE) is required |

On Windows the only way to present a "microphone" that a meeting app (Teams/Zoom/Meet) can select is a virtual audio driver, so the outgoing direction needs one. Without it, meetings run in **listen-only** mode automatically.

1. Install a free virtual cable, e.g. [VB-CABLE](https://vb-audio.com/Cable/) — run its installer as administrator, reboot.
2. In Voxis, set **Output device** to your real headphones and **Microphone** to the one you actually speak into. The installed virtual cable is auto-detected; no manual routing is needed.
3. In your meeting app, set its **microphone** to the cable's *recording* device (e.g. "CABLE Output") — that is where Voxis writes your translated voice.
4. Start Voxis → **Meeting** mode. Speak your language → it goes out translated; they speak theirs → you hear it translated.

---

## Latency & simultaneous translation

The end-to-end delay is roughly the sentence length plus a few seconds — that lag is the translation model's designed *ear-voice span* (it waits for enough context to translate correctly, the way a human simultaneous interpreter does), not a client-side setting. There is no "go faster" toggle; a shorter buffer would trade accuracy for speed, not remove the lag.

---

## Troubleshooting

| Symptom | Cause | Fix |
| --- | --- | --- |
| Meeting is listen-only | No virtual microphone installed | Install a virtual cable (see above) |
| No translation output is heard | Output device set to a virtual cable | Point the output device at your real headphones |
| `PaError -9999` | Stale Windows audio device list | Unplug/replug the audio device, restart Voxis |

For anything else, use in-app **Report a problem** (see `app/report_scrub.py` for exactly what it redacts before sending) or open a [GitHub Issue](https://github.com/VoxisLive/voxislive/issues).

---

## License — PolyForm Strict 1.0.0

This repository is licensed under the **[PolyForm Strict License 1.0.0](LICENSE)**.

- ✅ You may read it, cite it, and use it for personal, noncommercial reference.
- ❌ It does **not** grant a right to distribute copies, create a fork, or build a derivative work from it — including a modified or "libre" build of Voxis itself.

**Commercial licensing, or any use beyond reading this excerpt** (commercial products, SaaS, white-label): **<https://voxislive.com/licensing>**.

We do not accept code contributions to this repository (see [`.github/CONTRIBUTING.md`](.github/CONTRIBUTING.md)) — there is no derivative-work right to grant one under, and this isn't the product's real source tree.

---

## Support

- **Issues / bug reports about the app:** [GitHub Issues](https://github.com/VoxisLive/voxislive/issues)
- **Security:** [`.github/SECURITY.md`](.github/SECURITY.md)
- **Commercial inquiries:** <https://voxislive.com/licensing>
- **Privacy policy:** [`docs/PRIVACY.md`](docs/PRIVACY.md)

*Voxis Live — real-time, simultaneous voice translation.*
