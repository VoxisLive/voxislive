# VOXIS LIVE — PRIVACY POLICY

**Last Updated:** July 31, 2026

At **Voxis Live** ("Voxis", "we", "us", or "our"), accessible from [voxislive.com](https://voxislive.com), we respect your privacy and are committed to protecting personal data. This Privacy Policy explains how we collect, use, process, and protect your information across the Voxis desktop application, browser extensions (Chrome, Edge, Chromium), and our web services, in compliance with the General Data Protection Regulation (GDPR), the California Consumer Privacy Act (CCPA), the Turkish Law on Protection of Personal Data (KVKK No. 6698), and applicable international privacy laws.

---

## 1. Information We Process & Data Flow Architecture

Voxis is built with a **privacy-first, local-processing architecture**. The table below summarizes how your data is handled:

### 1.1 Live Audio Streams (System Audio & Microphone)
- **Processing:** Audio captured from your system output (Video/Game Mode) or local microphone (Meeting Mode) is processed in real time for AI speech-to-speech translation.
- **Transmission:** Audio chunks are encrypted in transit (`wss://`) and transmitted transiently to our designated third-party AI translation providers (**Google Gemini Live API** and **Alibaba Cloud Qwen Realtime API**).
- **Storage:** Audio streams pass through RAM only. Voxis **does not store** your audio on any server. Audio is saved to your local disk only if you explicitly enable the optional "Record Audio" setting. In **Meeting Mode**, audio recording is **permanently disabled by code** to prevent non-consensual recording of third-party call participants.

### 1.2 On-Device (Local Only) Data
- **Speaker Identification (S1 / S2 Tagging):** Speaker voice embedding analysis is performed 100% locally on your computer CPU using an embedded `sherpa-onnx` neural model. No biometric data or voiceprints ever leave your device.
- **Voice Activity Detection (VAD):** Noise/silence filtering (`Silero VAD`) runs locally on your CPU.
- **API Key Storage (BYOK Build):** If you provide your own Gemini or Qwen API key, it is encrypted at rest using **Windows Data Protection API (DPAPI)** (`CryptProtectData`), tied exclusively to your Windows user identity.
- **Transcripts & Subtitles:** Saved transcripts (TXT, SRT, VTT, JSON) remain 100% stored on your local hard drive (`%APPDATA%/Voxis/transcripts`).

### 1.3 SaaS Account & Technical Data (Official Release Build Only)
If you use the official SaaS / Microsoft Store release, we collect minimal data required for account management and abuse prevention:
- **Account Credentials:** Email address, hashed password, or Google OAuth token.
- **Usage Minutes:** Aggregated minutes of translation used per session (for subscription quota enforcement).
- **Device Hash:** A one-way, non-reversible cryptographic hash derived from your machine GUID used strictly to prevent free trial abuse across multiple accounts.
- **Technical Problem Reports (Optional):** If you manually submit a problem report, a technical snapshot (app version, Windows OS version, audio mode, error logs) is transmitted. Sensitive data (passwords, API keys, login tokens, Windows usernames) are **automatically stripped out** before sending.

### 1.4 Developer / BYOK Build (Open Source)
The open-source BYOK build communicates **only** with Google Gemini or Alibaba Qwen API servers using your own key. It sends zero telemetry, zero usage minutes, and zero account data to Voxis servers.

---

## 2. Legal Bases for Processing (GDPR / KVKK)

We process your data under the following legal bases:
1. **Performance of a Contract (GDPR Art. 6(1)(b)):** To deliver real-time speech translation and manage your subscription account.
2. **Legitimate Interests (GDPR Art. 6(1)(f)):** To enforce free trial limits, maintain service security, and prevent fraudulent multi-account creation.
3. **Explicit Consent (GDPR Art. 6(1)(a) & Art. 9(2)(a)):** For optional technical problem report submissions and optional local audio recording.

---

## 3. Third-Party Sub-Processors & Data Sharing

Voxis does not sell, rent, or trade your personal data. We share data only with trusted sub-processors strictly necessary for service delivery:

| Sub-Processor | Purpose | Data Received | Privacy Terms |
| :--- | :--- | :--- | :--- |
| **Google Cloud / AI Studio** | Live Speech Translation Engine | Encrypted PCM Audio Stream | [Google AI Privacy Policy](https://policies.google.com/privacy) |
| **Alibaba Cloud / DashScope (Qwen)** | Realtime Speech Translation Engine | Encrypted PCM Audio Stream | [Alibaba Cloud Privacy Policy](https://www.alibabacloud.com/help/faq-detail/42425.htm) |
| **PocketBase (Self-Hosted)** | SaaS Account & Subscription Backend | Email, Hashed Password, Usage Minutes, Device Hash | Encrypted at rest on secure cloud servers |

---

## 4. Browser Extensions (Chrome / Edge / Chromium)

If you use the Voxis Browser Extension:
- **Permissions:** The extension uses `tabCapture` to capture audio from the active tab for translation overlays and `storage` to save user preferences.
- **Privacy Assurance:** Extension audio capture occurs exclusively in memory while translation is active. Extension data is never sold, monitored for advertising, or shared with third parties beyond the translation API.

---

## 5. Data Retention & User Rights

- **Local Data:** You have full control to view, export, or delete your local transcripts, encrypted API keys, and audio recordings at any time by clearing your application data or opening the transcript folder.
- **Account Data:** You may request the deletion of your SaaS account and associated usage logs at any time by contacting [support@voxislive.com](mailto:support@voxislive.com).

### Your Rights under GDPR, CCPA, and KVKK:
- **Access:** Request a copy of the personal data we hold about you.
- **Rectification:** Request correction of inaccurate account data.
- **Erasure ("Right to be Forgotten"):** Request permanent deletion of your account.
- **Data Portability:** Export your transcript history in standard formats (TXT, SRT, VTT, JSON).

---

## 6. Security Measures

We implement robust security measures to protect your information:
- End-to-end TLS/SSL encryption (`wss://`, `https://`) for all network transmissions.
- Hardware-backed Windows DPAPI encryption for stored API keys.
- Automatic redaction of credentials and PII in error reporting logs.

---

## 7. Changes to This Privacy Policy

We may update our Privacy Policy periodically. We will notify you of any material changes by posting the new Privacy Policy on [voxislive.com](https://voxislive.com) and updating the "Last Updated" date.

---

## 8. Contact Us & Data Protection Officer

For any privacy-related inquiries, rights requests, or feedback, please contact us:
- **Email:** [support@voxislive.com](mailto:support@voxislive.com)
- **Website:** [https://voxislive.com](https://voxislive.com)
