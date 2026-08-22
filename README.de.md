# Voxis Live

**[English](README.md)** | **[Türkçe](README.tr.md)** | **Deutsch**

![GitHub stars](https://img.shields.io/github/stars/VoxisLive/voxislive?style=social)
![License](https://img.shields.io/badge/license-PolyForm%20Strict%201.0.0-blue)

> Echtzeit-Sprachübersetzung für Windows — übersetzen Sie jedes Video, Spiel oder Meeting live und hören Sie es in Ihrer eigenen Sprache.
>
> Marke: **Voxis** · Website: **[voxislive.com](https://voxislive.com)** · App herunterladen: **[Microsoft Store](https://voxislive.com)**

> [!WARNING]
> **Dieses Repository bietet keine Möglichkeit, Voxis auszuführen.** Es ist ein kuratierter, schreibgeschützter Ausschnitt des audio-verarbeitenden Codes der Engine, veröffentlicht, damit jeder überprüfen kann, wie Audio erfasst, übertragen und gespeichert wird — siehe [Quelltransparenz](#quelltransparenz) unten. **Vertrauen Sie nur Downloads von [voxislive.com](https://voxislive.com), dem Microsoft-Store-Eintrag oder diesem Repository unter `github.com/VoxisLive/voxislive`.** Kopien dieses Repositories wurden auf anderen GitHub-Konten gefunden, einige leiten zu anderswo gehosteten Installern weiter — diese sind **nicht offiziell** und können bösartig sein. Wenn ein Fork oder Klon behauptet, Sie könnten Voxis daraus bauen und ausführen, ist das falsch; melden Sie es an [support@voxislive.com](mailto:support@voxislive.com).

---

## Überblick

Browser-Tab-Dubber können nur Audio übersetzen, das in einem Chrome-Tab läuft. Voxis liest **Windows-Systemaudio direkt**, funktioniert also bei allem, was Ihr PC wiedergibt — native Spiele, Desktop-Zoom/Teams/Discord-Anrufe, jeder lokale Videoplayer — nicht nur bei dem, was in einem Browser-Tab geöffnet ist.

Voxis erfasst Windows-Systemaudio (aus Videos, Spielen oder Anrufen), streamt es an ein cloudbasiertes Sprache-zu-Sprache-Übersetzungsmodell und spielt die gesprochene Übersetzung in Echtzeit ab, während die Person spricht — ein nativer **Simultandolmetscher**, keine Kette aus Spracherkennung → Übersetzung → Sprachsynthese.

Zwei Betriebsmodi:

- **Video / Spiel** — einseitige eingehende Übersetzung; das Originalaudio wird gedämpft, während die Übersetzung spricht.
- **Meeting** — zweiseitig: die Stimme der anderen Person wird in Ihre Sprache übersetzt, Ihre Stimme wird in ihre Sprache übersetzt und als virtuelles Mikrofon in den Anruf eingespeist.

Jede Sitzung kann gespeichert und als **TXT / SRT / VTT** exportiert werden; vergangene Sitzungen bleiben im In-App-Verlaufsbereich durchsuchbar.

---

## Quelltransparenz

Wir bitten Sie nicht, uns beim Wort zu nehmen, dass wir Ihre Gespräche nicht aufzeichnen. Dieses Repository veröffentlicht einen kleinen, **explizit zugelassenen** Ausschnitt der echten Voxis-Engine — wortgetreu aus dem ausgelieferten Quellcode kopiert, nicht zur Show umgeschrieben — genau die Kette, durch die Ihr Audio läuft:

```
Systemaudio ──► Erfassung ──► lokales VAD-Gate ──► Übersetzungssitzung ──► Player
            (process_loopback.py,     (vad.py,        (base_translator.py,      (audio_io.py,
             session_duck.py,          filtert lokal    translator.py — der       mix_core.py)
             win_audio.py)             Nicht-Sprache)   EINZIGE Netzwerk-Hop)
```

Was diese Dateien Ihnen zu überprüfen erlauben:

- **`app/base_translator.py`** ist die gemeinsame Sitzungs-Zustandsmaschine, die beide unserer Übersetzungs-Engines für den Netzwerk-Roundtrip verwenden — verbinden, Audio senden, übersetztes Audio empfangen, bei Fehlern neu verbinden. Es ist die einzige Stelle, an der Audio das Gerät verlässt. Lesen Sie sie vollständig: es gibt keinen zweiten Kanal, keinen Hintergrund-Upload, keine Protokollierung des Gesagten.
- **`app/translator.py`** ist ein konkretes, vollständiges Beispiel dieser Verbindung (unsere Gemini-Integration) — kein Platzhalter.
- **`app/vad.py`** zeigt, dass Stille niemals das Netzwerk erreicht; nur erkannte Sprache wird gesendet.
- **`app/audio_recorder.py`** zeigt, dass lokale Audioaufzeichnung opt-in, standardmäßig deaktiviert und **im Meeting-Modus unmöglich zu aktivieren** ist — diese Prüfung steht im Code, nicht nur in einer Einstellung.
- **`app/transcript_store.py`** zeigt, dass Transkripte nur auf Ihre eigene Festplatte geschrieben werden, es sei denn, Sie exportieren oder teilen eines ausdrücklich.
- **`app/report_scrub.py`** zeigt genau, was (Schlüssel, Tokens, E-Mails, lokale Benutzernamen) entfernt wird, bevor ein optionaler Problembericht Ihr Gerät verlässt.
- **`app/i18n.py`** ist der tatsächliche Text, den die App dazu auf dem Bildschirm zeigt — einschließlich der In-App-Datenschutzerklärung.

`docs/PRIVACY.md`, `docs/TERMS.md` und der Rest von `docs/` sind die allgemeinverständlichen Versionen derselben Aussagen.

**Was hier nicht enthalten ist, und warum:** die Orchestrierungsschicht, die Benutzeroberfläche, unsere kostenpflichtigen Übersetzungs-Engine-Integrationen, Qualitätsoptimierungen und Konto-/Abrechnungscode werden nicht veröffentlicht. Nichts davon ändert, wie Audio behandelt wird — der obige Mechanismus ist derselbe, egal welche Engine aktiv ist — und die Veröffentlichung würde einem Wettbewerber ohne Transparenzgewinn unsere Feinabstimmung und Geschäftslogik liefern. `scripts/check_release_hygiene.py` ist das mechanische Gate, das verhindert, dass diese Grenze verwässert wird; jede in diesem Repository getrackte Datei muss dort explizit benannt sein.

Dieses Repository ist unter **[PolyForm Strict 1.0.0](LICENSE)** lizenziert: Sie können es lesen und zitieren, aber es gewährt kein Recht, es weiterzuverbreiten, zu forken oder abgeleitete Werke daraus zu erstellen. Siehe [Lizenz](#lizenz--polyform-strict-100).

---

## Architektur (veröffentlichte Dateien)

| Modul | Was es zeigt |
| --- | --- |
| `app/process_loopback.py` | Treiberlose WASAPI-Loopback-Erfassung; schließt Voxis' eigene Audioausgabe aus, damit es sich niemals selbst neu übersetzt |
| `app/session_duck.py`, `app/win_audio.py` | Wie andere Anwendungen gedämpft und Ausgabe-Endpunkte umgeschaltet werden — kein Audio wird im Prozess anderswohin kopiert |
| `app/audio_io.py`, `app/mix_core.py` | Geräteerfassung, der Stereo-Player und der Look-ahead-Limiter |
| `app/vad.py` | Lokales Silero-VAD-Gate — Stille wird herausgefiltert, bevor etwas gesendet wird |
| `app/base_translator.py` | Die gemeinsame Übersetzungssitzungs-Zustandsmaschine — der einzige Netzwerk-Ausgangspunkt |
| `app/translator.py` | Eine vollständige, konkrete Übersetzungs-Engine-Verbindung (Gemini) |
| `app/audio_recorder.py` | Optionale lokale Zwei-Spur-Aufnahme — opt-in, nur Video/Spiel-Modus |
| `app/transcript_store.py` | Rein lokale Transkript-Persistenz und TXT/SRT/VTT-Export |
| `app/report_scrub.py` | Client-seitige Schwärzung, angewendet vor dem Senden eines optionalen Problemberichts |
| `app/i18n.py` | Der tatsächliche In-App-Status- und Datenschutz-Erklärungstext |
| `app/paths.py` | Wo lokale Daten (Transkripte, Modelle) tatsächlich auf der Festplatte liegen |

Einige Dateien unter `tests/` prüfen diese Module direkt (`test_mix_core.py`, `test_ring.py`, `test_player_volume.py`, `test_audio_test_tone.py`, `test_speech_gate.py`, `test_session_duck.py`, `test_report_scrub.py`, `test_transcript_export.py`, `test_audio_recorder.py`) und laufen bei jedem Push in der CI — siehe der [Quality-Workflow](.github/workflows/quality.yml). Sie sind zum Lesen und als zweite, ausführbare Form derselben Aussagen enthalten, nicht als Einladung, die vollständige Anwendung aus diesem Baum zu bauen.

---

## Meeting-Modus einrichten (Zwei-Wege-Übersetzung)

Dieser Abschnitt richtet sich an Nutzer der installierten App, nicht ans Bauen aus dem Quellcode.

**Ziel:** Sie sprechen Türkisch → die andere Seite hört Englisch; die andere Seite spricht Englisch → Sie hören Türkisch.

| Richtung | Was sie tut | Voraussetzung |
| --- | --- | --- |
| **Eingehend** (Sie hören die andere Person in Ihrer Sprache) | Hört Systemaudio ab, übersetzt, spielt in Ihren Kopfhörern ab | Keine zusätzliche Installation |
| **Ausgehend** (Ihre Stimme geht übersetzt hinaus) | Übersetzt Ihr Mikrofon, speist ein virtuelles Mikrofon | Ein virtuelles Mikrofon (VB-CABLE) ist erforderlich |

Unter Windows ist die einzige Möglichkeit, ein "Mikrofon" bereitzustellen, das eine Meeting-App (Teams/Zoom/Meet) auswählen kann, ein virtueller Audiotreiber — daher braucht die ausgehende Richtung einen solchen. Ohne ihn läuft ein Meeting automatisch im **Nur-Zuhören**-Modus.

1. Installieren Sie ein kostenloses virtuelles Kabel, z. B. [VB-CABLE](https://vb-audio.com/Cable/) — Installer als Administrator ausführen, neu starten.
2. Stellen Sie in Voxis das **Ausgabegerät** auf Ihre echten Kopfhörer und das **Mikrofon** auf das Gerät, in das Sie tatsächlich sprechen. Das installierte virtuelle Kabel wird automatisch erkannt; kein manuelles Routing nötig.
3. Stellen Sie in Ihrer Meeting-App das **Mikrofon** auf das Aufnahmegerät des Kabels (z. B. "CABLE Output") — dorthin schreibt Voxis Ihre übersetzte Stimme.
4. Starten Sie Voxis → **Meeting**-Modus. Sprechen Sie Ihre Sprache → sie geht übersetzt hinaus; die andere Seite spricht ihre Sprache → Sie hören sie übersetzt.

---

## Latenz und Simultanübersetzung

Die End-to-End-Verzögerung beträgt grob die Satzlänge plus ein paar Sekunden — diese Verzögerung ist die vom Übersetzungsmodell vorgesehene *Ohr-Stimme-Spanne* (es wartet auf genug Kontext, um korrekt zu übersetzen, so wie ein menschlicher Simultandolmetscher), keine clientseitige Einstellung. Es gibt keinen "schneller"-Schalter; ein kürzerer Puffer würde die Verzögerung nicht entfernen, sondern Genauigkeit gegen Geschwindigkeit eintauschen.

---

## Fehlerbehebung

| Symptom | Ursache | Lösung |
| --- | --- | --- |
| Meeting ist nur im Zuhör-Modus | Kein virtuelles Mikrofon installiert | Virtuelles Kabel installieren (siehe oben) |
| Keine Übersetzungsausgabe zu hören | Ausgabegerät auf ein virtuelles Kabel gesetzt | Ausgabegerät auf Ihre echten Kopfhörer setzen |
| `PaError -9999` | Veraltete Windows-Audiogeräteliste | Audiogerät aus- und wieder einstecken, Voxis neu starten |

Für alles andere nutzen Sie **Problem melden** in der App (siehe `app/report_scrub.py` für die genaue Schwärzung vor dem Versand) oder eröffnen Sie ein [GitHub Issue](https://github.com/VoxisLive/voxislive/issues).

---

## Lizenz — PolyForm Strict 1.0.0

Dieses Repository ist unter der **[PolyForm Strict License 1.0.0](LICENSE)** lizenziert.

- ✅ Sie dürfen es lesen, zitieren und für persönliche, nichtkommerzielle Referenzzwecke nutzen.
- ❌ Es gewährt **kein** Recht, Kopien zu verbreiten, einen Fork zu erstellen oder ein abgeleitetes Werk daraus zu bauen — einschließlich eines modifizierten oder "freien" Builds von Voxis selbst.

**Kommerzielle Lizenzierung, oder jede Nutzung über das Lesen dieses Ausschnitts hinaus** (kommerzielle Produkte, SaaS, White-Label): **<https://voxislive.com/licensing>**.

Wir nehmen keine Code-Beiträge zu diesem Repository an (siehe [`.github/CONTRIBUTING.md`](.github/CONTRIBUTING.md)) — es gibt kein Recht auf abgeleitete Werke, unter dem man beitragen könnte, und dies ist nicht der echte Quellbaum des Produkts.

---

## Support

- **Probleme/Fehlerberichte zur App:** [GitHub Issues](https://github.com/VoxisLive/voxislive/issues)
- **Sicherheit:** [`.github/SECURITY.md`](.github/SECURITY.md)
- **Geschäftliche Anfragen:** <https://voxislive.com/licensing>
- **Datenschutzerklärung:** [`docs/PRIVACY.md`](docs/PRIVACY.md)

*Voxis Live — Echtzeit-Simultanübersetzung.*
