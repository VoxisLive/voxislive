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
    "1.0.58": {
        "en": [
            "Fixed an issue where the free trial could be incorrectly flagged as already used on some computers, even for a brand-new account.",
            "Fixed a rare crash on launch caused by corrupted settings data.",
            "Various security hardening improvements to how the app handles connections and login sessions.",
        ],
        "tr": [
            "Bazı bilgisayarlarda, ücretsiz deneme süresinin yepyeni bir hesapta bile daha önce kullanılmış gibi yanlış işaretlenmesine neden olan bir sorun giderildi.",
            "Bozuk ayar verisinden kaynaklanan nadir bir başlangıç çökmesi giderildi.",
            "Uygulamanın bağlantıları ve oturum açma işlemlerini ele alış biçiminde çeşitli güvenlik sıkılaştırmaları yapıldı.",
        ],
        "de": [
            "Ein Problem behoben, bei dem die kostenlose Testversion auf manchen Computern fälschlicherweise als bereits verwendet markiert wurde, selbst bei einem brandneuen Konto.",
            "Einen seltenen Absturz beim Start behoben, der durch beschädigte Einstellungsdaten verursacht wurde.",
            "Verschiedene Sicherheitsverbesserungen bei der Handhabung von Verbindungen und Anmeldesitzungen.",
        ],
        "fr": [
            "Correction d'un problème où l'essai gratuit pouvait être signalé à tort comme déjà utilisé sur certains ordinateurs, même pour un tout nouveau compte.",
            "Correction d'un plantage rare au démarrage causé par des données de paramètres corrompues.",
            "Diverses améliorations de sécurité dans la gestion des connexions et des sessions de connexion.",
        ],
        "es": [
            "Se corrigió un problema por el que la prueba gratuita podía marcarse incorrectamente como ya utilizada en algunos equipos, incluso con una cuenta completamente nueva.",
            "Se corrigió un fallo poco frecuente al iniciar la aplicación causado por datos de configuración dañados.",
            "Diversas mejoras de seguridad en la forma en que la aplicación gestiona las conexiones y las sesiones de inicio de sesión.",
        ],
        "pt": [
            "Corrigido um problema em que o período de teste gratuito podia ser marcado incorretamente como já utilizado em alguns computadores, mesmo para uma conta totalmente nova.",
            "Corrigida uma falha rara na inicialização causada por dados de configuração corrompidos.",
            "Diversas melhorias de segurança na forma como o app lida com conexões e sessões de login.",
        ],
        "it": [
            "Risolto un problema per cui la prova gratuita poteva essere erroneamente segnalata come già utilizzata su alcuni computer, anche con un account del tutto nuovo.",
            "Risolto un raro arresto anomalo all'avvio causato da dati di configurazione danneggiati.",
            "Diversi miglioramenti di sicurezza nella gestione delle connessioni e delle sessioni di accesso.",
        ],
        "nl": [
            "Een probleem opgelost waarbij de gratis proefperiode op sommige computers onterecht als al gebruikt werd gemarkeerd, zelfs bij een gloednieuw account.",
            "Een zeldzame crash bij het opstarten, veroorzaakt door beschadigde instellingengegevens, opgelost.",
            "Diverse beveiligingsverbeteringen in hoe de app verbindingen en inlogsessies verwerkt.",
        ],
        "pl": [
            "Naprawiono problem, przez który darmowy okres próbny mógł zostać błędnie oznaczony jako już wykorzystany na niektórych komputerach, nawet w przypadku zupełnie nowego konta.",
            "Naprawiono rzadką awarię przy uruchamianiu spowodowaną uszkodzonymi danymi ustawień.",
            "Wprowadzono różne usprawnienia bezpieczeństwa w sposobie obsługi połączeń i sesji logowania.",
        ],
        "cs": [
            "Opravena chyba, kdy mohla být bezplatná zkušební verze na některých počítačích nesprávně označena jako již využitá, a to i u zcela nového účtu.",
            "Opravena vzácná chyba při spuštění způsobená poškozenými daty nastavení.",
            "Různá bezpečnostní vylepšení ve způsobu, jakým aplikace zpracovává připojení a přihlašovací relace.",
        ],
        "hu": [
            "Kijavítottunk egy hibát, amely miatt az ingyenes próbaidőszak egyes számítógépeken tévesen már felhasználtként jelenhetett meg, még egy vadonatúj fiók esetén is.",
            "Kijavítottunk egy ritka, sérült beállítási adatok okozta indítási összeomlást.",
            "Több biztonsági fejlesztés történt az alkalmazás kapcsolat- és bejelentkezési munkamenet-kezelésében.",
        ],
        "ro": [
            "A fost remediată o problemă prin care perioada de probă gratuită putea fi marcată incorect ca fiind deja utilizată pe unele computere, chiar și pentru un cont complet nou.",
            "A fost remediată o blocare rară la pornire, cauzată de date de configurare corupte.",
            "Diverse îmbunătățiri de securitate în modul în care aplicația gestionează conexiunile și sesiunile de autentificare.",
        ],
        "sv": [
            "Åtgärdat ett problem där den kostnadsfria provperioden felaktigt kunde markeras som redan använd på vissa datorer, även för ett helt nytt konto.",
            "Åtgärdad en sällsynt krasch vid start orsakad av skadade inställningsdata.",
            "Olika säkerhetsförbättringar i hur appen hanterar anslutningar och inloggningssessioner.",
        ],
        "sr": [
            "Ispravljen problem zbog kog je besplatna probna verzija na nekim računarima mogla biti pogrešno označena kao već iskorišćena, čak i za potpuno nov nalog.",
            "Ispravljeno retko rušenje pri pokretanju izazvano oštećenim podacima podešavanja.",
            "Razna bezbednosna poboljšanja u načinu na koji aplikacija rukuje vezama i sesijama prijave.",
        ],
        "ru": [
            "Исправлена проблема, из-за которой бесплатный пробный период на некоторых компьютерах мог ошибочно помечаться как уже использованный, даже для совершенно нового аккаунта.",
            "Исправлен редкий сбой при запуске, вызванный повреждёнными данными настроек.",
            "Различные улучшения безопасности в обработке соединений и сеансов входа в приложении.",
        ],
        "ja": [
            "一部のパソコンで、まったく新しいアカウントであっても無料トライアルがすでに使用済みと誤って判定される問題を修正しました。",
            "設定データの破損が原因で起動時にまれに発生していたクラッシュを修正しました。",
            "アプリの接続処理とログインセッションの扱いに関するセキュリティを強化しました。",
        ],
        "ko": [
            "일부 컴퓨터에서 완전히 새로운 계정임에도 무료 체험판이 이미 사용된 것으로 잘못 표시되던 문제를 수정했습니다.",
            "손상된 설정 데이터로 인해 드물게 발생하던 실행 시 충돌 문제를 수정했습니다.",
            "앱이 연결 및 로그인 세션을 처리하는 방식에 대한 다양한 보안 강화가 이루어졌습니다.",
        ],
        "zh": [
            "修复了部分电脑上免费试用可能被错误标记为已使用的问题，即使是全新账户也会受影响。",
            "修复了因设置数据损坏导致的偶发启动崩溃问题。",
            "对应用处理连接和登录会话的方式进行了多项安全加固。",
        ],
        "zh-Hant": [
            "修復了部分電腦上免費試用可能被錯誤標記為已使用的問題，即使是全新帳戶也會受影響。",
            "修復了因設定資料損毀導致的偶發啟動當機問題。",
            "對應用程式處理連線和登入工作階段的方式進行了多項安全強化。",
        ],
        "hi": [
            "एक समस्या ठीक की गई जिसके कारण कुछ कंप्यूटरों पर मुफ्‍त ट्रायल को गलत तरीके से पहले से इस्तेमाल किया हुआ दिखाया जा सकता था, भले ही खाता बिल्‍कुल नया हो।",
            "खराब सेटिंग्‍स डेटा के कारण शुरू होते समय होने वाली एक दुर्लभ क्रैश समस्या ठीक की गई।",
            "ऐप के कनेक्‍शन और लॉगिन सेशन को संभालने के तरीके में कई सुरक्षा सुधार किए गए।",
        ],
        "id": [
            "Memperbaiki masalah di mana uji coba gratis dapat salah ditandai sebagai sudah digunakan di beberapa komputer, bahkan untuk akun yang benar-benar baru.",
            "Memperbaiki crash langka saat memulai yang disebabkan oleh data pengaturan yang rusak.",
            "Berbagai peningkatan keamanan dalam cara aplikasi menangani koneksi dan sesi login.",
        ],
        "vi": [
            "Đã khắc phục sự cố khiến bản dùng thử miễn phí có thể bị đánh dấu sai là đã sử dụng trên một số máy tính, ngay cả với tài khoản hoàn toàn mới.",
            "Đã khắc phục lỗi hiếm gặp gây treo ứng dụng khi khởi động do dữ liệu cài đặt bị hỏng.",
            "Nhiều cải tiến bảo mật trong cách ứng dụng xử lý kết nối và phiên đăng nhập.",
        ],
        "th": [
            "แก้ไขปัญหาที่ทดลองใช้ฟรีอาจถูกทำเครื่องหมายผิดพลาดว่าใช้ไปแล้วบนคอมพิวเตอร์บางเครื่อง แม้จะเป็นบัญชีใหม่ทั้งหมดก็ตาม",
            "แก้ไขปัญหาแอปขัดข้องที่พบได้ยากขณะเริ่มทำงาน ซึ่งเกิดจากข้อมูลการตั้งค่าที่เสียหาย",
            "ปรับปรุงความปลอดภัยหลายจุดในวิธีที่แอปจัดการการเชื่อมต่อและเซสชันการเข้าสู่ระบบ",
        ],
    },
    "1.0.59": {
        "en": [
            "Fixed a rare case where a session could get stuck with no audio and no error message — it now recovers automatically instead of requiring a manual restart.",
        ],
        "tr": [
            "Oturumun bazen sessiz kalıp hiçbir hata göstermeden takılı kalabilmesi sorunu giderildi — artık elle yeniden başlatmaya gerek kalmadan kendiliğinden toparlanıyor.",
        ],
        "de": [
            "Ein seltener Fall behoben, bei dem eine Sitzung ohne Ton und ohne Fehlermeldung hängen bleiben konnte — sie erholt sich jetzt automatisch, statt einen manuellen Neustart zu erfordern.",
        ],
        "fr": [
            "Correction d'un cas rare où une session pouvait rester bloquée sans son ni message d'erreur — elle se rétablit désormais automatiquement, sans nécessiter de redémarrage manuel.",
        ],
        "es": [
            "Se corrigió un caso poco frecuente en el que una sesión podía quedarse bloqueada sin audio ni mensaje de error — ahora se recupera automáticamente en lugar de requerir un reinicio manual.",
        ],
        "pt": [
            "Corrigido um caso raro em que uma sessão podia travar sem áudio e sem mensagem de erro — agora ela se recupera automaticamente em vez de exigir um reinício manual.",
        ],
        "it": [
            "Risolto un caso raro in cui una sessione poteva bloccarsi senza audio e senza messaggi di errore — ora si ripristina automaticamente invece di richiedere un riavvio manuale.",
        ],
        "nl": [
            "Een zeldzaam geval opgelost waarbij een sessie kon vastlopen zonder geluid en zonder foutmelding — deze herstelt nu automatisch in plaats van een handmatige herstart te vereisen.",
        ],
        "pl": [
            "Naprawiono rzadki przypadek, w którym sesja mogła się zawiesić bez dźwięku i bez komunikatu o błędzie — teraz wznawia się automatycznie zamiast wymagać ręcznego ponownego uruchomienia.",
        ],
        "cs": [
            "Opraven vzácný případ, kdy se relace mohla zaseknout bez zvuku a bez chybové zprávy — nyní se automaticky obnoví, aniž by bylo nutné ruční restartování.",
        ],
        "hu": [
            "Kijavítottunk egy ritka esetet, amikor a munkamenet hang és hibaüzenet nélkül leállhatott — mostantól automatikusan helyreáll, kézi újraindítás nélkül.",
        ],
        "ro": [
            "A fost remediat un caz rar în care o sesiune putea rămâne blocată fără sunet și fără mesaj de eroare — acum se reface automat, fără a necesita o repornire manuală.",
        ],
        "sv": [
            "Åtgärdat ett sällsynt fall där en session kunde fastna utan ljud och utan felmeddelande — den återhämtar sig nu automatiskt istället för att kräva en manuell omstart.",
        ],
        "sr": [
            "Ispravljen redak slučaj u kome je sesija mogla da se zaglavi bez zvuka i bez poruke o grešci — sada se automatski oporavlja umesto da zahteva ručno ponovno pokretanje.",
        ],
        "ru": [
            "Исправлен редкий случай, когда сеанс мог зависнуть без звука и без сообщения об ошибке — теперь он восстанавливается автоматически, без необходимости вручную перезапускать сеанс.",
        ],
        "ja": [
            "音声も出ずエラーメッセージも表示されないままセッションが停止してしまう、まれな問題を修正しました。手動での再起動を行わなくても自動的に回復するようになりました。",
        ],
        "ko": [
            "오디오도 오류 메시지도 없이 세션이 멈춰버리는 드문 문제를 수정했습니다 — 이제 수동으로 다시 시작하지 않아도 자동으로 복구됩니다.",
        ],
        "zh": [
            "修复了会话偶尔会在没有声音、也没有错误提示的情况下卡住的问题——现在无需手动重启即可自动恢复。",
        ],
        "zh-Hant": [
            "修復了工作階段偶爾會在沒有聲音、也沒有錯誤提示的情況下卡住的問題——現在無需手動重新啟動即可自動恢復。",
        ],
        "hi": [
            "एक दुर्लभ समस्या ठीक की गई जिसमें सेशन बिना किसी ऑडियो और बिना किसी एरर मैसेज के अटक सकता था — अब यह बिना मैन्युअल रीस्टार्ट किए अपने आप ठीक हो जाता है।",
        ],
        "id": [
            "Memperbaiki kasus langka di mana sesi dapat macet tanpa audio dan tanpa pesan error — kini pulih secara otomatis tanpa perlu memulai ulang secara manual.",
        ],
        "vi": [
            "Đã khắc phục một trường hợp hiếm gặp khiến phiên làm việc có thể bị treo mà không có âm thanh và không có thông báo lỗi — giờ đây ứng dụng sẽ tự động khôi phục thay vì phải khởi động lại thủ công.",
        ],
        "th": [
            "แก้ไขกรณีที่พบได้ยากซึ่งเซสชันอาจค้างโดยไม่มีเสียงและไม่มีข้อความแจ้งข้อผิดพลาด — ตอนนี้ระบบจะกู้คืนโดยอัตโนมัติแทนที่จะต้องรีสตาร์ทด้วยตนเอง",
        ],
    },
    "1.0.60": {
        "en": [
            "You can now hear the translation in a voice close to the original speaker's own — turn on \"Dubbing Voice\" in Settings › Translation.",
            "History got three new tools: star sessions to keep them from being cleaned up automatically, edit the saved text (exports pick up your fix), and generate a short AI summary of any session (paid plans).",
            "A new button lets you skip the sentence currently playing without stopping the whole session.",
            "Invite a friend from Settings › Membership — you both earn free minutes when they join.",
            "The Terms list in Settings › Translation can now be imported straight from a text file.",
        ],
        "tr": [
            "Artık çeviriyi orijinal konuşmacının kendi sesine benzer bir sesle dinleyebilirsiniz — Ayarlar › Çeviri sekmesindeki \"Dublaj Sesi\" ile açabilirsiniz.",
            "Geçmiş paneline üç yeni araç eklendi: oturumları yıldızlayıp otomatik temizlenmekten koruyun, kaydedilen metni düzenleyin (dışa aktarımlar düzeltmenizi otomatik yansıtır), ve herhangi bir oturumun kısa bir AI özetini oluşturun (ücretli planlar).",
            "Yeni bir buton, oturumu durdurmadan o an çalan çeviri cümlesini atlamanızı sağlıyor.",
            "Ayarlar › Üyelik sekmesinden bir arkadaşınızı davet edin — katıldığında ikiniz de ücretsiz dakika kazanırsınız.",
            "Ayarlar › Çeviri sekmesindeki Terimler listesi artık doğrudan bir metin dosyasından içe aktarılabiliyor.",
        ],
        "de": [
            "Sie können die Übersetzung jetzt in einer Stimme hören, die der des Originalsprechers ähnelt — aktivierbar unter Einstellungen › Übersetzung („Synchronstimme“).",
            "Der Verlauf hat drei neue Werkzeuge erhalten: Sitzungen markieren, damit sie nicht automatisch bereinigt werden, den gespeicherten Text bearbeiten (Exporte übernehmen Ihre Korrektur), und eine kurze KI-Zusammenfassung jeder Sitzung erstellen (kostenpflichtige Pläne).",
            "Eine neue Schaltfläche lässt Sie den gerade abgespielten Satz überspringen, ohne die ganze Sitzung zu beenden.",
            "Laden Sie einen Freund über Einstellungen › Mitgliedschaft ein — Sie beide erhalten kostenlose Minuten, wenn er beitritt.",
            "Die Begriffsliste unter Einstellungen › Übersetzung kann jetzt direkt aus einer Textdatei importiert werden.",
        ],
        "cs": [
            "Nyní si můžete poslechnout překlad hlasem podobným hlasu původního mluvčího — zapnete ho v Nastavení › Překlad („Dabovaný hlas“).",
            "Historie získala tři nové nástroje: označte relace hvězdičkou, aby nebyly automaticky vymazány, upravte uložený text (exporty automaticky převezmou vaši opravu) a vytvořte krátké AI shrnutí libovolné relace (placené plány).",
            "Nové tlačítko umožňuje přeskočit právě přehrávanou větu, aniž byste museli zastavit celou relaci.",
            "Pozvěte přítele z Nastavení › Členství — oba získáte volné minuty, jakmile se připojí.",
            "Seznam pojmů v Nastavení › Překlad lze nyní importovat přímo z textového souboru.",
        ],
        "fr": [
            "Vous pouvez désormais entendre la traduction avec une voix proche de celle du locuteur original — activez-la dans Paramètres › Traduction (« Voix de doublage »).",
            "L'historique a trois nouveaux outils : marquez vos sessions comme favorites pour éviter qu'elles ne soient nettoyées automatiquement, modifiez le texte enregistré (les exports reprennent votre correction), et générez un court résumé IA de n'importe quelle session (forfaits payants).",
            "Un nouveau bouton permet de passer la phrase en cours de lecture sans arrêter toute la session.",
            "Invitez un ami depuis Paramètres › Abonnement — vous gagnez tous les deux des minutes gratuites quand il rejoint.",
            "La liste des termes dans Paramètres › Traduction peut désormais être importée directement depuis un fichier texte.",
        ],
        "es": [
            "Ahora puedes escuchar la traducción con una voz parecida a la del hablante original — actívala en Configuración › Traducción (“Voz de doblaje”).",
            "El historial tiene tres herramientas nuevas: destaca sesiones para evitar que se limpien automáticamente, edita el texto guardado (las exportaciones recogen tu corrección) y genera un breve resumen con IA de cualquier sesión (planes de pago).",
            "Un nuevo botón te permite saltar la frase que se está reproduciendo sin detener toda la sesión.",
            "Invita a un amigo desde Configuración › Membresía — ambos ganáis minutos gratis cuando se una.",
            "La lista de términos en Configuración › Traducción ahora se puede importar directamente desde un archivo de texto.",
        ],
        "pt": [
            "Agora você pode ouvir a tradução numa voz semelhante à do orador original — ative-a em Definições › Tradução (“Voz de dublagem”).",
            "O Histórico ganhou três novas ferramentas: marque sessões com estrela para evitar que sejam limpas automaticamente, edite o texto guardado (as exportações captam a sua correção) e gere um breve resumo com IA de qualquer sessão (planos pagos).",
            "Um novo botão permite saltar a frase que está a tocar sem parar a sessão inteira.",
            "Convide um amigo em Definições › Assinatura — ambos ganham minutos grátis quando ele se juntar.",
            "A lista de termos em Definições › Tradução agora pode ser importada diretamente de um ficheiro de texto.",
        ],
        "it": [
            "Ora puoi ascoltare la traduzione con una voce simile a quella del parlante originale — attivala in Impostazioni › Traduzione (“Voce del doppiaggio”).",
            "Lo Storico ha tre nuovi strumenti: contrassegna le sessioni come preferite per evitare che vengano ripulite automaticamente, modifica il testo salvato (le esportazioni recepiscono la tua correzione) e genera un breve riepilogo IA di qualsiasi sessione (piani a pagamento).",
            "Un nuovo pulsante ti permette di saltare la frase attualmente in riproduzione senza interrompere l'intera sessione.",
            "Invita un amico da Impostazioni › Abbonamento — entrambi guadagnate minuti gratuiti quando si iscrive.",
            "L'elenco dei termini in Impostazioni › Traduzione ora può essere importato direttamente da un file di testo.",
        ],
        "nl": [
            "Je kunt de vertaling nu horen in een stem die lijkt op die van de oorspronkelijke spreker — zet 'm aan bij Instellingen › Vertaling (“Nasynchronisatiestem”).",
            "Geschiedenis heeft drie nieuwe tools gekregen: markeer sessies met een ster zodat ze niet automatisch worden opgeruimd, bewerk de opgeslagen tekst (exports nemen je correctie automatisch over) en genereer een korte AI-samenvatting van elke sessie (betaalde abonnementen).",
            "Met een nieuwe knop kun je de zin die nu wordt afgespeeld overslaan zonder de hele sessie te stoppen.",
            "Nodig een vriend uit via Instellingen › Abonnement — jullie verdienen allebei gratis minuten zodra hij/zij zich aansluit.",
            "De termenlijst in Instellingen › Vertaling kan nu rechtstreeks uit een tekstbestand worden geïmporteerd.",
        ],
        "pl": [
            "Teraz możesz usłyszeć tłumaczenie głosem zbliżonym do głosu oryginalnego mówcy — włącz go w Ustawienia › Tłumaczenie („Głos dubbingu”).",
            "Historia zyskała trzy nowe narzędzia: oznaczaj sesje gwiazdką, aby nie były automatycznie usuwane, edytuj zapisany tekst (eksporty automatycznie uwzględniają Twoją poprawkę) oraz generuj krótkie podsumowanie AI dowolnej sesji (plany płatne).",
            "Nowy przycisk pozwala pominąć aktualnie odtwarzane zdanie bez zatrzymywania całej sesji.",
            "Zaproś znajomego z Ustawienia › Subskrypcja — oboje zyskujecie darmowe minuty, gdy dołączy.",
            "Listę terminów w Ustawienia › Tłumaczenie można teraz zaimportować bezpośrednio z pliku tekstowego.",
        ],
        "ja": [
            "元の話者本人に近い声で翻訳を聴けるようになりました — 設定 › 翻訳の「吹き替え音声」でオンにできます。",
            "履歴に3つの新機能が追加されました：セッションをスターで保存して自動削除を防ぐ、保存されたテキストを編集する（エクスポートにも修正が反映されます）、任意のセッションの短いAI要約を作成する（有料プラン）。",
            "新しいボタンで、セッション全体を止めずに現在再生中の文をスキップできます。",
            "設定 › メンバーシップから友達を招待しましょう — 友達が参加すると、お互いに無料の分数がもらえます。",
            "設定 › 翻訳の用語リストは、テキストファイルから直接インポートできるようになりました。",
        ],
        "ko": [
            "이제 원본 화자 본인과 비슷한 목소리로 번역을 들을 수 있습니다 — 설정 › 번역의 “더빙 음성”에서 켜세요.",
            "기록에 세 가지 새로운 도구가 추가되었습니다: 세션을 즐겨찾기로 표시해 자동 정리되지 않도록 하기, 저장된 텍스트 편집하기(내보내기에도 수정 사항이 반영됨), 모든 세션의 짧은 AI 요약 생성하기(유료 플랜).",
            "새 버튼으로 전체 세션을 중지하지 않고 현재 재생 중인 문장을 건너뛸 수 있습니다.",
            "설정 › 멤버십에서 친구를 초대하세요 — 친구가 가입하면 둘 다 무료 분을 받습니다.",
            "설정 › 번역의 용어 목록을 이제 텍스트 파일에서 바로 가져올 수 있습니다.",
        ],
        "ru": [
            "Теперь перевод можно слушать голосом, похожим на голос оригинального говорящего — включите в Настройки › Перевод («Голос дубляжа»).",
            "В истории появилось три новых инструмента: отмечайте сеансы звёздочкой, чтобы они не удалялись автоматически, редактируйте сохранённый текст (экспорт учитывает вашу правку) и создавайте краткое резюме любого сеанса с помощью ИИ (платные тарифы).",
            "Новая кнопка позволяет пропустить текущее произносимое предложение без остановки всего сеанса.",
            "Приглашайте друга из Настройки › Подписка — вы оба получите бесплатные минуты, когда он присоединится.",
            "Список терминов в Настройки › Перевод теперь можно импортировать прямо из текстового файла.",
        ],
        "zh": [
            "现在可以以接近原始说话人本人的声音收听译文了——可在 设置 › 翻译 中的“配音声音”开关开启。",
            "历史记录新增三项工具：为会话加星标以避免被自动清理、编辑已保存的文本（导出会自动使用你的修改）、为任意会话生成简短的 AI 摘要（付费方案）。",
            "新增按钮可让你跳过当前正在播放的句子，而无需停止整个会话。",
            "在 设置 › 会员 中邀请好友——好友加入后你们双方都会获得免费分钟数。",
            "设置 › 翻译 中的术语列表现在可以直接从文本文件导入。",
        ],
        "zh-Hant": [
            "現在可以以接近原始說話者本人的聲音聆聽譯文了——可在 設定 › 翻譯 中的「配音聲音」開關開啟。",
            "歷史記錄新增三項工具：為工作階段加星標以避免被自動清除、編輯已儲存的文字（匯出會自動採用你的修改）、為任意工作階段產生簡短的 AI 摘要（付費方案）。",
            "新增按鈕可讓你跳過目前正在播放的句子，而不必停止整個工作階段。",
            "在 設定 › 會員 中邀請朋友——朋友加入後你們雙方都會獲得免費分鐘數。",
            "設定 › 翻譯 中的術語清單現在可以直接從文字檔匯入。",
        ],
        "hi": [
            "अब आप अनुवाद को मूल वक्ता की अपनी आवाज़ जैसी आवाज़ में सुन सकते हैं — इसे सेटिंग्स › अनुवाद में \"डबिंग आवाज़\" से चालू करें।",
            "इतिहास में तीन नए टूल जुड़े: सत्रों को तारांकित करें ताकि वे अपने आप साफ़ न हों, सहेजे गए टेक्स्ट को संपादित करें (निर्यात आपके सुधार को अपने आप शामिल करते हैं), और किसी भी सत्र का छोटा AI सारांश बनाएं (भुगतान वाली योजनाएं)।",
            "एक नया बटन आपको पूरे सत्र को रोके बिना अभी चल रहे वाक्य को छोड़ने देता है।",
            "सेटिंग्स › सदस्यता से किसी दोस्त को आमंत्रित करें — जुड़ने पर आप दोनों को मुफ़्त मिनट मिलते हैं।",
            "सेटिंग्स › अनुवाद में शब्द सूची को अब सीधे टेक्स्ट फ़ाइल से आयात किया जा सकता है।",
        ],
        "id": [
            "Kini Anda dapat mendengar terjemahan dengan suara yang mirip suara pembicara asli — aktifkan di Pengaturan › Terjemahan (“Suara Sulih Suara”).",
            "Riwayat mendapat tiga alat baru: beri bintang pada sesi agar tidak dibersihkan otomatis, edit teks yang disimpan (ekspor otomatis mengikuti perbaikan Anda), dan buat ringkasan AI singkat untuk sesi mana pun (paket berbayar).",
            "Tombol baru memungkinkan Anda melewati kalimat yang sedang diputar tanpa menghentikan seluruh sesi.",
            "Undang teman dari Pengaturan › Keanggotaan — Anda berdua mendapat menit gratis saat mereka bergabung.",
            "Daftar Istilah di Pengaturan › Terjemahan kini dapat diimpor langsung dari berkas teks.",
        ],
        "vi": [
            "Giờ đây bạn có thể nghe bản dịch bằng giọng gần giống giọng của người nói gốc — bật trong Cài đặt › Dịch (“Giọng Lồng Tiếng”).",
            "Lịch sử có thêm ba công cụ mới: đánh dấu sao cho phiên để tránh bị tự động dọn dẹp, chỉnh sửa văn bản đã lưu (bản xuất tự động áp dụng chỉnh sửa của bạn), và tạo tóm tắt AI ngắn cho bất kỳ phiên nào (gói trả phí).",
            "Một nút mới cho phép bạn bỏ qua câu đang phát mà không cần dừng toàn bộ phiên.",
            "Mời bạn bè từ Cài đặt › Gói thành viên — cả hai đều nhận được phút miễn phí khi họ tham gia.",
            "Danh sách Thuật ngữ trong Cài đặt › Dịch giờ đây có thể được nhập trực tiếp từ tệp văn bản.",
        ],
        "th": [
            "ตอนนี้คุณสามารถฟังคำแปลด้วยเสียงที่ใกล้เคียงกับผู้พูดต้นฉบับได้แล้ว — เปิดได้ที่ การตั้งค่า › การแปล (“เสียงพากย์”)",
            "ประวัติมีเครื่องมือใหม่สามอย่าง: ติดดาวเซสชันเพื่อไม่ให้ถูกล้างข้อมูลอัตโนมัติ แก้ไขข้อความที่บันทึกไว้ (การส่งออกจะใช้การแก้ไขของคุณโดยอัตโนมัติ) และสร้างสรุปโดย AI แบบสั้นสำหรับเซสชันใดก็ได้ (แพ็กเกจแบบชำระเงิน)",
            "ปุ่มใหม่ช่วยให้คุณข้ามประโยคที่กำลังเล่นอยู่ได้โดยไม่ต้องหยุดเซสชันทั้งหมด",
            "เชิญเพื่อนจาก การตั้งค่า › สมาชิก — ทั้งคุณและเพื่อนจะได้รับนาทีฟรีเมื่อเพื่อนเข้าร่วม",
            "รายการคำศัพท์ใน การตั้งค่า › การแปล ตอนนี้สามารถนำเข้าได้โดยตรงจากไฟล์ข้อความ",
        ],
        "ro": [
            "Acum poți asculta traducerea cu o voce apropiată de cea a vorbitorului original — o activezi din Setări › Traducere („Voce de Dublaj”).",
            "Istoricul a primit trei instrumente noi: marchează sesiunile cu stea pentru a evita curățarea automată, editează textul salvat (exporturile preiau automat corectura ta) și generează un scurt rezumat AI al oricărei sesiuni (planuri plătite).",
            "Un buton nou îți permite să sari peste propoziția redată în prezent fără a opri întreaga sesiune.",
            "Invită un prieten din Setări › Abonament — amândoi câștigați minute gratuite când se alătură.",
            "Lista de Termeni din Setări › Traducere poate fi acum importată direct dintr-un fișier text.",
        ],
        "hu": [
            "Mostantól az eredeti beszélő hangjához közeli hangon is hallgathatod a fordítást — bekapcsolhatod a Beállítások › Fordítás alatt („Szinkronhang”).",
            "Az Előzmények három új eszközzel bővült: csillagozd meg a munkameneteket, hogy ne törlődjenek automatikusan, szerkeszd a mentett szöveget (az exportok automatikusan átveszik a javításodat), és készíts rövid AI-összefoglalót bármelyik munkamenetről (fizetős csomagok).",
            "Egy új gombbal kihagyhatod az éppen lejátszott mondatot anélkül, hogy leállítanád az egész munkamenetet.",
            "Hívj meg egy barátot a Beállítások › Tagság alól — mindketten ingyenes perceket kaptok, amikor csatlakozik.",
            "A Beállítások › Fordítás alatti kifejezéslistát mostantól közvetlenül szövegfájlból is importálhatod.",
        ],
        "sv": [
            "Du kan nu höra översättningen i en röst som liknar den ursprungliga talarens — slå på den i Inställningar › Översättning (”Dubbningsröst”).",
            "Historik fick tre nya verktyg: stjärnmärk sessioner så att de inte rensas automatiskt, redigera den sparade texten (exporter tar automatiskt med din rättelse), och skapa en kort AI-sammanfattning av valfri session (betalplaner).",
            "En ny knapp låter dig hoppa över meningen som spelas upp just nu utan att stoppa hela sessionen.",
            "Bjud in en vän från Inställningar › Medlemskap — ni får båda gratis minuter när hen går med.",
            "Termlistan i Inställningar › Översättning kan nu importeras direkt från en textfil.",
        ],
        "sr": [
            "Sada možete da čujete prevod glasom sličnim glasu izvornog govornika — uključite ga u Podešavanja › Prevod („Glas Sinhronizacije“).",
            "Istorija je dobila tri nova alata: označite sesije zvezdicom da se ne bi automatski brisale, izmenite sačuvani tekst (izvoz automatski koristi vašu ispravku) i napravite kratak AI rezime bilo koje sesije (plaćeni planovi).",
            "Novo dugme vam omogućava da preskočite rečenicu koja se trenutno reprodukuje bez zaustavljanja cele sesije.",
            "Pozovite prijatelja iz Podešavanja › Članstvo — oboje dobijate besplatne minute kada se pridruži.",
            "Spisak pojmova u Podešavanja › Prevod sada se može uvesti direktno iz tekstualne datoteke.",
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
