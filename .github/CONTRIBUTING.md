# About this repository

This repository is **not the Voxis product source** and it does not accept
code contributions or pull requests.

It publishes a small, explicitly allowlisted excerpt of the real Voxis
engine — the audio capture → translate → playback → local-storage chain —
so that anyone can read exactly how audio is handled, without us asking you
to take our word for it. It is licensed under **PolyForm Strict 1.0.0**
(see [LICENSE](../LICENSE)), which permits reading and personal/noncommercial
reference use but not distribution, forks, or derivative works — so there is
no contribution flow to describe here.

If you found something worth flagging:

- **A bug in the Voxis app itself** (the Microsoft Store release): open an
  [Issue](https://github.com/VoxisLive/voxislive/issues) with steps to
  reproduce, or use in-app **Report a problem**.
- **A security concern**: see [SECURITY.md](SECURITY.md).
- **A discrepancy between this repository and what the app actually does**:
  that is exactly the kind of report we want — please open an Issue. The
  allowlist in `scripts/check_release_hygiene.py` and this file set are kept
  in sync with the shipping engine deliberately; if you can show they've
  drifted, that's a bug in our process.
