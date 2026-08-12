"""In-app release notes: shown once per version, in the user's own UI language.

Why this exists: updates arrive through the Microsoft Store, so the only place a
returning user could read what changed was the Store listing — which nobody opens
after installing. Feature work therefore shipped invisibly.

Contract:
  * NOTES is keyed by APP_VERSION, then by the app's own language code (the 23 in
    app/i18n.py). A missing language falls back to English; a version with no
    entry shows nothing at all, so a release that forgets to add notes degrades to
    the old silence instead of an empty dialog.
  * The gate (webui.Bridge.whatsnew) shows the notes once and records the version
    in cfg["whatsnew_seen"]. A FRESH install is marked silently — a first-time user
    gets the onboarding tour, not a changelog for a version they never had.
  * Bullets are plain user-facing sentences: the symptom fixed or the thing you can
    now do, never the mechanism. Same rule as the Store listing.
  * A bullet must still be TRUE in the running build, because the card is now
    shown after the fact — it covers every version the user skipped, not just the
    current one. 1.0.49 shipped "your minutes pause while nobody is speaking" and
    that behaviour was reverted the next day (a8530a9, owner decision); its bullet
    was deleted from this table rather than shown to a 1.0.52 user as a billing
    promise the build does not keep. When backfilling old notes, re-read them
    against today's behaviour first.

Keeping it filled: the release chain already translates the same text into 23
locales for the Store listing (`.local/store-listings/notes_<ver>.json`).
`scripts/gen_whatsnew.py` maps those locale codes onto the app's codes and rewrites
this file, so the two can never drift and nobody translates twice.
"""
from . import APP_VERSION

# Fallback language for any locale we have no translation for.
FALLBACK_LANG = "en"

NOTES = {
    "1.0.56": {
        "en": [
            "The language picker now shows upfront which languages are on paid plans only, instead of letting you pick one on the free tier and finding out later that it doesn't work.",
        ],
        "tr": [
            "Dil seçici artık hangi dillerin yalnızca ücretli planlarda olduğunu baştan gösteriyor — ücretsiz sürümde bir dili seçip sonradan çalışmadığını görmek yerine.",
        ],
        "de": [
            "Die Sprachauswahl zeigt jetzt von vornherein an, welche Sprachen nur in kostenpflichtigen Plänen verfügbar sind, statt dass man sie in der kostenlosen Version auswählt und erst später feststellt, dass sie nicht funktioniert.",
        ],
        "fr": [
            "Le sélecteur de langue indique désormais dès le départ quelles langues sont réservées aux forfaits payants, plutôt que de laisser choisir une langue dans la version gratuite pour découvrir ensuite qu'elle ne fonctionne pas.",
        ],
        "es": [
            "El selector de idioma ahora muestra de antemano qué idiomas están disponibles solo en los planes de pago, en lugar de dejarte elegir uno en la versión gratuita y descubrir después que no funciona.",
        ],
        "pt": [
            "O seletor de idioma agora mostra logo de início quais idiomas estão disponíveis apenas nos planos pagos, em vez de deixar você escolher um na versão gratuita e descobrir depois que ele não funciona.",
        ],
        "it": [
            "Il selettore della lingua ora mostra subito quali lingue sono disponibili solo nei piani a pagamento, invece di lasciarti scegliere una nella versione gratuita e scoprire solo dopo che non funziona.",
        ],
        "nl": [
            "De taalkiezer laat nu meteen zien welke talen alleen in betaalde abonnementen beschikbaar zijn, in plaats van dat je er in de gratis versie een kiest en pas later merkt dat die niet werkt.",
        ],
        "pl": [
            "Selektor języka pokazuje teraz od razu, które języki są dostępne tylko w planach płatnych, zamiast pozwalać wybrać taki język w wersji darmowej i dopiero potem odkryć, że nie działa.",
        ],
        "cs": [
            "Výběr jazyka teď rovnou ukazuje, které jazyky jsou jen v placených plánech, místo aby ve zdarma verzi šlo takový jazyk vybrat a zjistit až pak, že nefunguje.",
        ],
        "hu": [
            "A nyelvválasztó most már előre megmutatja, mely nyelvek érhetők el csak fizetős csomagokban, ahelyett hogy az ingyenes verzióban kiválaszthatnád, majd csak utólag derülne ki, hogy nem működik.",
        ],
        "ro": [
            "Selectorul de limbă arată acum din start care limbi sunt disponibile doar în planurile plătite, în loc să te lase să alegi una în versiunea gratuită și să afli abia mai târziu că nu funcționează.",
        ],
        "sv": [
            "Språkväljaren visar nu direkt vilka språk som bara finns i betalplaner, i stället för att du väljer ett i den gratis versionen och först senare upptäcker att det inte fungerar.",
        ],
        "sr": [
            "Birač jezika sada odmah pokazuje koji su jezici dostupni samo u plaćenim paketima, umesto da izaberete jezik u besplatnoj verziji pa tek kasnije otkrijete da ne radi.",
        ],
        "ru": [
            "Выбор языка теперь сразу показывает, какие языки доступны только на платных тарифах, вместо того чтобы вы выбирали язык в бесплатной версии и узнавали позже, что он не работает.",
        ],
        "ja": [
            "言語選択画面で、どの言語が有料プラン限定かを最初から表示するようになりました。無料版で選んでから動作しないことに後で気づく、という状況がなくなります。",
        ],
        "ko": [
            "언어 선택 화면에서 어떤 언어가 유료 플랜 전용인지 처음부터 표시됩니다. 무료 버전에서 선택한 뒤 나중에 작동하지 않는다는 것을 알게 되는 대신입니다.",
        ],
        "zh": [
            "语言选择器现在会提前显示哪些语言仅限付费套餐使用，而不是让你在免费版中选择后才发现无法使用。",
        ],
        "zh-Hant": [
            "語言選擇器現在會提前顯示哪些語言僅限付費方案使用，而不是讓你在免費版中選取後才發現無法使用。",
        ],
        "hi": [
            "भाषा चयनकर्ता अब पहले से दिखाता है कि कौन-सी भाषाएँ केवल भुगतान वाली योजनाओं में उपलब्ध हैं, बजाय इसके कि आप मुफ़्त संस्करण में उसे चुनें और बाद में पता चले कि वह काम नहीं करती।",
        ],
        "id": [
            "Pemilih bahasa sekarang langsung menunjukkan bahasa mana yang hanya tersedia di paket berbayar, alih-alih membiarkan Anda memilihnya di versi gratis dan baru menyadari kemudian bahwa bahasa itu tidak berfungsi.",
        ],
        "vi": [
            "Bộ chọn ngôn ngữ giờ đây hiển thị ngay từ đầu ngôn ngữ nào chỉ có ở các gói trả phí, thay vì để bạn chọn ở bản miễn phí rồi mới phát hiện ra là nó không hoạt động.",
        ],
        "th": [
            "ตัวเลือกภาษาตอนนี้จะแสดงล่วงหน้าว่าภาษาใดใช้ได้เฉพาะในแพ็กเกจแบบชำระเงินเท่านั้น แทนที่จะให้คุณเลือกในเวอร์ชันฟรีแล้วมาพบทีหลังว่าใช้งานไม่ได้",
        ],
    },
}


