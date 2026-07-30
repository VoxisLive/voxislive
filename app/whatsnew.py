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
    "1.0.50": {
        "en": [
            "Choose whether the translated voice sounds female or male — with a separate setting for the voice the other person hears as you in Meeting mode.",
            "Brand and product names are spelled correctly out of the box: a ready-made term list now ships with Voxis, and your own terms moved to Settings › Translation.",
            "Release notes now live in the app: after every update you see what changed once, in your own language.",
        ],
        "tr": [
            "Çeviri sesinin kadın ya da erkek olmasını seçin — toplantıda karşı tarafın sizi hangi sesle duyacağı ayrı bir ayar.",
            "Marka ve ürün adları kutudan çıktığı gibi doğru yazılıyor: Voxis artık hazır bir terim listesiyle geliyor, kendi terimleriniz Ayarlar › Çeviri sekmesine taşındı.",
            "Sürüm notları artık uygulamanın içinde: her güncellemeden sonra neyin değiştiğini kendi dilinizde bir kez görüyorsunuz.",
        ],
        "de": [
            "Wähle, ob die übersetzte Stimme weiblich oder männlich klingt — mit einer separaten Einstellung für die Stimme, in der dich andere im Meeting-Modus hören.",
            "Marken- und Produktnamen werden von Anfang an korrekt geschrieben: Voxis bringt jetzt eine fertige Begriffsliste mit, deine eigenen Begriffe findest du unter Einstellungen › Übersetzung.",
            "Versionshinweise stehen jetzt in der App: Nach jedem Update siehst du einmal, was sich geändert hat — in deiner Sprache.",
        ],
        "cs": [
            "Vyber, zda má přeložený hlas znít žensky nebo mužsky — s vlastním nastavením pro hlas, kterým tě ostatní slyší v režimu schůzky.",
            "Názvy firem a produktů se píší správně hned od začátku: Voxis nyní obsahuje připravený seznam pojmů a tvoje vlastní pojmy najdeš v Nastavení › Překlad.",
            "Poznámky k verzi jsou nově přímo v aplikaci: po každé aktualizaci jednou uvidíš, co se změnilo, ve svém jazyce.",
        ],
        "fr": [
            "Choisissez si la voix traduite sonne féminine ou masculine, avec un réglage distinct pour la voix dans laquelle votre interlocuteur vous entend en mode Réunion.",
            "Les noms de marques et de produits sont correctement orthographiés dès le départ : Voxis intègre désormais une liste de termes prête à l'emploi, et vos propres termes se trouvent dans Paramètres › Traduction.",
            "Les nouveautés s'affichent maintenant dans l'application : après chaque mise à jour, vous voyez une fois ce qui a changé, dans votre langue.",
        ],
        "es": [
            "Elige si la voz traducida suena femenina o masculina, con un ajuste aparte para la voz con la que la otra persona te oye en el modo Reunión.",
            "Los nombres de marcas y productos se escriben bien desde el principio: Voxis ya incluye una lista de términos lista para usar y tus propios términos están en Ajustes › Traducción.",
            "Las novedades ahora están en la app: después de cada actualización ves una vez qué ha cambiado, en tu idioma.",
        ],
        "pt": [
            "Escolhe se a voz traduzida soa feminina ou masculina, com uma definição separada para a voz com que a outra pessoa te ouve no modo Reunião.",
            "Nomes de marcas e produtos ficam escritos corretamente desde o início: o Voxis já inclui uma lista de termos pronta e os teus próprios termos estão em Definições › Tradução.",
            "As novidades passam a estar na aplicação: depois de cada atualização vês uma vez o que mudou, no teu idioma.",
        ],
        "ja": [
            "翻訳音声を女性の声か男性の声かを選べます。会議モードで相手に聞こえるあなたの声は別に設定できます。",
            "ブランド名や製品名が最初から正しく表記されます。用語リストが同梱され、自分の用語は「設定 › 翻訳」に移りました。",
            "更新内容がアプリ内で読めるようになりました。アップデートのたびに、変更点を自分の言語で一度だけ表示します。",
        ],
        "ko": [
            "번역 음성을 여성 또는 남성으로 선택할 수 있습니다. 회의 모드에서 상대방이 나를 듣는 음성은 따로 설정합니다.",
            "브랜드와 제품 이름이 처음부터 정확하게 표기됩니다. 기본 용어 목록이 함께 제공되며, 직접 추가한 용어는 설정 › 번역으로 옮겼습니다.",
            "업데이트 내용을 이제 앱에서 봅니다. 업데이트할 때마다 무엇이 바뀌었는지 내 언어로 한 번 보여 줍니다.",
        ],
        "ru": [
            "Выберите, будет ли переведённый голос женским или мужским — и отдельно голос, которым собеседник слышит вас в режиме встречи.",
            "Названия брендов и продуктов сразу пишутся правильно: в Voxis теперь есть готовый список терминов, а ваши собственные термины переехали в «Настройки › Перевод».",
            "Список изменений теперь внутри приложения: после каждого обновления вы один раз увидите, что нового, на своём языке.",
        ],
        "zh": [
            "可以选择翻译语音是女声还是男声——会议模式中对方听到你的声音是单独的设置。",
            "品牌和产品名称一开始就拼写正确：Voxis 现在内置术语表，你自己的术语已移到“设置 › 翻译”。",
            "更新说明现在在应用内：每次更新后，你会用自己的语言看到一次变更内容。",
        ],
        "zh-Hant": [
            "可以選擇翻譯語音是女聲還是男聲——會議模式中對方聽到你的聲音是獨立的設定。",
            "品牌與產品名稱一開始就拼寫正確：Voxis 現在內建術語表，你自己的術語已移到「設定 › 翻譯」。",
            "更新說明現在在應用程式內：每次更新後，你會用自己的語言看到一次變更內容。",
        ],
        "pl": [
            "Wybierz, czy przetłumaczony głos ma brzmieć kobieco czy męsko — z osobnym ustawieniem głosu, którym słyszy Cię druga osoba w trybie spotkania.",
            "Nazwy marek i produktów są od razu pisane poprawnie: Voxis zawiera teraz gotową listę terminów, a Twoje własne terminy trafiły do Ustawienia › Tłumaczenie.",
            "Informacje o zmianach są teraz w aplikacji: po każdej aktualizacji raz zobaczysz, co się zmieniło, w swoim języku.",
        ],
        "it": [
            "Scegli se la voce tradotta suona femminile o maschile, con un'impostazione separata per la voce con cui l'altra persona ti sente in modalità Riunione.",
            "I nomi di marchi e prodotti sono scritti correttamente sin da subito: Voxis include ora un elenco di termini pronto e i tuoi termini si trovano in Impostazioni › Traduzione.",
            "Le novità ora sono nell'app: dopo ogni aggiornamento vedi una volta che cosa è cambiato, nella tua lingua.",
        ],
        "id": [
            "Pilih apakah suara terjemahan terdengar perempuan atau laki-laki — dengan pengaturan terpisah untuk suara yang didengar orang lain sebagai kamu di mode Rapat.",
            "Nama merek dan produk langsung ditulis dengan benar: Voxis kini membawa daftar istilah siap pakai, dan istilahmu sendiri pindah ke Pengaturan › Terjemahan.",
            "Catatan rilis kini ada di dalam aplikasi: setiap selesai memperbarui, kamu melihat sekali apa yang berubah dalam bahasamu.",
        ],
        "nl": [
            "Kies of de vertaalde stem vrouwelijk of mannelijk klinkt — met een aparte instelling voor de stem waarin de ander jou hoort in de vergadermodus.",
            "Merk- en productnamen worden meteen goed geschreven: Voxis bevat nu een kant-en-klare termenlijst en je eigen termen staan in Instellingen › Vertaling.",
            "Release-opmerkingen staan nu in de app: na elke update zie je één keer wat er is veranderd, in je eigen taal.",
        ],
        "vi": [
            "Chọn giọng dịch là nữ hay nam — kèm thiết lập riêng cho giọng mà người kia nghe thấy bạn trong chế độ Họp.",
            "Tên thương hiệu và sản phẩm được viết đúng ngay từ đầu: Voxis nay có sẵn danh sách thuật ngữ, còn thuật ngữ của bạn chuyển sang Cài đặt › Dịch.",
            "Ghi chú phát hành giờ nằm trong ứng dụng: sau mỗi lần cập nhật, bạn xem một lần những gì đã thay đổi bằng ngôn ngữ của mình.",
        ],
        "th": [
            "เลือกได้ว่าเสียงแปลจะเป็นเสียงผู้หญิงหรือผู้ชาย พร้อมการตั้งค่าแยกสำหรับเสียงที่อีกฝ่ายได้ยินเป็นคุณในโหมดประชุม",
            "ชื่อแบรนด์และชื่อสินค้าสะกดถูกตั้งแต่แรก: Voxis มีรายการคำศัพท์พร้อมใช้มาให้แล้ว และคำศัพท์ของคุณย้ายไปที่ ตั้งค่า › การแปล",
            "บันทึกรุ่นอยู่ในแอปแล้ว: หลังอัปเดตทุกครั้ง คุณจะเห็นสิ่งที่เปลี่ยนไปหนึ่งครั้งในภาษาของคุณ",
        ],
        "ro": [
            "Alege dacă vocea tradusă sună feminin sau masculin — cu o setare separată pentru vocea în care cealaltă persoană te aude în modul Întâlnire.",
            "Numele de mărci și produse sunt scrise corect din start: Voxis include acum o listă de termeni gata făcută, iar termenii tăi au trecut în Setări › Traducere.",
            "Notele de versiune sunt acum în aplicație: după fiecare actualizare vezi o dată ce s-a schimbat, în limba ta.",
        ],
        "hi": [
            "तय करें कि अनुवादित आवाज़ महिला जैसी हो या पुरुष जैसी — मीटिंग मोड में सामने वाला आपको जिस आवाज़ में सुनता है, उसकी सेटिंग अलग है।",
            "ब्रांड और उत्पाद के नाम शुरू से ही सही लिखे जाते हैं: Voxis के साथ अब तैयार शब्द-सूची आती है, और आपके अपने शब्द सेटिंग्स › अनुवाद में चले गए हैं।",
            "रिलीज़ नोट्स अब ऐप में हैं: हर अपडेट के बाद आप एक बार अपनी भाषा में देखेंगे कि क्या बदला।",
        ],
        "hu": [
            "Válaszd ki, hogy a lefordított hang nőies vagy férfias legyen — külön beállítással arra a hangra, amelyen a másik fél hall téged megbeszélés módban.",
            "A márka- és terméknevek elsőre is helyesen íródnak: a Voxis mostantól kész kifejezéslistát hoz magával, a saját kifejezéseid pedig a Beállítások › Fordítás alá kerültek.",
            "A verziójegyzet mostantól az alkalmazásban van: minden frissítés után egyszer látod, mi változott, a saját nyelveden.",
        ],
        "sv": [
            "Välj om den översatta rösten ska låta kvinnlig eller manlig — med en separat inställning för rösten som den andra personen hör dig i, i mötesläget.",
            "Varumärkes- och produktnamn stavas rätt från början: Voxis har nu en färdig termlista och dina egna termer finns under Inställningar › Översättning.",
            "Versionsnyheterna finns nu i appen: efter varje uppdatering ser du en gång vad som ändrats, på ditt språk.",
        ],
        "sr": [
            "Izaberi da li prevedeni glas zvuči kao ženski ili muški — uz posebno podešavanje za glas kojim te druga osoba sluša u režimu sastanka.",
            "Imena brendova i proizvoda odmah se pišu ispravno: Voxis sada dolazi sa gotovim spiskom pojmova, a tvoji sopstveni pojmovi su prešli u Podešavanja › Prevod.",
            "Beleške o verziji su sada u aplikaciji: posle svakog ažuriranja jednom vidiš šta se promenilo, na svom jeziku.",
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
