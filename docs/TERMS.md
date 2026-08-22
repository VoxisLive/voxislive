# VOXIS LIVE — TERMS OF SERVICE

**Last Updated:** August 22, 2026

Welcome to **Voxis Live** ("Voxis", "Application", "Service", "we", "us", or "our"). Please read these Terms of Service ("Terms") carefully before using the Voxis desktop application, browser extensions (including Chrome, Edge, and Chromium-based extensions), the website located at [voxislive.com](https://voxislive.com), or any related software, APIs, or documentation.

By downloading, installing, accessing, or using Voxis Live (via desktop app, browser extension, or web services), you ("User" or "you") agree to be bound by these Terms. If you do not agree to all of these Terms, do not install, access, or use the Application or Extensions.

---

## 1. Description of Service

Voxis Live is a real-time speech-to-speech AI translation software ecosystem provided across desktop software and browser extension platforms:
- **Desktop Application (Windows):** Captures system audio output (Video/Game Mode) or local microphone audio (Meeting Mode) and processes it via third-party artificial intelligence models (such as **Google Gemini Live API** and **Alibaba Cloud Qwen Realtime API**) to generate live translated speech and real-time subtitles.
- **Browser Extension (Chrome / Edge / Chromium):** Captures tab audio and in-browser streams to provide real-time translation overlays, subtitles, and audio dubbing within web browsers.

Voxis is distributed as an **Official Release / SaaS Build**: via official stores (Microsoft Store, Chrome Web Store, Edge Add-ons) or official installer, operating with integrated server-managed authentication, minute subscriptions, and automated routing across Google Gemini and Alibaba Qwen infrastructure.

A limited, explicitly curated excerpt of the underlying source code is separately published at github.com/VoxisLive/voxislive for transparency and audit purposes, under its own license (PolyForm Strict 1.0.0) — it is not a distribution mode of the Service, and these Terms do not apply to reading it.

Prior to August 2026, Voxis also offered a source-buildable **Developer / Bring Your Own Key (BYOK) Build**, where translation requests executed using the User's own API key directly between the User's device and the third-party AI provider. That distribution channel has been discontinued and is no longer offered. Section 4.2 continues to govern any previously obtained BYOK build still in use.

---

## 2. Artificial Intelligence Disclaimer & Accuracy Warning

### 2.1 AI-Generated Output
You acknowledge and agree that translations, synthetic voices, captions, and transcriptions produced by Voxis are generated dynamically using artificial intelligence models ("AI Output").

### 2.2 No Guarantee of Accuracy
**AI Output may contain errors, omissions, misinterpretations, or "hallucinations." Voxis makes no warranty or representation regarding the accuracy, completeness, reliability, or timeliness of any translation.** Voxis must **NOT** be relied upon for emergency services, medical diagnosis, legal proceedings, high-risk financial transactions, safety-critical navigation, or any situation where inaccurate translation could lead to personal injury, financial loss, or legal liability.

---

## 3. User Warranties & Live Audio Consent Obligations

### 3.1 Compliance with Eavesdropping & Wiretapping Laws
In many jurisdictions (including various U.S. states such as California, Florida, and Illinois, as well as Member States of the European Union), it is illegal to record, intercept, or transmit the live oral communications of another person without their prior consent (often referred to as "all-party consent" or "two-party consent" laws).

### 3.2 User Warranties & Representations
When using Voxis in **Meeting Mode** or whenever capturing, translating, or processing third-party audio, **YOU EXPRESSLY WARRANT AND REPRESENT THAT:**
1. You have obtained all required consents, permissions, and authorizations from all participants in the audio stream or call prior to initiating real-time AI translation.
2. You will comply with all applicable local, state, national, and international privacy, wiretapping, surveillance, and data protection laws (including GDPR and CCPA).
3. You will not use Voxis for unauthorized surveillance, wiretapping, secret recording, or unlawful monitoring of any individual or entity.

### 3.3 Obligation to Inform
Voxis provides built-in notices regarding Meeting Mode consent. You acknowledge that these UI notices do not relieve you of your legal duty to explicitly inform and obtain consent from all call participants.

---

## 4. Third-Party Services & API Usage

### 4.1 Google Gemini & Alibaba Qwen AI Service Providers
Voxis relies on third-party AI services, including but not limited to **Google Gemini Live API** (`gemini-3.5-live-translate-preview`) and **Alibaba Cloud Qwen Realtime API** (`qwen3.5-livetranslate-flash-realtime`). Audio data sent for translation is governed by the respective terms and privacy policies of those providers (e.g., [Google Terms of Service](https://policies.google.com/terms), [Google AI Studio Terms](https://ai.google.dev/terms), and [Alibaba Cloud International Privacy Policy](https://www.alibabacloud.com/help/faq-detail/42425.htm)).

### 4.2 Legacy BYOK Key Management & Liability
The Developer / BYOK Build is discontinued and no longer distributed (see Section 1). If you obtained a BYOK build prior to its discontinuation and continue to use it:
- You are solely responsible for obtaining, maintaining, and securing your own API keys.
- API keys are encrypted locally on your Windows device using Windows Data Protection API (DPAPI) or local browser extension storage.
- You are solely responsible for any costs, API quotas, or violations of third-party API terms incurred under your key.

---

## 5. Acceptable Use & Prohibited Activities

You agree **NOT** to use Voxis to:
1. Intercept or translate communications without proper legal authorization or consent.
2. Infringe upon the intellectual property, privacy, or publicity rights of third parties.
3. Transmit audio containing hate speech, illegal material, harassment, or content violating third-party platform terms (e.g., Zoom, Teams, Discord).
4. Reverse engineer, decompile, or tamper with the security or license-verification mechanisms of the official SaaS build or browser extension.
5. Circumvent, manipulate, or exploit usage limits, billing counters, device hashes, or access restrictions.

---

## 6. Account Suspension, Banning & Termination Rights

### 6.1 Right to Block, Suspend, or Terminate Access
**Voxis Live reserves the absolute, unilateral right to suspend, restrict, block, or permanently terminate your account, API access, device access (`device_hash`), or IP address at any time, with or without prior notice, at our sole discretion.** Reasons for suspension or termination include, but are not limited to:
- Violation of any provision of these Terms or EULA;
- Fraudulent, abusive, or unauthorized use of the Application, API endpoints, or subscription minutes;
- Attempts to reverse engineer, hack, or bypass billing controls;
- Unlawful wiretapping or non-consensual interception of live audio;
- Requests by law enforcement or government agencies.

### 6.2 Effect of Termination & Subscription Cancellation
Upon termination or blocking of your account due to a violation of these Terms:
1. Your license to use the Software and SaaS services is immediately revoked.
2. Any remaining subscription minutes, minute packages, or unused paid credits shall be **forfeited immediately without any right to refund or compensation**.
3. Voxis shall not be liable to you or any third party for any termination of your access to the Application.

### 6.3 Voluntary User Cancellation
You may cancel your SaaS subscription or delete your account at any time through your account settings or Microsoft Store subscription portal. Cancellation will take effect at the end of the current billing cycle.

---

## 7. Intellectual Property & License Rights

- **Application Code & Assets:** The Voxis Live codebase, Official SaaS release assets, pre-compiled binaries, logos, branding ("Powered by Voxis"), and proprietary server infrastructures are and remain the exclusive property of Voxis Live. A limited, separately-licensed excerpt is published at github.com/VoxisLive/voxislive for transparency purposes only (see Section 1); no other part of the codebase is licensed for public use.
- **User Transcripts & Generated Files:** You retain full ownership of all text transcripts (TXT, SRT, VTT, JSON) and local WAV audio recordings generated by your use of the Software.

---

## 8. Limitation of Liability & Indemnification

### 8.1 Disclaimer of Warranties
**TO THE MAXIMUM EXTENT PERMITTED BY APPLICABLE LAW, VOXIS LIVE IS PROVIDED ON AN "AS IS" AND "AS AVAILABLE" BASIS, WITHOUT WARRANTIES OF ANY KIND, EXPRESS OR IMPLIED, INCLUDING BUT NOT LIMITED TO IMPLIED WARRANTIES OF MERCHANTABILITY, FITNESS FOR A PARTICULAR PURPOSE, OR NON-INFRINGEMENT.**

### 8.2 Limitation of Liability
**IN NO EVENT SHALL VOXIS LIVE, ITS DEVELOPERS, AFFILIATES, OFFICERS, OR SUPPLIERS BE LIABLE FOR ANY INDIRECT, INCIDENTAL, SPECIAL, CONSEQUENTIAL, OR PUNITIVE DAMAGES (INCLUDING LOSS OF PROFITS, DATA LOSS, BUSINESS INTERRUPTION, OR THIRD-PARTY FINES) ARISING OUT OF OR IN CONNECTION WITH YOUR USE OF OR INABILITY TO USE THE APPLICATION OR BROWSER EXTENSIONS.**

### 8.3 User Indemnification (Tazminat Yükümlülüğü)
**YOU AGREE TO INDEMNIFY, DEFEND, AND HOLD HARMLESS VOXIS LIVE, ITS DEVELOPERS, AND AFFILIATES FROM AND AGAINST ANY AND ALL CLAIMS, LIABILITIES, LOSSES, DAMAGES, FINES, EXPENSES, OR DEMANDS (INCLUDING REASONABLE ATTORNEYS' FEES) ARISING OUT OF OR RELATED TO:**
1. Your violation of these Terms;
2. Your failure to obtain required consent from call participants before capturing or translating their audio;
3. Your violation of any applicable wiretapping, privacy, or data protection law.

---

## 9. Modifications to Terms & Service

We reserve the right to modify these Terms at any time. Updated Terms will be posted on [voxislive.com](https://voxislive.com) and noted in application release notes. Your continued use of Voxis following the posting of updated Terms constitutes acceptance of those changes.

---

## 10. Contact Information

If you have any questions regarding these Terms, please contact us at:
- **Email:** [support@voxislive.com](mailto:support@voxislive.com)
- **Website:** [https://voxislive.com](https://voxislive.com)
