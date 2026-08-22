# VOXIS LIVE — MEETING & LIVE AUDIO CONSENT NOTICE

**Last Updated:** July 31, 2026

This **Meeting & Live Audio Consent Notice** ("Notice") outlines the legal requirements, user responsibilities, and privacy safeguards when using **Meeting Mode** or processing third-party audio streams within **Voxis Live** (desktop application and browser extensions).

---

## 1. Legal Requirements for Live Audio Translation

When you use Voxis in **Meeting Mode** or capture audio from live video calls (e.g., Zoom, Microsoft Teams, Google Meet, Discord, Webex):
1. **Live Audio Interception & Transmission:** The application captures live incoming audio and local microphone input and streams it over an encrypted WebSocket connection to third-party AI translation providers (**Google Gemini Live API** or **Alibaba Cloud Qwen Realtime API**).
2. **Wiretapping & Eavesdropping Regulations:** Under laws in multiple jurisdictions (including U.S. federal and state laws such as California, Florida, Illinois, Pennsylvania, as well as the EU ePrivacy Directive and GDPR), accessing, processing, or transmitting the oral communications of individuals without their explicit knowledge or consent may constitute unlawful wiretapping or eavesdropping.

---

## 2. Your Mandatory Legal Obligation

**YOU ARE LEGALLY REQUIRED TO INFORM ALL CALL PARTICIPANTS AND OBTAIN THEIR CONSENT PRIOR TO INITIATING REAL-TIME AI TRANSLATION.**

Voxis provides built-in informational popups prior to launching Meeting Mode. However, these in-app notices do **NOT** automatically notify third-party call participants. You maintain sole legal responsibility for providing adequate disclosure.

---

## 3. Sample Recommended Disclosure Scripts

To ensure full compliance, we recommend providing a brief notification to all call participants before activating Voxis Meeting Mode:

### Verbal Disclosure (Before Starting Meeting Mode):
> *"Please note: I am using Voxis Live, a real-time AI translation assistant, to translate our conversation live between [Language A] and [Language B]. Audio is processed transiently for translation and is not recorded or stored. If anyone has objections, please let me know."*

### Written In-Chat Disclosure (For Zoom / Teams / Meet Chat):
> *"Notice: This meeting is being translated in real time using Voxis AI Translation. Audio is processed solely for live translation and is not recorded or saved."*

---

## 4. Built-in Privacy Safeguards in Voxis

Voxis implements strict code-level safeguards to protect call participants:
1. **Permanent Recording Lockout:** In Meeting Mode, audio recording is **hardcoded to be disabled** (`audio_recorder.py`). The application will never save live WAV audio of call participants to disk.
2. **Transient In-Memory Processing:** Audio chunks pass through volatile RAM only during active translation and are never stored on Voxis or third-party servers.
3. **Local Speaker Diarization:** Speaker voice tagging (S1 / S2) is computed 100% locally on your computer CPU (`sherpa-onnx`). No biometric voice embeddings are uploaded.

---

## 5. Limitation of Liability

Voxis Live disclaims all liability for any civil claims, administrative fines, or legal penalties resulting from a user's failure to obtain proper consent from meeting participants. By using Meeting Mode, you agree to indemnify and hold Voxis Live harmless against any related third-party claims.
