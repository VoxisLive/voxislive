# Voxis Live

**[English](README.md)** | **[Türkçe](README.tr.md)** | **Deutsch**

![GitHub stars](https://img.shields.io/github/stars/VoxisLive/voxislive?style=social)
![License](https://img.shields.io/badge/license-All%20Rights%20Reserved-blue)

**VoxisLive ist eine Desktop-App für Windows (und Linux über den Snap Store), die Systemaudio — Videos, Spiele, Meetings — in Echtzeit übersetzt und die Übersetzung in Ihrer Sprache vorspricht: Sie hören eine Stimme, keine Untertitel.** Im Zwei-Wege-Meeting-Modus hört Ihr Gegenüber Sie über ein virtuelles Mikrofon in seiner Sprache. 79 Zielsprachen; kostenlos 10 Minuten pro Tag (35 der 79 Sprachen mit Stimme); vorausbezahlte Minuten, kein Abo; im Microsoft Store erhältlich.

Die kostenlosen Tagesminuten gelten im Video- und Spielmodus; die 44 Sprachen ohne kostenlose Stimme erscheinen als Live-Untertitel. Kostenpflichtige Minutenpakete sprechen alle 79 Sprachen und schalten den Meeting-Modus frei.

**Herunterladen:** [Microsoft Store](https://apps.microsoft.com/detail/9P5Z0KVS58RS) (Windows 10 und 11) · [Snap Store](https://snapcraft.io/voxis) (Linux) · Website: **[voxislive.com](https://voxislive.com)** · [Preise](https://voxislive.com/pricing)

> [!WARNING]
> **Dieses Repository bietet keine Möglichkeit, Voxis auszuführen.** Es ist ein kuratierter, schreibgeschützter Ausschnitt des audioverarbeitenden Codes der Engine, veröffentlicht, damit jeder überprüfen kann, wie Audio erfasst, übertragen und gespeichert wird — siehe [Quelltransparenz](#quelltransparenz) unten. **Vertrauen Sie nur Downloads aus dem [Microsoft Store](https://apps.microsoft.com/detail/9P5Z0KVS58RS), dem [Snap Store](https://snapcraft.io/voxis) oder von [voxislive.com](https://voxislive.com)** — dieses Repository bietet keine Downloads an. Kopien dieses Repositories wurden auf anderen GitHub-Konten gefunden, einige leiten zu anderswo gehosteten Installern weiter — diese sind **nicht offiziell** und können bösartig sein. Wenn ein Fork oder Klon behauptet, Sie könnten Voxis daraus bauen und ausführen, ist das falsch; melden Sie es an [support@voxislive.com](mailto:support@voxislive.com).

---

## Überblick

Voxis liest **Systemaudio direkt** (WASAPI unter Windows, PipeWire unter Linux) und funktioniert daher mit allem, was Ihr Computer wiedergibt — native Spiele, Zoom/Teams/Discord-Anrufe in der Desktop-App, ein lokaler Videoplayer oder ein Video in einem beliebigen Browser.

Voxis erfasst Systemaudio (aus Videos, Spielen oder Anrufen), streamt es an ein cloudbasiertes Sprache-zu-Sprache-Übersetzungsmodell und spielt die gesprochene Übersetzung in Echtzeit ab, während die Person spricht — ein nativer **Simultandolmetscher**, keine Kette aus Spracherkennung → Übersetzung → Sprachsynthese.

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
             win_audio.py)             Nicht-Sprache)   Live-Sitzungs-Hop)
```

Was diese Dateien Ihnen zu überprüfen erlauben:

- **`app/base_translator.py`** ist die Sitzungs-Zustandsmaschine, die unsere beiden Echtzeit-Engines für den Live-Roundtrip verwenden — verbinden, Audio senden, übersetztes Audio empfangen, bei Fehlern neu verbinden. Lesen Sie sie vollständig: es gibt keinen Hintergrund-Upload und keine Protokollierung des Gesagten. Die kostenlosen Tagesminuten nutzen einen separaten Anfrageweg — ein HTTPS-Aufruf pro erkanntem Sprachsegment, zurück kommt übersetzter Text, der auf Ihrem Gerät vertont wird —, der in der nicht veröffentlichten Orchestrierungsschicht liegt; davor sitzt ebenfalls ein lokales Sprach-Gate derselben Art.
- **`app/translator.py`** ist ein konkretes, vollständiges Beispiel dieser Verbindung (unsere Gemini-Integration) — kein Platzhalter.
- **`app/vad.py`** ist das lokale Sprach-Gate: Audio, das das Gate als Nicht-Sprache einstuft, wird vor dem Senden durch digitale Stille ersetzt, sodass Musik, Geräusche und Raumklang das Gerät nie als Audio verlassen. Die Gate-Entscheidung steht hier; der Ersetzungsschritt liegt in der nicht veröffentlichten Orchestrierungsschicht.
- **`app/audio_recorder.py`** zeigt, dass lokale Audioaufzeichnung opt-in, standardmäßig deaktiviert und **im Meeting-Modus unmöglich zu aktivieren** ist — diese Prüfung steht im Code, nicht nur in einer Einstellung.
- **`app/transcript_store.py`** zeigt, dass Transkripte nur auf Ihre eigene Festplatte geschrieben werden, es sei denn, Sie exportieren oder teilen eines ausdrücklich.
- **`app/report_scrub.py`** zeigt genau, was (Schlüssel, Tokens, E-Mails, lokale Benutzernamen) entfernt wird, bevor ein optionaler Problembericht Ihr Gerät verlässt.
- **`app/i18n.py`** ist der tatsächliche Text, den die App dazu auf dem Bildschirm zeigt — einschließlich der In-App-Datenschutzerklärung.

`docs/PRIVACY.md`, `docs/TERMS.md` und der Rest von `docs/` sind die allgemeinverständlichen Versionen derselben Aussagen.

**Was hier nicht enthalten ist, und warum:** die Orchestrierungsschicht, die Benutzeroberfläche, unsere kostenpflichtigen Übersetzungs-Engine-Integrationen, Qualitätsoptimierungen und Konto-/Abrechnungscode werden nicht veröffentlicht. Nichts davon ändert die obige Kette aus Erfassung und Sprach-Gate, die vor jeder Engine sitzt — und die Veröffentlichung würde einem Wettbewerber ohne Transparenzgewinn unsere Feinabstimmung und Geschäftslogik liefern. `scripts/check_release_hygiene.py` ist das mechanische Gate, das verhindert, dass diese Grenze verwässert wird; jede in diesem Repository getrackte Datei muss dort explizit benannt sein.

Der Code in diesem Repository wird unter einem **[Alle-Rechte-vorbehalten-Hinweis](LICENSE)** veröffentlicht: Sie können ihn lesen, aber er gewährt kein Recht, ihn zu nutzen, zu kopieren, weiterzuverbreiten, zu forken oder abgeleitete Werke daraus zu erstellen — auch nicht für den persönlichen oder nichtkommerziellen Gebrauch. Siehe Abschnitt [Lizenz](#lizenz) unten.

---

## Architektur (veröffentlichte Dateien)

| Modul | Was es zeigt |
| --- | --- |
| `app/process_loopback.py` | Treiberlose WASAPI-Loopback-Erfassung; schließt Voxis' eigene Audioausgabe aus, damit es sich niemals selbst neu übersetzt |
| `app/session_duck.py`, `app/win_audio.py` | Wie andere Anwendungen gedämpft und Ausgabe-Endpunkte umgeschaltet werden — kein Audio wird im Prozess anderswohin kopiert |
| `app/audio_io.py`, `app/mix_core.py` | Geräteerfassung, der Stereo-Player und der Look-ahead-Limiter |
| `app/vad.py` | Lokales Silero-VAD-Gate — Nicht-Sprache wird durch Stille ersetzt, bevor etwas gesendet wird |
| `app/base_translator.py` | Die Übersetzungssitzungs-Zustandsmaschine der Echtzeit-Engines — der Netzwerk-Hop der Live-Sitzung |
| `app/translator.py` | Eine vollständige, konkrete Übersetzungs-Engine-Verbindung (Gemini) |
| `app/audio_recorder.py` | Optionale lokale Zwei-Spur-Aufnahme — opt-in, nur Video/Spiel-Modus |
| `app/transcript_store.py` | Rein lokale Transkript-Persistenz und TXT/SRT/VTT-Export |
| `app/report_scrub.py` | Client-seitige Schwärzung, angewendet vor dem Senden eines optionalen Problemberichts |
| `app/i18n.py` | Der tatsächliche In-App-Status- und Datenschutz-Erklärungstext |
| `app/paths.py` | Wo lokale Daten (Transkripte, Modelle) tatsächlich auf der Festplatte liegen |

Einige Dateien unter `tests/` prüfen diese Module direkt (`test_mix_core.py`, `test_ring.py`, `test_player_volume.py`, `test_audio_test_tone.py`, `test_speech_gate.py`, `test_session_duck.py`, `test_report_scrub.py`, `test_transcript_export.py`, `test_audio_recorder.py`) und laufen bei jedem Push in der CI — siehe den [Quality-Workflow](.github/workflows/quality.yml). Sie sind zum Lesen und als zweite, ausführbare Form derselben Aussagen enthalten, nicht als Einladung, die vollständige Anwendung aus diesem Baum zu bauen.

---

## Meeting-Modus einrichten (Zwei-Wege-Übersetzung)

Dieser Abschnitt richtet sich an Nutzer der installierten App, nicht ans Bauen aus dem Quellcode.

**Ziel:** Sie sprechen Türkisch → die andere Seite hört Englisch; die andere Seite spricht Englisch → Sie hören Türkisch.

| Richtung | Was sie tut | Voraussetzung |
| --- | --- | --- |
| **Eingehend** (Sie hören die andere Person in Ihrer Sprache) | Hört Systemaudio ab, übersetzt, spielt in Ihren Kopfhörern ab | Teil des Meeting-Modus, der das unten beschriebene virtuelle Kabel voraussetzt |
| **Ausgehend** (Ihre Stimme geht übersetzt hinaus) | Übersetzt Ihr Mikrofon, speist ein virtuelles Mikrofon | Ein virtuelles Mikrofon (VB-CABLE) ist erforderlich |

Unter Windows ist die einzige Möglichkeit, ein "Mikrofon" bereitzustellen, das eine Meeting-App (Teams/Zoom/Meet) auswählen kann, ein virtueller Audiotreiber — daher braucht die ausgehende Richtung einen solchen. **Unter Windows startet der Meeting-Modus ohne installiertes virtuelles Kabel nicht.**

1. Installieren Sie ein kostenloses virtuelles Kabel, z. B. [VB-CABLE](https://vb-audio.com/Cable/) — Installer als Administrator ausführen, neu starten.
2. Stellen Sie in Voxis das **Ausgabegerät** auf Ihre echten Kopfhörer und das **Mikrofon** auf das Gerät, in das Sie tatsächlich sprechen. Das installierte virtuelle Kabel wird automatisch erkannt; kein manuelles Routing nötig.
3. Stellen Sie in Ihrer Meeting-App das **Mikrofon** auf das Aufnahmegerät des Kabels (z. B. "CABLE Output") — dorthin schreibt Voxis Ihre übersetzte Stimme.
4. Starten Sie Voxis → **Meeting**-Modus. Sprechen Sie Ihre Sprache → sie geht übersetzt hinaus; die andere Seite spricht ihre Sprache → Sie hören sie übersetzt.

---

## Latenz und Simultanübersetzung

Die Verzögerung ist die vom Übersetzungsmodell vorgesehene *Ohr-Stimme-Spanne* — es wartet auf genug Kontext, um korrekt zu übersetzen, so wie ein menschlicher Simultandolmetscher —, kein clientseitiger Puffer. Der **Schnelle Modus** der App zeigt Untertitel sofort an und lässt die übersetzte Stimme mit bis zu 1,5× aufholen; die Spanne des Modells verkürzt er nicht.

---

## Fehlerbehebung

| Symptom | Ursache | Lösung |
| --- | --- | --- |
| Meeting-Modus startet nicht (Windows) | Kein virtuelles Kabel installiert | Ein virtuelles Kabel wie VB-CABLE installieren (siehe oben) und das Meeting erneut starten |
| Keine Übersetzungsausgabe zu hören | Ausgabegerät auf ein virtuelles Kabel gesetzt | Ausgabegerät auf Ihre echten Kopfhörer setzen |
| `PaError -9999` | Veraltete Windows-Audiogeräteliste | Audiogerät aus- und wieder einstecken, Voxis neu starten |

Für alles andere nutzen Sie **Problem melden** in der App (siehe `app/report_scrub.py` für die genaue Schwärzung vor dem Versand) oder eröffnen Sie ein [GitHub Issue](https://github.com/VoxisLive/voxislive/issues).

---

## Lizenz

Dieses Repository existiert, damit Sie unsere Datenschutzversprechen selbst überprüfen können — siehe [Quelltransparenz](#quelltransparenz) oben. Es zu lesen kostet nichts und erfordert keine Lizenz; darauf aufzubauen schon. Es ist ein einsehbarer Quellcode-Ausschnitt ohne Nutzungslizenz, veröffentlicht unter einem **[Alle-Rechte-vorbehalten-Hinweis](LICENSE)**.

- ✅ Sie dürfen den Code lesen und kurze Ausschnitte für Kommentare, Kritik oder Sicherheitsforschung zitieren.
- ❌ Er gewährt **kein** Recht zur Nutzung, zum Kopieren, zur Verbreitung, zum Forken oder zum Erstellen eines abgeleiteten Werks daraus — weder kommerziell noch für den persönlichen/nichtkommerziellen Gebrauch. Voxis Live wird verkauft, nicht verschenkt: Wir vertreiben die offizielle App, und die Nutzung mit eigenem API-Schlüssel (BYOK) wird innerhalb dieser App als einmalige Freischaltung verkauft. Daran ändert dieses Repository nichts.

**Kommerzielle Lizenzierung, oder jede Nutzung über das Lesen dieses Ausschnitts hinaus** (kommerzielle Produkte, SaaS, White-Label): **<https://voxislive.com/licensing>**.

Wir nehmen keine Code-Beiträge zu diesem Repository an (siehe [`.github/CONTRIBUTING.md`](.github/CONTRIBUTING.md)) — es gibt keine Lizenz, unter der man beitragen könnte, und dies ist nicht der echte Quellbaum des Produkts.

---

## Support

- **Probleme/Fehlerberichte zur App:** [GitHub Issues](https://github.com/VoxisLive/voxislive/issues)
- **Sicherheit:** [`.github/SECURITY.md`](.github/SECURITY.md)
- **Geschäftliche Anfragen:** <https://voxislive.com/licensing>
- **Datenschutzerklärung:** [`docs/PRIVACY.md`](docs/PRIVACY.md)

*Voxis Live — Echtzeit-Simultanübersetzung.*
