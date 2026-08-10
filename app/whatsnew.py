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
    "1.0.54": {
        "en": [
            "When the translation service briefly runs out of capacity, Voxis now tries a backup connection right away instead of repeatedly retrying the one that's already overloaded — fewer full switches to the alternate engine during short service hiccups.",
            "Fixed a volume ceiling some setups hit: if your speakers or headphones' own volume was below 100%, Voxis's volume control silently capped there — the display showed full volume with no way to get louder. Voxis now raises the device to full for the session and restores your setting afterward.",
            "Voxis now shows which version you're running in the top bar, and lets you know when a new version is available.",
        ],
        "tr": [
            "Çeviri servisi kısa süreliğine kapasite sorunu yaşadığında, Voxis artık zaten aşırı yüklenmiş bağlantıyı tekrar tekrar denemek yerine hemen bir yedek bağlantı deniyor — kısa servis aksaklıklarında yedek motora tam geçiş daha az gerekiyor.",
            "Bazı kurulumlarda karşılaşılan bir ses tavanı sorunu düzeltildi: hoparlörünüzün veya kulaklığınızın kendi ses seviyesi %100'ün altındaysa, Voxis'in ses kontrolü sessizce o seviyede tavan yapıyordu — gösterge tam sesi gösterse de daha fazla açamıyordunuz. Voxis artık oturum süresince cihazı tam sese çıkarıyor ve bitince ayarınızı geri yüklüyor.",
            "Voxis artık üst çubukta hangi sürümü kullandığınızı gösteriyor ve yeni bir sürüm çıktığında sizi bilgilendiriyor.",
        ],
        "de": [
            "Wenn der Übersetzungsdienst kurzzeitig an seine Kapazitätsgrenze stößt, versucht Voxis jetzt sofort eine Backup-Verbindung, anstatt die bereits überlastete Verbindung wiederholt erneut zu versuchen – dadurch ist bei kurzen Dienstausfällen seltener ein vollständiger Wechsel zur Backup-Engine nötig.",
            "Ein Lautstärke-Deckel auf manchen Systemen wurde behoben: Lag die eigene Lautstärke Ihrer Lautsprecher oder Kopfhörer unter 100 %, deckelte die Lautstärkeregelung von Voxis dort still und leise – die Anzeige zeigte volle Lautstärke, obwohl man nicht lauter stellen konnte. Voxis stellt das Gerät jetzt für die Dauer der Sitzung auf volle Lautstärke und stellt Ihre Einstellung danach wieder her.",
            "Voxis zeigt jetzt in der oberen Leiste an, welche Version Sie verwenden, und informiert Sie, wenn eine neue Version verfügbar ist.",
        ],
        "fr": [
            "Lorsque le service de traduction manque brièvement de capacité, Voxis tente désormais immédiatement une connexion de secours au lieu de retenter sans cesse la connexion déjà saturée — moins de bascules complètes vers le moteur de secours lors de courtes pannes de service.",
            "Correction d'un plafond de volume rencontré sur certaines configurations : si le volume propre de vos enceintes ou de votre casque était inférieur à 100 %, le contrôle du volume de Voxis se plafonnait silencieusement à ce niveau — l'affichage indiquait le volume maximal sans pouvoir monter davantage. Voxis règle désormais l'appareil au volume maximal pendant la session et restaure votre réglage ensuite.",
            "Voxis affiche désormais la version que vous utilisez dans la barre supérieure et vous informe lorsqu'une nouvelle version est disponible.",
        ],
        "es": [
            "Cuando el servicio de traducción se queda momentáneamente sin capacidad, Voxis ahora intenta una conexión de respaldo de inmediato en lugar de reintentar repetidamente la conexión ya saturada — menos cambios completos al motor alternativo durante interrupciones breves del servicio.",
            "Se corrigió un límite de volumen que afectaba a algunas configuraciones: si el volumen propio de tus altavoces o auriculares estaba por debajo del 100 %, el control de volumen de Voxis se topaba silenciosamente con ese límite — el indicador mostraba volumen máximo sin poder subir más. Voxis ahora sube el dispositivo al máximo durante la sesión y restaura tu ajuste al finalizar.",
            "Voxis ahora muestra en la barra superior la versión que estás usando y te avisa cuando hay una nueva versión disponible.",
        ],
        "pt": [
            "Quando o serviço de tradução fica momentaneamente sem capacidade, o Voxis agora tenta uma conexão de backup imediatamente, em vez de tentar repetidamente a conexão já sobrecarregada — menos trocas completas para o mecanismo alternativo durante falhas breves do serviço.",
            "Corrigido um teto de volume que afetava algumas configurações: se o volume dos seus alto-falantes ou fones de ouvido estivesse abaixo de 100%, o controle de volume do Voxis parava silenciosamente nesse limite — o indicador mostrava volume máximo, mas não era possível aumentar mais. O Voxis agora eleva o dispositivo ao máximo durante a sessão e restaura sua configuração depois.",
            "Agora o Voxis mostra na barra superior a versão que você está usando e avisa quando há uma nova versão disponível.",
        ],
        "it": [
            "Quando il servizio di traduzione esaurisce brevemente la capacità, Voxis ora prova subito una connessione di backup invece di ritentare più volte quella già sovraccarica — meno passaggi completi al motore alternativo durante brevi interruzioni del servizio.",
            "Corretto un limite di volume riscontrato su alcune configurazioni: se il volume proprio degli altoparlanti o delle cuffie era sotto il 100%, il controllo del volume di Voxis si fermava silenziosamente a quel limite — l'indicatore mostrava il volume massimo pur non potendo alzarlo ulteriormente. Voxis ora porta il dispositivo al massimo per la durata della sessione e ripristina l'impostazione al termine.",
            "Voxis ora mostra nella barra superiore la versione in uso e avvisa quando è disponibile una nuova versione.",
        ],
        "nl": [
            "Als de vertaaldienst kortstondig door zijn capaciteit heen zit, probeert Voxis nu meteen een back-upverbinding in plaats van steeds opnieuw de al overbelaste verbinding te proberen — minder volledige overstappen naar de back-up-engine bij korte storingen.",
            "Een volumeplafond op sommige opstellingen is verholpen: als het eigen volume van je luidsprekers of koptelefoon onder de 100% stond, liep het volumebeheer van Voxis daar stilletjes tegenaan — de indicator toonde vol volume terwijl je niet harder kon zetten. Voxis zet het apparaat nu voor de duur van de sessie op vol volume en herstelt je instelling daarna.",
            "Voxis toont nu in de bovenbalk welke versie je gebruikt en laat het weten zodra er een nieuwe versie beschikbaar is.",
        ],
        "pl": [
            "Gdy usługa tłumaczenia chwilowo wyczerpie limit przepustowości, Voxis od razu próbuje połączenia zapasowego zamiast wielokrotnie ponawiać już przeciążone połączenie — rzadziej dochodzi do pełnego przełączenia na silnik zapasowy podczas krótkich awarii usługi.",
            "Naprawiono pułap głośności występujący w niektórych konfiguracjach: jeśli głośność samych głośników lub słuchawek była poniżej 100%, regulacja głośności Voxis po cichu zatrzymywała się na tym poziomie — wskaźnik pokazywał pełną głośność, choć nie dało się jej zwiększyć. Voxis ustawia teraz urządzenie na pełną głośność na czas sesji i przywraca ustawienie po jej zakończeniu.",
            "Voxis pokazuje teraz w górnym pasku, której wersji używasz, i informuje, gdy dostępna jest nowa wersja.",
        ],
        "cs": [
            "Když překladové službě dočasně dojde kapacita, Voxis nyní okamžitě zkusí záložní připojení, místo aby opakovaně zkoušel už přetížené připojení — při krátkých výpadcích služby je díky tomu méně potřeba úplné přepnutí na záložní engine.",
            "Opraven strop hlasitosti, na který narážela některá nastavení: pokud byla vlastní hlasitost reproduktorů nebo sluchátek pod 100 %, ovládání hlasitosti Voxis se na této hranici tiše zastavilo — ukazatel zobrazoval plnou hlasitost, ačkoli výš už nešlo přidat. Voxis nyní na dobu relace nastaví zařízení na plnou hlasitost a po jejím skončení obnoví vaše nastavení.",
            "Voxis nyní v horní liště zobrazuje, kterou verzi používáte, a upozorní vás, jakmile je dostupná nová verze.",
        ],
        "hu": [
            "Amikor a fordítószolgáltatás átmenetileg kifogy a kapacitásból, a Voxis most azonnal megpróbál egy tartalék kapcsolatot ahelyett, hogy ismételten a már túlterhelt kapcsolatot próbálná — rövid szolgáltatási fennakadásoknál ritkábban van szükség teljes átváltásra a tartalék motorra.",
            "Kijavítottunk egy hangerő-plafont, amellyel néhány beállítás találkozott: ha a hangszórók vagy fejhallgatók saját hangereje 100% alatt volt, a Voxis hangerő-szabályzása csendben ott állt meg — a kijelző teljes hangerőt mutatott, mégsem lehetett feljebb tekerni. A Voxis mostantól a munkamenet idejére teljes hangerőre állítja az eszközt, majd utána visszaállítja a beállítást.",
            "A Voxis mostantól a felső sávban mutatja, melyik verziót használja, és jelzi, ha új verzió érhető el.",
        ],
        "ro": [
            "Când serviciul de traducere rămâne temporar fără capacitate, Voxis încearcă acum imediat o conexiune de rezervă, în loc să reîncerce repetat conexiunea deja supraîncărcată — mai puține comutări complete la motorul alternativ în timpul întreruperilor scurte ale serviciului.",
            "A fost corectată o limită de volum întâlnită la unele configurații: dacă volumul propriu al difuzoarelor sau căștilor era sub 100%, controlul volumului din Voxis se plafona silențios acolo — indicatorul arăta volum maxim, deși nu se mai putea urca. Voxis ridică acum dispozitivul la volum maxim pe durata sesiunii și restaurează setarea ta după aceea.",
            "Voxis afișează acum în bara de sus versiunea pe care o folosești și te anunță atunci când este disponibilă o versiune nouă.",
        ],
        "sv": [
            "När översättningstjänsten kortvarigt får kapacitetsbrist försöker Voxis nu genast med en reservanslutning i stället för att upprepade gånger försöka igen med den redan överbelastade anslutningen — färre fullständiga byten till reservmotorn vid korta driftstörningar.",
            "Ett volymtak på vissa uppsättningar är åtgärdat: om dina högtalares eller hörlurars egen volym låg under 100 % stannade Voxis volymkontroll tyst vid den nivån — indikatorn visade full volym trots att du inte kunde höja mer. Voxis höjer nu enheten till full volym under sessionen och återställer din inställning efteråt.",
            "Voxis visar nu i det övre fältet vilken version du använder och meddelar dig när en ny version finns tillgänglig.",
        ],
        "sr": [
            "Kada usluga prevođenja privremeno ostane bez kapaciteta, Voxis sada odmah pokušava rezervnu vezu umesto da ponovo pokušava već preopterećenu vezu — manje potpunih prelazaka na rezervni mehanizam tokom kratkih smetnji u usluzi.",
            "Ispravljen je plafon jačine zvuka na koji su neka podešavanja nailazila: ako je sopstvena jačina zvuka zvučnika ili slušalica bila ispod 100%, kontrola jačine zvuka u Voxisu se tiho zaustavljala na tom nivou — indikator je prikazivao punu jačinu iako se nije mogla dalje pojačati. Voxis sada postavlja uređaj na punu jačinu tokom sesije i vraća vaše podešavanje nakon toga.",
            "Voxis sada u gornjoj traci prikazuje koju verziju koristite i obaveštava vas kada je dostupna nova verzija.",
        ],
        "ru": [
            "Когда сервису перевода временно не хватает мощности, Voxis теперь сразу пробует резервное соединение вместо повторных попыток на уже перегруженном — при коротких сбоях сервиса реже требуется полный переход на резервный движок.",
            "Исправлено ограничение громкости, с которым сталкивались некоторые конфигурации: если собственная громкость динамиков или наушников была ниже 100%, регулятор громкости Voxis незаметно упирался в этот предел — индикатор показывал полную громкость, хотя добавить больше было нельзя. Теперь Voxis на время сеанса поднимает устройство на полную громкость и восстанавливает вашу настройку после его завершения.",
            "Voxis теперь показывает в верхней панели, какую версию вы используете, и сообщает, когда доступна новая версия.",
        ],
        "ja": [
            "翻訳サービスが一時的に容量不足になった場合、Voxisはすでに過負荷の接続を何度も再試行する代わりに、すぐにバックアップ接続を試すようになりました — 短時間のサービス障害時に、バックアップエンジンへの完全切り替えが発生する頻度が減ります。",
            "一部の環境で発生していた音量の上限の不具合を修正しました。スピーカーやヘッドホン自体の音量が100%未満の場合、Voxisの音量調整はその音量で静かに頭打ちになり、表示上は最大音量なのにそれ以上上げられませんでした。Voxisはセッション中はデバイスを最大音量に設定し、終了後に元の設定に戻すようになりました。",
            "Voxisは現在使用しているバージョンを上部バーに表示するようになり、新しいバージョンが利用可能になると知らせます。",
        ],
        "ko": [
            "번역 서비스가 일시적으로 용량 부족을 겪을 때, Voxis는 이제 이미 과부하된 연결을 반복해서 재시도하는 대신 즉시 백업 연결을 시도합니다 — 짧은 서비스 장애 중 백업 엔진으로 완전히 전환되는 빈도가 줄어듭니다.",
            "일부 환경에서 발생하던 음량 상한 문제를 수정했습니다. 스피커나 헤드폰 자체 음량이 100% 미만이면 Voxis의 음량 조절이 그 지점에서 조용히 멈췄습니다 — 표시는 최대 음량이지만 더 이상 올릴 수 없었습니다. 이제 Voxis는 세션 동안 장치를 최대 음량으로 설정하고 종료 후 원래 설정으로 복원합니다.",
            "Voxis가 이제 상단 바에 현재 사용 중인 버전을 표시하고, 새 버전을 사용할 수 있을 때 알려줍니다.",
        ],
        "zh": [
            "当翻译服务暂时容量不足时，Voxis 现在会立即尝试备用连接，而不是反复重试已经过载的连接——短暂的服务故障期间，完全切换到备用引擎的情况会减少。",
            "修复了部分设置中出现的音量上限问题：如果扬声器或耳机自身的音量低于 100%，Voxis 的音量控制会悄悄地卡在那个上限——显示已是最大音量，却无法再调高。现在 Voxis 会在会话期间将设备音量调至最大，并在结束后恢复你的原始设置。",
            "Voxis 现在会在顶部栏显示您正在使用的版本，并在有新版本可用时通知您。",
        ],
        "zh-Hant": [
            "當翻譯服務暫時容量不足時，Voxis 現在會立即嘗試備援連線，而不是反覆重試已經過載的連線——短暫的服務中斷期間，完全切換到備援引擎的情況會減少。",
            "修正了部分設定中出現的音量上限問題：如果喇叭或耳機本身的音量低於 100%，Voxis 的音量控制會悄悄卡在那個上限——顯示已是最大音量，卻無法再調高。現在 Voxis 會在工作階段期間將裝置音量調到最大，並在結束後還原您的原始設定。",
            "Voxis 現在會在頂部列顯示您正在使用的版本，並在有新版本可用時通知您。",
        ],
        "hi": [
            "जब अनुवाद सेवा अस्थायी रूप से क्षमता से बाहर हो जाती है, तो Voxis अब पहले से ही अतिभारित कनेक्शन को बार-बार दोबारा आज़माने के बजाय तुरंत एक बैकअप कनेक्शन आज़माता है — संक्षिप्त सेवा रुकावटों के दौरान बैकअप इंजन पर पूर्ण स्विच कम बार होता है।",
            "कुछ सेटअप में आने वाली एक वॉल्यूम सीमा की समस्या ठीक की गई: यदि आपके स्पीकर या हेडफ़ोन का अपना वॉल्यूम 100% से कम था, तो Voxis का वॉल्यूम नियंत्रण चुपचाप उसी स्तर पर सीमित हो जाता था — संकेतक पूरा वॉल्यूम दिखाता था, फिर भी और तेज़ नहीं किया जा सकता था। अब Voxis सत्र के दौरान डिवाइस को पूर्ण वॉल्यूम पर सेट करता है और समाप्त होने पर आपकी सेटिंग को वापस बहाल कर देता है।",
            "Voxis अब टॉप बार में यह दिखाता है कि आप कौन-सा संस्करण उपयोग कर रहे हैं, और नया संस्करण उपलब्ध होने पर आपको सूचित करता है।",
        ],
        "id": [
            "Ketika layanan terjemahan kehabisan kapasitas sementara, Voxis kini langsung mencoba koneksi cadangan alih-alih terus mencoba ulang koneksi yang sudah kelebihan beban — lebih jarang terjadi peralihan penuh ke mesin cadangan saat gangguan layanan singkat.",
            "Memperbaiki batas volume yang dialami beberapa pengaturan: jika volume speaker atau headphone Anda sendiri di bawah 100%, kontrol volume Voxis diam-diam terbatas pada level itu — indikator menunjukkan volume penuh padahal tidak bisa dinaikkan lagi. Voxis kini menaikkan perangkat ke volume penuh selama sesi berlangsung dan mengembalikan pengaturan Anda setelahnya.",
            "Voxis kini menampilkan versi yang Anda gunakan di bilah atas, dan memberi tahu Anda saat versi baru tersedia.",
        ],
        "vi": [
            "Khi dịch vụ dịch thuật tạm thời hết công suất, Voxis giờ đây thử ngay một kết nối dự phòng thay vì liên tục thử lại kết nối vốn đã quá tải — giảm số lần phải chuyển hoàn toàn sang công cụ dự phòng khi có gián đoạn dịch vụ ngắn.",
            "Đã sửa lỗi giới hạn âm lượng gặp phải ở một số cấu hình: nếu âm lượng riêng của loa hoặc tai nghe dưới 100%, bộ điều khiển âm lượng của Voxis âm thầm bị chặn ở mức đó — chỉ báo hiển thị âm lượng tối đa nhưng không thể tăng thêm. Voxis giờ đây đưa thiết bị lên âm lượng tối đa trong suốt phiên và khôi phục lại cài đặt của bạn sau đó.",
            "Voxis giờ đây hiển thị phiên bản bạn đang dùng ở thanh trên cùng, và cho bạn biết khi có phiên bản mới.",
        ],
        "th": [
            "เมื่อบริการแปลภาษาหมดความจุชั่วคราว ตอนนี้ Voxis จะลองใช้การเชื่อมต่อสำรองทันที แทนที่จะลองเชื่อมต่อใหม่ซ้ำๆ กับการเชื่อมต่อที่โอเวอร์โหลดอยู่แล้ว — ลดการสลับไปใช้เอนจินสำรองแบบเต็มรูปแบบระหว่างการหยุดชะงักสั้นๆ ของบริการ",
            "แก้ไขปัญหาเพดานระดับเสียงที่พบในบางการตั้งค่า หากระดับเสียงของลำโพงหรือหูฟังของคุณเองต่ำกว่า 100% การควบคุมระดับเสียงของ Voxis จะติดอยู่ที่ระดับนั้นอย่างเงียบๆ โดยตัวแสดงระดับเสียงแสดงว่าเต็มแล้วแต่ไม่สามารถเพิ่มได้อีก ตอนนี้ Voxis จะปรับอุปกรณ์ให้มีระดับเสียงเต็มระหว่างเซสชันและคืนค่าการตั้งค่าของคุณหลังจากนั้น",
            "ตอนนี้ Voxis จะแสดงเวอร์ชันที่คุณกำลังใช้อยู่ในแถบด้านบน และแจ้งให้คุณทราบเมื่อมีเวอร์ชันใหม่",
        ],
    },
    "1.0.55": {
        "en": [
            "Fixed a rare case where a long or busy translation session would disconnect and reconnect on its own — a background connection check was giving up on a healthy connection too early while a large amount of speech was still being processed. Long sessions should now run through without this interruption.",
        ],
        "tr": [
            "Uzun veya yoğun bir çeviri oturumunun kendiliğinden bağlantısının kopup yeniden bağlanmasına yol açan nadir bir durum düzeltildi — arka plandaki bir bağlantı kontrolü, büyük miktarda konuşma hâlâ işlenirken sağlıklı bir bağlantıdan çok erken vazgeçiyordu. Uzun oturumlar artık bu kesintiye uğramadan sürüyor.",
        ],
        "de": [
            "Ein seltener Fall behoben, in dem eine lange oder stark ausgelastete Übersetzungssitzung sich von selbst trennte und neu verband — eine Hintergrundverbindungsprüfung gab eine gesunde Verbindung zu früh auf, während noch eine große Menge an Sprache verarbeitet wurde. Lange Sitzungen laufen jetzt ohne diese Unterbrechung durch.",
        ],
        "fr": [
            "Correction d'un cas rare où une session de traduction longue ou chargée se déconnectait et se reconnectait d'elle-même — une vérification de connexion en arrière-plan abandonnait une connexion pourtant saine trop tôt, alors qu'une grande quantité de parole était encore en cours de traitement. Les sessions longues se déroulent désormais sans cette interruption.",
        ],
        "es": [
            "Se corrigió un caso poco frecuente en el que una sesión de traducción larga o con mucha actividad se desconectaba y se reconectaba por sí sola — una comprobación de conexión en segundo plano abandonaba una conexión sana demasiado pronto mientras todavía se procesaba una gran cantidad de voz. Las sesiones largas ahora deberían completarse sin esta interrupción.",
        ],
        "pt": [
            "Corrigido um caso raro em que uma sessão de tradução longa ou intensa se desconectava e reconectava sozinha — uma verificação de conexão em segundo plano desistia de uma conexão saudável cedo demais enquanto uma grande quantidade de fala ainda estava sendo processada. Sessões longas agora devem continuar sem essa interrupção.",
        ],
        "it": [
            "Corretto un caso raro in cui una sessione di traduzione lunga o intensa si disconnetteva e riconnetteva da sola — un controllo di connessione in background abbandonava una connessione sana troppo presto mentre veniva ancora elaborata una grande quantità di parlato. Le sessioni lunghe ora dovrebbero proseguire senza questa interruzione.",
        ],
        "nl": [
            "Een zeldzaam geval opgelost waarbij een lange of drukke vertaalsessie zichzelf verbrak en opnieuw verbond — een achtergrondverbindingscontrole gaf een gezonde verbinding te vroeg op terwijl er nog een grote hoeveelheid spraak werd verwerkt. Lange sessies zouden nu zonder deze onderbreking moeten doorlopen.",
        ],
        "pl": [
            "Naprawiono rzadki przypadek, w którym długa lub intensywna sesja tłumaczenia sama się rozłączała i łączyła ponownie — sprawdzanie połączenia w tle zbyt wcześnie rezygnowało ze sprawnego połączenia, gdy wciąż przetwarzana była duża ilość mowy. Długie sesje powinny teraz przebiegać bez tego przerwania.",
        ],
        "cs": [
            "Opravena vzácná situace, kdy se dlouhá nebo vytížená překladová relace sama odpojila a znovu připojila — kontrola připojení na pozadí příliš brzy vzdávala funkční spojení, zatímco se ještě zpracovávalo velké množství řeči. Dlouhé relace by nyní měly probíhat bez tohoto přerušení.",
        ],
        "hu": [
            "Kijavítottunk egy ritka esetet, amikor egy hosszú vagy forgalmas fordítási munkamenet magától megszakadt és újracsatlakozott — egy háttérben futó kapcsolatellenőrzés túl korán adta fel az egyébként egészséges kapcsolatot, miközben még nagy mennyiségű beszéd feldolgozása zajlott. A hosszú munkamenetek mostantól ez a megszakítás nélkül futnak végig.",
        ],
        "ro": [
            "A fost corectat un caz rar în care o sesiune de traducere lungă sau încărcată se deconecta și se reconecta de la sine — o verificare a conexiunii din fundal renunța prea devreme la o conexiune sănătoasă, în timp ce se procesa încă un volum mare de vorbire. Sesiunile lungi ar trebui acum să continue fără această întrerupere.",
        ],
        "sv": [
            "Åtgärdat ett sällsynt fall där en lång eller intensiv översättningssession kopplades bort och återanslöts av sig själv — en bakgrundskontroll av anslutningen gav upp en fungerande anslutning för tidigt medan en stor mängd tal fortfarande bearbetades. Långa sessioner bör nu köras igenom utan detta avbrott.",
        ],
        "sr": [
            "Ispravljen redak slučaj u kome se duga ili zauzeta sesija prevođenja sama prekidala i ponovo povezivala — provera veze u pozadini je odustajala od zdrave veze prerano dok se još uvek obrađivala velika količina govora. Duge sesije bi sada trebalo da teku bez ovog prekida.",
        ],
        "ru": [
            "Исправлен редкий случай, когда длинный или загруженный сеанс перевода сам разрывал и восстанавливал соединение — фоновая проверка соединения слишком рано отказывалась от исправного соединения, пока ещё обрабатывался большой объём речи. Теперь длинные сеансы должны проходить без этого прерывания.",
        ],
        "ja": [
            "長時間または発話量の多い翻訳セッションが自動的に切断・再接続されるまれなケースを修正しました — バックグラウンドの接続チェックが、大量の音声をまだ処理している最中の正常な接続を早々に諦めてしまうことがありました。長時間のセッションは、この中断なく最後まで実行されるようになりました。",
        ],
        "ko": [
            "길거나 발화량이 많은 번역 세션이 저절로 연결이 끊겼다가 다시 연결되던 드문 경우를 수정했습니다 — 백그라운드 연결 점검이 많은 양의 음성을 아직 처리 중인 정상적인 연결을 너무 일찍 포기하곤 했습니다. 이제 긴 세션은 이런 중단 없이 끝까지 이어집니다.",
        ],
        "zh": [
            "修复了一个罕见问题：时间较长或对话较密集的翻译会话会自行断开并重新连接——后台连接检查会在仍有大量语音待处理时，过早放弃一个本来正常的连接。现在，长时间的会话应该不会再受到这种中断的影响。",
        ],
        "zh-Hant": [
            "修正了一個罕見問題：時間較長或對話較密集的翻譯工作階段會自行斷線並重新連線——背景連線檢查會在仍有大量語音待處理時，過早放棄一個原本正常的連線。現在，長時間的工作階段應該不會再受到這種中斷影響。",
        ],
        "hi": [
            "एक दुर्लभ स्थिति ठीक की गई जिसमें लंबा या व्यस्त अनुवाद सत्र अपने आप डिस्कनेक्ट होकर फिर से जुड़ जाता था — बैकग्राउंड कनेक्शन जांच एक स्वस्थ कनेक्शन को बहुत जल्दी छोड़ देती थी, जबकि अभी भी बड़ी मात्रा में आवाज़ प्रोसेस हो रही होती थी। लंबे सत्र अब इस रुकावट के बिना पूरे चलने चाहिए।",
        ],
        "id": [
            "Memperbaiki kasus langka saat sesi terjemahan yang panjang atau sibuk terputus dan tersambung kembali dengan sendirinya — pemeriksaan koneksi di latar belakang menyerah pada koneksi yang sebenarnya sehat terlalu cepat, saat masih ada banyak ucapan yang sedang diproses. Sesi panjang kini seharusnya berjalan tanpa gangguan ini.",
        ],
        "vi": [
            "Đã sửa một trường hợp hiếm gặp khi phiên dịch dài hoặc bận rộn tự ngắt kết nối rồi kết nối lại — một bước kiểm tra kết nối chạy nền đã từ bỏ một kết nối vẫn đang hoạt động tốt quá sớm, trong khi vẫn còn một lượng lớn giọng nói đang được xử lý. Các phiên dài giờ đây sẽ chạy suốt mà không bị gián đoạn này.",
        ],
        "th": [
            "แก้ไขกรณีที่พบได้ยากซึ่งเซสชันการแปลที่ยาวนานหรือมีการพูดจำนวนมากจะตัดการเชื่อมต่อแล้วเชื่อมต่อใหม่เอง — การตรวจสอบการเชื่อมต่อในพื้นหลังยกเลิกการเชื่อมต่อที่ยังปกติดีเร็วเกินไป ขณะที่ยังมีเสียงพูดจำนวนมากกำลังถูกประมวลผลอยู่ เซสชันที่ยาวนานตอนนี้ควรทำงานต่อเนื่องโดยไม่มีการขัดจังหวะนี้",
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
