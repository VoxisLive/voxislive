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
    "1.0.57": {
        "en": [
            "If Voxis's fast translation engine runs into trouble during your free trial, you now get a backup voice instead of the session simply ending — with a short notice explaining what happened.",
            "Fixed a rare case where a translation error could show a technical message instead of a clear one.",
        ],
        "tr": [
            "Voxis'in hızlı çeviri motoru ücretsiz deneme sürenizde bir sorunla karşılaşırsa artık oturum tamamen sona ermek yerine yedek bir sese geçiyor — ne olduğunu açıklayan kısa bir uyarıyla birlikte.",
            "Bir çeviri hatasının bazen teknik bir mesaj göstermesine neden olan nadir bir durum düzeltildi.",
        ],
        "de": [
            "Wenn die schnelle Übersetzungs-Engine von Voxis während deiner kostenlosen Testphase Probleme hat, bekommst du jetzt eine Ersatzstimme, statt dass die Sitzung einfach endet — mit einem kurzen Hinweis, was passiert ist.",
            "Ein seltener Fall behoben, bei dem ein Übersetzungsfehler eine technische Meldung statt einer klaren Meldung anzeigen konnte.",
        ],
        "fr": [
            "Si le moteur de traduction rapide de Voxis rencontre un problème pendant votre essai gratuit, vous obtenez désormais une voix de secours au lieu que la session se termine simplement — avec une brève notification expliquant ce qui s'est passé.",
            "Correction d'un cas rare où une erreur de traduction pouvait afficher un message technique au lieu d'un message clair.",
        ],
        "es": [
            "Si el motor de traducción rápido de Voxis tiene problemas durante tu prueba gratuita, ahora obtienes una voz de respaldo en lugar de que la sesión simplemente termine, con un breve aviso que explica lo ocurrido.",
            "Se corrigió un caso poco frecuente en el que un error de traducción podía mostrar un mensaje técnico en lugar de uno claro.",
        ],
        "pt": [
            "Se o mecanismo de tradução rápida da Voxis tiver problemas durante seu teste gratuito, agora você recebe uma voz alternativa em vez de a sessão simplesmente terminar — com um breve aviso explicando o que aconteceu.",
            "Corrigido um caso raro em que um erro de tradução podia mostrar uma mensagem técnica em vez de uma mensagem clara.",
        ],
        "it": [
            "Se il motore di traduzione veloce di Voxis riscontra un problema durante la prova gratuita, ora ricevi una voce di riserva invece che la sessione termini semplicemente — con un breve avviso che spiega cosa è successo.",
            "Risolto un caso raro in cui un errore di traduzione poteva mostrare un messaggio tecnico anziché uno chiaro.",
        ],
        "nl": [
            "Als Voxis' snelle vertaalengine tijdens je gratis proefperiode problemen ondervindt, krijg je nu een noodstem in plaats van dat de sessie gewoon eindigt — met een korte melding die uitlegt wat er is gebeurd.",
            "Een zeldzaam geval opgelost waarbij een vertaalfout een technisch bericht kon tonen in plaats van een duidelijk bericht.",
        ],
        "pl": [
            "Jeśli szybki silnik tłumaczenia Voxis napotka problem podczas Twojego darmowego okresu próbnego, zamiast zakończenia sesji otrzymasz teraz głos zapasowy — wraz z krótkim komunikatem wyjaśniającym, co się stało.",
            "Naprawiono rzadki przypadek, w którym błąd tłumaczenia mógł wyświetlać komunikat techniczny zamiast zrozumiałego.",
        ],
        "cs": [
            "Pokud rychlý překladový engine Voxis narazí na problém během vaší bezplatné zkušební doby, nyní místo ukončení relace dostanete záložní hlas — s krátkým upozorněním vysvětlujícím, co se stalo.",
            "Opravena vzácná situace, kdy chyba překladu mohla zobrazit technickou zprávu místo srozumitelné.",
        ],
        "hu": [
            "Ha a Voxis gyors fordítómotorja problémába ütközik az ingyenes próbaidőszak alatt, a munkamenet egyszerű leállása helyett most tartalék hangot kapsz — egy rövid üzenettel, amely elmagyarázza, mi történt.",
            "Kijavítottunk egy ritka esetet, amikor egy fordítási hiba technikai üzenetet jeleníthetett meg egy érthető helyett.",
        ],
        "ro": [
            "Dacă motorul rapid de traducere al Voxis întâmpină o problemă în timpul perioadei de probă gratuite, primești acum o voce de rezervă în loc ca sesiunea să se încheie pur și simplu — cu o notificare scurtă care explică ce s-a întâmplat.",
            "A fost corectată o situație rară în care o eroare de traducere putea afișa un mesaj tehnic în loc de unul clar.",
        ],
        "sv": [
            "Om Voxis snabba översättningsmotor stöter på problem under din kostnadsfria provperiod får du nu en reservröst i stället för att sessionen bara avslutas — med ett kort meddelande som förklarar vad som hände.",
            "Ett sällsynt fall åtgärdat där ett översättningsfel kunde visa ett tekniskt meddelande i stället för ett tydligt.",
        ],
        "sr": [
            "Ako brzi motor za prevođenje Voxis-a naiđe na problem tokom vašeg besplatnog probnog perioda, sada dobijate rezervni glas umesto da se sesija jednostavno završi — uz kratko obaveštenje koje objašnjava šta se dogodilo.",
            "Ispravljen redak slučaj u kome je greška prevoda mogla da prikaže tehničku poruku umesto jasne.",
        ],
        "ru": [
            "Если быстрый движок перевода Voxis столкнётся с проблемой во время бесплатного пробного периода, теперь вместо завершения сеанса вы получите резервный голос — с коротким уведомлением о том, что произошло.",
            "Исправлен редкий случай, когда ошибка перевода могла показывать техническое сообщение вместо понятного.",
        ],
        "ja": [
            "無料トライアル中にVoxisの高速翻訳エンジンに問題が発生した場合、セッションがそのまま終了する代わりに、バックアップ音声に切り替わるようになりました。何が起きたかを説明する短い通知も表示されます。",
            "翻訳エラー時にわかりやすいメッセージの代わりに技術的なメッセージが表示されることがあった、まれな不具合を修正しました。",
        ],
        "ko": [
            "무료 체험 중 Voxis의 빠른 번역 엔진에 문제가 발생하면 세션이 그냥 종료되는 대신 이제 백업 음성으로 전환됩니다 — 무슨 일이 있었는지 설명하는 짧은 안내와 함께요.",
            "번역 오류 시 알기 쉽게 메시지 대신 기술적인 메시지가 표시되던 드물것을 수정했습니다.",
        ],
        "zh": [
            "如果 Voxis 的快速翻译引擎在您的免费试用期间遇到问题，现在会切换到备用语音，而不是直接结束会话——并附有简短提示说明发生了什么。",
            "修复了翻译出错时偶尔显示技术性信息而非清晰提示的问题。",
        ],
        "zh-Hant": [
            "如果 Voxis 的快速翻譯引擎在您的免費試用期間遇到問題，現在會切換到備援語音，而不是直接結束工作階段——並附上簡短提示說明發生了什麼事。",
            "修復了翻譯發生錯誤時偶爾顯示技術性訊息而非清楚提示的問題。",
        ],
        "hi": [
            "अगर आपके फ़्री ट्रायल के दौरान Voxis का तेज़ अनुवाद इंजन किसी समस्या में फंसता है, तो अब सत्र बस समाप्त होने के बजाय आपको एक बैकअप आवाज़ मिलेगी — साथ ही यह बताने वाला एक छोटा नोटिस कि क्या हुआ।",
            "एक दुर्लभ स्थिति ठीक की गई जिसमें अनुवाद त्रुटि स्पष्ट संदेश के बजाय एक तकनीकी संदेश दिखा सकती थी।",
        ],
        "id": [
            "Jika mesin terjemahan cepat Voxis mengalami gangguan selama masa uji coba gratis Anda, kini Anda mendapatkan suara cadangan alih-alih sesi langsung berakhir — disertai pemberitahuan singkat yang menjelaskan apa yang terjadi.",
            "Memperbaiki kasus langka di mana kesalahan terjemahan bisa menampilkan pesan teknis alih-alih pesan yang jelas.",
        ],
        "vi": [
            "Nếu công cụ dịch nhanh của Voxis gặp sự cố trong thời gian dùng thử miễn phí, giờ đây bạn sẽ nhận được giọng nói dự phòng thay vì phiên làm việc kết thúc — kèm theo thông báo ngắn giải thích điều gì đã xảy ra.",
            "Đã sửa một trường hợp hiếm gặp khi lỗi dịch có thể hiển thị thông báo kỹ thuật thay vì thông báo rõ ràng.",
        ],
        "th": [
            "หากเอนจินแปลภาษาความเร็วสูงของ Voxis พบปัญหาระหว่างช่วงทดลองใช้ฟรีของคุณ ตอนนี้คุณจะได้รับเสียงสำรองแทนที่เซสชันจะจบลงไปเฉยๆ — พร้อมข้อความแจ้งเตือนสั้นๆ อธิบายว่าเกิดอะไรขึ้น",
            "แก้ไขกรณีที่พบได้ยากซึ่งข้อผิดพลาดในการแปลอาจแสดงข้อความทางเทคนิคแทนที่จะเป็นข้อความที่ชัดเจน",
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
