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

Keeping it filled: the release chain already translates the same text into 23
locales for the Store listing (`.local/store-listings/notes_<ver>.json`).
`scripts/gen_whatsnew.py` maps those locale codes onto the app's codes and rewrites
this file, so the two can never drift and nobody translates twice.
"""
from . import APP_VERSION

# Fallback language for any locale we have no translation for.
FALLBACK_LANG = "en"

NOTES = {
    "1.0.51": {
        "cs": [
            "Překlad už uprostřed relace neztichne: když překladová služba přestane odpovídat, Voxis to teď pozná a sám se znovu připojí.",
            "Dlouhé schůzky se zotaví samy — už není nutné relaci zastavit a spustit znovu, aby se hlas vrátil.",
        ],
        "de": [
            "Die Übersetzung verstummt nicht mehr mitten in einer Sitzung: Wenn der Übersetzungsdienst nicht mehr antwortet, merkt Voxis das jetzt und verbindet sich von selbst neu.",
            "Lange Meetings erholen sich von allein — du musst die Sitzung nicht mehr stoppen und neu starten, damit die Stimme zurückkommt.",
        ],
        "en": [
            "Translation no longer goes quiet in the middle of a session: if the translation service stops responding, Voxis now notices and reconnects on its own.",
            "Long meetings recover by themselves — no more stopping and restarting the session to get the voice back.",
        ],
        "es": [
            "La traducción ya no se queda en silencio a mitad de una sesión: si el servicio de traducción deja de responder, Voxis lo detecta y se reconecta solo.",
            "Las reuniones largas se recuperan por sí solas: ya no hace falta detener y reiniciar la sesión para recuperar la voz.",
        ],
        "fr": [
            "La traduction ne devient plus silencieuse en pleine session : si le service de traduction cesse de répondre, Voxis s'en aperçoit et se reconnecte tout seul.",
            "Les longues réunions se rétablissent d'elles-mêmes — plus besoin d'arrêter et de relancer la session pour retrouver la voix.",
        ],
        "hi": [
            "अनुवाद अब सेशन के बीच में चुप नहीं होता: अगर अनुवाद सेवा जवाब देना बंद कर दे, तो Voxis इसे पहचानकर खुद दोबारा जुड़ जाता है।",
            "लंबी मीटिंग खुद ही सामान्य हो जाती हैं — आवाज़ वापस लाने के लिए सेशन रोककर दोबारा शुरू करने की ज़रूरत नहीं।",
        ],
        "hu": [
            "A fordítás már nem némul el a munkamenet közepén: ha a fordítási szolgáltatás nem válaszol, a Voxis ezt észreveszi, és magától újracsatlakozik.",
            "A hosszú megbeszélések maguktól helyreállnak — nem kell leállítani és újraindítani a munkamenetet, hogy visszatérjen a hang.",
        ],
        "id": [
            "Terjemahan tidak lagi mendadak senyap di tengah sesi: jika layanan terjemahan berhenti merespons, Voxis kini menyadarinya dan menyambung ulang sendiri.",
            "Rapat panjang pulih dengan sendirinya — tidak perlu lagi menghentikan dan memulai ulang sesi agar suaranya kembali.",
        ],
        "it": [
            "La traduzione non ammutolisce più a metà sessione: se il servizio di traduzione smette di rispondere, Voxis se ne accorge e si riconnette da solo.",
            "Le riunioni lunghe si riprendono da sole — non serve più fermare e riavviare la sessione per far tornare la voce.",
        ],
        "ja": [
            "セッションの途中で翻訳が止まらなくなりました。翻訳サービスが応答しなくなると、Voxis がそれを検知して自動的に接続し直します。",
            "長い会議も自動で復帰します。音声を取り戻すためにセッションを停止して開始し直す必要はありません。",
        ],
        "ko": [
            "세션 도중에 번역이 끊기지 않습니다. 번역 서비스가 응답을 멈추면 Voxis가 이를 감지해 스스로 다시 연결합니다.",
            "긴 회의도 저절로 복구됩니다. 음성을 되살리려고 세션을 중지했다가 다시 시작할 필요가 없습니다.",
        ],
        "nl": [
            "De vertaling valt niet meer stil midden in een sessie: als de vertaaldienst niet meer reageert, merkt Voxis dat nu en maakt vanzelf opnieuw verbinding.",
            "Lange vergaderingen herstellen zichzelf — je hoeft de sessie niet meer te stoppen en opnieuw te starten om de stem terug te krijgen.",
        ],
        "pl": [
            "Tłumaczenie nie milknie już w trakcie sesji: jeśli usługa tłumaczenia przestanie odpowiadać, Voxis to wykryje i sam połączy się ponownie.",
            "Długie spotkania wracają do normy same — nie trzeba już zatrzymywać i uruchamiać sesji od nowa, żeby odzyskać głos.",
        ],
        "pt": [
            "A tradução não fica mais muda no meio de uma sessão: se o serviço de tradução parar de responder, o Voxis percebe e se reconecta sozinho.",
            "Reuniões longas se recuperam sozinhas — não é mais preciso parar e reiniciar a sessão para a voz voltar.",
        ],
        "ro": [
            "Traducerea nu mai amuțește la mijlocul unei sesiuni: dacă serviciul de traducere nu mai răspunde, Voxis observă și se reconectează singur.",
            "Ședințele lungi își revin de la sine — nu mai trebuie să oprești și să repornești sesiunea ca să revină vocea.",
        ],
        "ru": [
            "Перевод больше не пропадает посреди сеанса: если служба перевода перестаёт отвечать, Voxis замечает это и переподключается сам.",
            "Длинные встречи восстанавливаются сами — больше не нужно останавливать и запускать сеанс заново, чтобы вернуть голос.",
        ],
        "sr": [
            "Prevod više ne utihne usred sesije: ako servis za prevođenje prestane da odgovara, Voxis to sada primeti i sam se ponovo poveže.",
            "Dugi sastanci se oporave sami — nema više zaustavljanja i ponovnog pokretanja sesije da bi se glas vratio.",
        ],
        "sv": [
            "Översättningen tystnar inte längre mitt i en session: om översättningstjänsten slutar svara märker Voxis det och återansluter av sig själv.",
            "Långa möten återhämtar sig på egen hand — du behöver inte längre stoppa och starta om sessionen för att få tillbaka rösten.",
        ],
        "th": [
            "การแปลจะไม่เงียบไปกลางคันอีกต่อไป: ถ้าบริการแปลหยุดตอบสนอง Voxis จะรู้ตัวและเชื่อมต่อใหม่ให้เอง",
            "การประชุมยาว ๆ กลับมาทำงานได้เอง ไม่ต้องหยุดแล้วเริ่มเซสชันใหม่เพื่อให้เสียงกลับมา",
        ],
        "tr": [
            "Çeviri artık oturumun ortasında susmuyor: çeviri servisi yanıt vermeyi kesince Voxis bunu fark edip kendiliğinden yeniden bağlanıyor.",
            "Uzun toplantılar kendi kendine toparlanıyor — sesi geri getirmek için oturumu durdurup yeniden başlatmanız gerekmiyor.",
        ],
        "vi": [
            "Bản dịch không còn im bặt giữa phiên nữa: nếu dịch vụ dịch ngừng phản hồi, Voxis sẽ nhận ra và tự kết nối lại.",
            "Các cuộc họp dài tự phục hồi — không cần dừng rồi khởi động lại phiên để lấy lại giọng nói.",
        ],
        "zh": [
            "翻译不会再在会话中途中断：如果翻译服务停止响应，Voxis 现在会察觉并自动重新连接。",
            "长时间会议可以自行恢复——不必再停止并重新开始会话才能让声音回来。",
        ],
        "zh-Hant": [
            "翻譯不會再在工作階段中途中斷：如果翻譯服務停止回應，Voxis 現在會察覺並自動重新連線。",
            "長時間會議可以自行恢復——不必再停止並重新開始工作階段才能讓聲音回來。",
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
