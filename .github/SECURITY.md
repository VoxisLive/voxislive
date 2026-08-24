# Security Policy

## Reporting a vulnerability

Please **do not** open a public issue for security problems.

Report privately through GitHub's
[**Report a vulnerability**](https://github.com/VoxisLive/voxislive/security/advisories/new)
form (the repository's **Security → Advisories** tab). We aim to acknowledge a
valid report within a few days and will coordinate a fix and disclosure with you.

When reporting, please include reproduction steps and the affected version.
**Never paste an API key, token, or any other secret** into a report.

## Design notes relevant to security

Voxis Live is a commercial product (official app + a paid Bring Your Own Key
unlock — see [Licensing](https://voxislive.com/licensing)). This repository is
a read-only, source-available excerpt of the desktop engine, published for
transparency — not the buildable app. What it shows about the real pipeline:

- Audio leaves the device only over the encrypted WebSocket session opened
  with the translation provider (`app/base_translator.py`, `app/translator.py`)
  — there is no other network hop, no telemetry, and no background upload in
  this code.
- Optional speaker labeling and local TTS may download hash-verified model
  assets from `k2-fsa/sherpa-onnx` GitHub releases on first use; those
  downloads contain no session audio or transcript data.
- This repository is kept free of secrets and closed-core code by a
  release-hygiene gate (`scripts/check_release_hygiene.py`), enforced in CI and
  a local pre-push hook.

**Legacy BYOK builds** (a source-buildable BYOK app, discontinued August 2026):
API keys were stored **encrypted at rest with Windows DPAPI**
(`CryptProtectData`, `CURRENT_USER` scope) plus a per-install entropy secret,
under `profiles/byok/` — never written to a plaintext `.env`, never leaving the
machine except to open the Gemini Live WebSocket the key authorized. That build
never contacted Voxis services — no telemetry, authentication, or usage
reporting. This paragraph is retained for anyone still running a previously
built copy; it is not describing a currently offered distribution.

## Supported versions

The latest version on the `main` branch receives security fixes.