def entry(version: str = APP_VERSION, lang: str = FALLBACK_LANG) -> list:
    """Release-note bullets for (version, lang); [] when the version is unknown.

    An unknown/untranslated language falls back to English rather than showing
    nothing — a returning user reading English notes is better served than one
    who is told nothing changed."""
    per_lang = NOTES.get(str(version)) or {}
    bullets = per_lang.get(lang) or per_lang.get(FALLBACK_LANG) or []
    return list(bullets)


def has_notes(version: str = APP_VERSION) -> bool:
    """True when this version ships notes at all (a release may forget)."""
    return bool(NOTES.get(str(version)))


def _key(version: str) -> tuple:
    """Sortable version key. String order is wrong here — "1.0.9" sorts after
    "1.0.10" as text, and the patch number has already passed 10."""
    parts = []
    for chunk in str(version).split("."):
        digits = "".join(c for c in chunk if c.isdigit())
        parts.append(int(digits) if digits else 0)
    return tuple(parts)


def versions_since(seen: str, current: str = APP_VERSION) -> list:
    """Versions with notes that the user has NOT read yet, oldest first.

    Store updates skip versions freely: someone can go from 1.0.49 straight to
    1.0.52 in one background update. The card used to show only the running
    version's notes, so every release in between was invisible — 1.0.50's notes
    reached nobody who jumped 1.0.49 -> 1.0.51 that way.

    `seen` is the version string cfg["whatsnew_seen"] recorded (see
    webui.mark_whatsnew_seen). Blank means the user updated from a build that
    predates this feature, so nothing in the table has been read — return all of
    it. Anything newer than `current` is ignored: a downgrade must not advertise
    features the running build does not have."""
    top = _key(current)
    if not seen:
        return sorted((v for v in NOTES if _key(v) <= top), key=_key)
    low = _key(seen)
    return sorted((v for v in NOTES if low < _key(v) <= top), key=_key)


def entries_since(seen: str, lang: str = FALLBACK_LANG,
                  current: str = APP_VERSION) -> list:
    """[{version, bullets}] for every unread version, newest first.

    Newest first because that is what the user came for; the older ones read as
    "and here is what you also missed"."""
    out = []
    for ver in reversed(versions_since(seen, current)):
        bullets = entry(ver, lang)
        if bullets:
            out.append({"version": ver, "bullets": bullets})
    return out
