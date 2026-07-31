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
    "1.0.49": {
        "en": [
            "Meeting mode no longer translates your own voice back at you: on PCs with a virtual audio cable, the translation sent into the call came back in as a third, phantom voice in your own language.",
            "Cleaner captions: words no longer run together at the end of a sentence, repeated sentences are removed, and very long lines are split where the sentence ends.",
            "Subtitle files (SRT/VTT) now wrap to a readable width and line up with the session's own recording — they used to run off the screen and start at the wrong time.",
            "Meeting mode keeps both sides apart: every line is labelled, on screen and in the saved transcript.",
            "New: a “Meeting terms” box in Settings — list the names your meetings use and the translation will spell them correctly.",
        ],
        "tr": [
            "Toplantı modu artık kendi sesinizi size geri çevirmiyor: sanal ses kablosu kurulu bilgisayarlarda, görüşmeye gönderilen çeviri kendi dilinizde üçüncü bir hayalet ses olarak geri dönüyordu.",
            "Altyazılar temizlendi: cümle sonlarında kelimeler artık birbirine yapışmıyor, tekrarlanan cümleler kaldırılıyor, çok uzun satırlar cümle bitiminde bölünüyor.",
            "Altyazı dosyaları (SRT/VTT) artık okunabilir genişlikte sarılıyor ve oturumun kendi ses kaydıyla hizalı — önceden ekrandan taşıyor ve yanlış zamanda başlıyordu.",
            "Toplantı modu iki tarafı ayırıyor: her satır hem ekranda hem kaydedilen transkriptte etiketleniyor.",
            "Yeni: Ayarlar'da “Toplantı terimleri” kutusu — toplantılarınızda geçen isimleri yazın, çeviri onları doğru yazsın.",
        ],
        "de": [
            "Der Meeting-Modus übersetzt deine eigene Stimme nicht mehr zu dir zurück: Auf PCs mit virtuellem Audiokabel kam die in den Anruf gesendete Übersetzung als dritte, geisterhafte Stimme in deiner Sprache zurück.",
            "Sauberere Untertitel: Wörter kleben am Satzende nicht mehr zusammen, wiederholte Sätze werden entfernt, sehr lange Zeilen werden am Satzende getrennt.",
            "Untertiteldateien (SRT/VTT) werden jetzt lesbar umbrochen und passen zur Aufnahme der Sitzung — früher liefen sie aus dem Bild und begannen zur falschen Zeit.",
            "Der Besprechungsmodus trennt beide Seiten: Jede Zeile ist gekennzeichnet — auf dem Bildschirm und im gespeicherten Transkript.",
            "Neu: ein Feld „Besprechungsbegriffe“ in den Einstellungen — tragen Sie Namen ein, die in Ihren Besprechungen vorkommen, damit die Übersetzung sie korrekt schreibt.",
        ],
        "fr": [
            "Le mode réunion ne vous retraduit plus votre propre voix : sur les PC équipés d'un câble audio virtuel, la traduction envoyée dans l'appel revenait sous forme d'une troisième voix fantôme dans votre langue.",
            "Sous-titres plus propres : les mots ne se collent plus en fin de phrase, les phrases répétées sont supprimées et les lignes très longues sont coupées à la fin de la phrase.",
            "Les fichiers de sous-titres (SRT/VTT) sont désormais mis à la ligne correctement et alignés sur l'enregistrement de la session — ils débordaient de l'écran et commençaient au mauvais moment.",
            "Le mode Réunion sépare les deux côtés : chaque ligne est identifiée, à l'écran comme dans la transcription enregistrée.",
            "Nouveau : un champ « Termes de réunion » dans les Paramètres — indiquez les noms utilisés dans vos réunions pour que la traduction les écrive correctement.",
        ],
        "es": [
            "El modo reunión ya no te devuelve tu propia voz traducida: en equipos con un cable de audio virtual, la traducción enviada a la llamada volvía como una tercera voz fantasma en tu idioma.",
            "Subtítulos más limpios: las palabras ya no se pegan al final de una frase, las frases repetidas se eliminan y las líneas muy largas se dividen donde termina la frase.",
            "Los archivos de subtítulos (SRT/VTT) ahora se ajustan a un ancho legible y coinciden con la grabación de la sesión: antes se salían de la pantalla y empezaban a destiempo.",
            "El modo Reunión separa ambos lados: cada línea se identifica, en pantalla y en la transcripción guardada.",
            "Nuevo: un cuadro “Términos de la reunión” en Ajustes: escribe los nombres que se usan en tus reuniones y la traducción los escribirá bien.",
        ],
        "pt": [
            "O modo reunião não traduz mais a sua própria voz de volta para você: em PCs com um cabo de áudio virtual, a tradução enviada para a chamada voltava como uma terceira voz fantasma no seu idioma.",
            "Legendas mais limpas: as palavras não se juntam mais no fim da frase, frases repetidas são removidas e linhas muito longas são divididas onde a frase termina.",
            "Os arquivos de legenda (SRT/VTT) agora quebram em largura legível e ficam alinhados com a gravação da sessão — antes saíam da tela e começavam na hora errada.",
            "O modo Reunião separa os dois lados: cada linha é identificada, na tela e na transcrição salva.",
            "Novo: uma caixa “Termos da reunião” nas Configurações — liste os nomes usados nas suas reuniões para a tradução escrevê-los corretamente.",
        ],
        "it": [
            "La modalità riunione non ti ritraduce più la tua stessa voce: sui PC con un cavo audio virtuale, la traduzione inviata alla chiamata rientrava come una terza voce fantasma nella tua lingua.",
            "Sottotitoli più puliti: le parole non si attaccano più a fine frase, le frasi ripetute vengono rimosse e le righe molto lunghe si dividono dove finisce la frase.",
            "I file dei sottotitoli (SRT/VTT) ora vanno a capo in modo leggibile e coincidono con la registrazione della sessione: prima uscivano dallo schermo e partivano nel momento sbagliato.",
            "La modalità Riunione tiene separati i due lati: ogni riga è etichettata, a schermo e nella trascrizione salvata.",
            "Novità: un campo “Termini della riunione” nelle Impostazioni — elenca i nomi usati nelle tue riunioni e la traduzione li scriverà correttamente.",
        ],
        "cs": [
            "Režim schůzky už nepřekládá váš vlastní hlas zpět k vám: na počítačích s virtuálním audio kabelem se překlad odeslaný do hovoru vracel zpět jako třetí, přízračný hlas ve vašem jazyce.",
            "Čistší titulky: slova se na konci věty už nespojují, opakované věty se odstraňují a velmi dlouhé řádky se dělí tam, kde věta končí.",
            "Soubory titulků (SRT/VTT) se nyní zalamují do čitelné šířky a odpovídají nahrávce rela  ce — dříve přebíhaly přes obrazovku a začínaly ve špatný čas.",
            "Režim Schůzka odděluje obě strany: každý řádek je označen — na obrazovce i v uloženém přepisu.",
            "Nové: pole „Termíny schůzky“ v Nastavení — zadejte jména, která se ve vašich schůzkách objevují, a překlad je napíše správně.",
        ],
        "hi": [
            "मीटिंग मोड अब आपकी अपनी आवाज़ आपको वापस अनुवाद करके नहीं सुनाता: वर्चुअल ऑडियो केबल वाले पीसी पर, कॉल में भेजा गया अनुवाद आपकी अपनी भाषा में तीसरी, भूतिया आवाज़ बनकर लौट आता था।",
            "साफ़ कैप्शन: वाक्य के अंत में शब्द अब आपस में नहीं जुड़ते, दोहराए गए वाक्य हटा दिए जाते हैं और बहुत लंबी पंक्तियाँ वाक्य के अंत पर विभाजित होती हैं।",
            "उपशीर्षक फ़ाइलें (SRT/VTT) अब पढ़ने योग्य चौड़ाई में रैप होती हैं और सेशन की रिकॉर्डिंग से मेल खाती हैं।",
            "मीटिंग मोड दोनों पक्षों को अलग रखता है: हर पंक्ति स्क्रीन पर और सहेजे गए ट्रांसक्रिप्ट में लेबल की गई है।",
            "नया: सेटिंग्स में “मीटिंग शब्द” बॉक्स — अपनी मीटिंग में आने वाले नाम लिखें, अनुवाद उन्हें सही लिखेगा।",
        ],
        "hu": [
            "A találkozó mód többé nem fordítja vissza a saját hangodat: virtuális hangkábellel rendelkező gépeken a hívásba küldött fordítás harmadik, kísérteties hangként tért vissza a saját nyelveden.",
            "Tisztább feliratok: a szavak a mondat végén már nem tapadnak össze, az ismételt mondatok eltűnnek, a nagyon hosszú sorok a mondat végén törődnek.",
            "A feliratfájlok (SRT/VTT) most olvasható szélességben tördelődnek és illeszkednek a munkamenet felvételéhez — korábban kif      utottak a képernyőről és rossz időben indultak.",
            "A Megbeszélés mód elkülöníti a két oldalt: minden sor címkézve van, a képernyőn és a mentett átiratban is.",
            "Új: „Megbeszélés kifejezései” mező a Beállításokban — sorolja fel a megbeszélésein elhangzó neveket, és a fordítás helyesen írja őket.",
        ],
        "id": [
            "Mode rapat tidak lagi menerjemahkan suara Anda sendiri kembali kepada Anda: di PC dengan kabel audio virtual, terjemahan yang dikirim ke panggilan kembali masuk sebagai suara ketiga dalam bahasa Anda.",
            "Teks lebih bersih: kata tidak lagi menempel di akhir kalimat, kalimat yang terulang dihapus, dan baris yang sangat panjang dipotong di akhir kalimat.",
            "Berkas subtitle (SRT/VTT) kini dibungkus dengan lebar yang mudah dibaca dan selaras dengan rekaman sesi — sebelumnya melebar keluar layar dan mulai di waktu yang salah.",
            "Mode Rapat memisahkan kedua sisi: setiap baris diberi label, di layar dan di transkrip yang tersimpan.",
            "Baru: kotak “Istilah rapat” di Pengaturan — tuliskan nama yang dipakai di rapat Anda agar terjemahan menulisnya dengan benar.",
        ],
        "ja": [
            "会議モードが自分の声を翻訳して返さなくなりました。仮想オーディオケーブルを使用している PC では、通話に送った翻訳が自分の言語の 3 つ目の声として戻ってきていました。",
            "字幕が読みやすく：文末で単語がくっつかなくなり、重複した文を削除し、長すぎる行は文の切れ目で分割されます。",
            "字幕ファイル（SRT/VTT）は読みやすい幅で折り返され、セッションの録音と一致します。",
            "会議モードで両方の発言を区別：画面上でも保存される議事録でも、各行にラベルが付きます。",
            "新機能：設定の「会議用の用語」欄 — 会議で使う名前を登録すると、翻訳が正しく表記します。",
        ],
        "ko": [
            "회의 모드가 더 이상 사용자의 목소리를 다시 번역해 들려주지 않습니다. 가상 오디오 케이블이 설치된 PC에서 통화로 보낸 번역이 사용자 언어의 세 번째 유령 음성으로 되돌아왔습니다.",
            "깔膵해진 자막: 문장 끝에서 단어가 붙지 않고, 반복된 문장은 제거되며, 너무 긴 줄은 문장이 끝나는 곳에서 나뉘어집니다.",
            "자막 파일(SRT/VTT)이 읽기 좋은 폭으로 줄바꿈되고 세션 녹음과 맞아떨어집니다.",
            "회의 모드가 양쪽을 구분합니다: 화면과 저장된 기록 모두에서 각 줄에 라벨이 붙습니다.",
            "새로움: 설정의 “회의 용어” 상자 — 회의에서 쓰는 이름을 적어 두면 번역이 정확하게 표기합니다.",
        ],
        "nl": [
            "De vergadermodus vertaalt je eigen stem niet meer naar je terug: op pc's met een virtuele audiokabel kwam de vertaling die naar het gesprek werd gestuurd terug als een derde, spookachtige stem in je eigen taal.",
            "Schonere ondertitels: woorden plakken niet meer aan elkaar aan het eind van een zin, herhaalde zinnen worden verwijderd en heel lange regels worden gesplitst waar de zin eindigt.",
            "Ondertitelbestanden (SRT/VTT) worden nu leesbaar afgebroken en lopen gelijk met de opname van de sessie — eerder liepen ze van het scherm af en begonnen ze op het verkeerde moment.",
            "De vergadermodus houdt beide kanten uit elkaar: elke regel is gelabeld, op het scherm en in het opgeslagen transcript.",
            "Nieuw: een veld “Vergadertermen” in Instellingen — noteer de namen die in uw vergaderingen voorkomen, dan schrijft de vertaling ze correct.",
        ],
        "pl": [
            "Tryb spotkania nie tłumaczy już Twojego własnego głosu z powrotem do Ciebie: na komputerach z wirtualnym kablem audio tłumaczenie wysłane do rozmowy wracało jako trzeci, widmowy głos w Twoim języku.",
            "Czytelniejsze napisy: słowa nie sklejają się już na końcu zdania, powtórzone zdania są usuwane, a bardzo długie wiersze dzielą się tam, gdzie kończy się zdanie.",
            "Pliki napisów (SRT/VTT) są teraz łamane do czytelnej szerokości i zgodne z nagraniem sesji — wcześniej wychodziły poza ekran i zaczynały się w złym momencie.",
            "Tryb Spotkanie rozdziela obie strony: każdy wiersz jest oznaczony — na ekranie i w zapisanej transkrypcji.",
            "Nowość: pole „Terminy spotkania” w Ustawieniach — wpisz nazwy używane na spotkaniach, a tłumaczenie zapisze je poprawnie.",
        ],
        "ro": [
            "Modul întâlnire nu îți mai traduce propria voce înapoi: pe PC-urile cu un cablu audio virtual, traducerea trimisă în apel se întorcea ca o a treia voce fantomă în limba ta.",
            "Subtitrări mai curate: cuvintele nu se mai lipesc la finalul propoziției, propozițiile repetate sunt eliminate, iar rândurile foarte lungi se împart acolo unde se termină propoziția.",
            "Fișierele de subtitrare (SRT/VTT) se împ   art acum pe o lățime lizibilă și se aliniază cu înregistrarea sesiunii.",
            "Modul Întâlnire separă cele două părți: fiecare rând este etichetat, pe ecran și în transcrierea salvată.",
            "Nou: câmpul „Termeni de întâlnire” în Setări — scrie numele folosite în întâlniri, iar traducerea le va scrie corect.",
        ],
        "ru": [
            "Режим встречи больше не переводит ваш собственный голос обратно вам: на компьютерах с виртуальным аудиокабелем перевод, отправленный в звонок, возвращался третьим, призрачным голосом на вашем языке.",
            "Чище субтитры: слова больше не слипаются в конце предложения, повторяющиеся фразы удаляются, а слишком длинные строки делятся по концу фразы.",
            "Файлы субтитров (SRT/VTT) теперь переносятся по читаемой ширине и совпадают с записью сеанса.",
            "Режим встречи разделяет стороны: каждая строка подписана — на экране и в сохранённой расшифровке.",
            "Новое: поле «Термины встречи» в настройках — укажите имена из ваших встреч, чтобы перевод писал их правильно.",
        ],
        "sr": [
            "Režim sastanka više ne prevodi vaš sopstveni glas nazad ka vama: na računarima sa virtuelnim audio kablom, prevod poslat u poziv vraćao se kao treći, sablasni glas na vašem jeziku.",
            "Čistiji titlovi: reči se više ne spajaju na kraju rečenice, ponovljene rečenice se uklanjaju, a veoma dugački redovi se dele tamo gde se rečenica završava.",
            "Fajlovi titlova (SRT/VTT) sada se prelamaju na čitljivu širinu i poklapaju se sa snimkom sesije.",
            "Režim sastanka razdvaja obe strane: svaki red je označen — na ekranu i u sačuvanom transkriptu.",
            "Novo: polje „Termini za sastanke“ u Podešavanjima — upišite imena koja se koriste na sastancima i prevod će ih ispravno napisati.",
        ],
        "sv": [
            "Mötesläget översätter inte längre tillbaka din egen röst till dig: på datorer med en virtuell ljudkabel kom översättningen som skickades in i samtalet tillbaka som en tredje, spöklik röst på ditt eget språk.",
            "Renare undertexter: ord klibbar inte längre ihop i slutet av en mening, upprepade meningar tas bort och mycket långa rader delas där meningen slutar.",
            "Undertextfiler (SRT/VTT) radbryts nu till läsbar bredd och stämmer med sessionens inspelning — tidigare gick de utanför skärmen och började vid fel tid.",
            "Mötesläget håller isär båda sidor: varje rad märks, på skärmen och i den sparade utskriften.",
            "Nytt: rutan ”Mötestermer” i Inställningar — skriv in namnen som förekommer i dina möten så stavar översättningen dem rätt.",
        ],
        "th": [
            "โหมดประชุมจะไม่แปลเสียงของคุณเองกลับมาให้คุณอีกต่อไป: บนพีซีที่มีสายสัญญาณเสียงเสมือน คำแปลที่ส่งเข้าไปในสายจะย้อนกลับเข้ามาเป็นเสียงที่สามในภาษาของคุณ",
            "คำบรรยายสะอาดขึ้น: คำไม่ติดกันที่ท้ายประโยคอีกต่อไป ประโยคที่ซ้ำถูกตัดออก และบรรทัดที่ยาวมากจะถูกแบ่งที่ท้ายประโยค",
            "ไฟล์คำบรรยาย (SRT/VTT) ตัดบรรทัดให้อ่านง่าย และตรงกับไฟล์เสียงของเซสชัน",
            "โหมดประชุมแยกสองฝั่งออกจากกัน: ทุกบรรทัดมีป้ายกำกับ ทั้งบนหน้าจอและในบันทึกที่บันทึกไว้",
            "ใหม่: ช่อง “คำศัพท์สำหรับการประชุม” ในการตั้งค่า — ใส่ชื่อที่ใช้ในการประชุม แล้วคำแปลจะสะกดถูกต้อง",
        ],
        "vi": [
            "Chế độ họp không còn dịch ngược giọng nói của chính bạn về phía bạn: trên máy tính có cáp âm thanh ảo, bản dịch gửi vào cuộc gọi quay trở lại thành giọng thứ ba bằng chính ngôn ngữ của bạn.",
            "Phụ đề sạch hơn: các từ không còn dính vào nhau ở cuối câu, câu bị lặp được loại bỏ và những dòng quá dài được tách tại chỗ kết thúc câu.",
            "Tệp phụ đề (SRT/VTT) nay ngắt dòng ở độ rộng dễ đọc và khớp với bản ghi của phiên.",
            "Chế độ Họp tách riêng hai bên: mỗi dòng đều có nhãn, trên màn hình và trong bản ghi đã lưu.",
            "Mới: ô “Thuật ngữ cuộc họp” trong Cài đặt — nhập các tên dùng trong cuộc họp để bản dịch viết đúng.",
        ],
        "zh": [
            "会议模式不再把你自己的声音翻译后放回给你：在装有虚拟音频线的电脑上，发送到通话中的译文会以你自己语言的第三个幽灵人声返回。",
            "字幕更干净：句末不再粘连单词，重复的句子会被移除，过长的行在句子结束处拆分。",
            "字幕文件（SRT/VTT）现在按可读宽度换行，并与本次会话的录音对齐。",
            "会议模式区分双方：屏幕上和保存的记录中，每一行都有标记。",
            "新增：设置中的“会议术语”框 — 列出会议中会用到的名称，翻译就会写对。",
        ],
        "zh-Hant": [
            "會議模式不再把你自己的聲音翻譯後播回給你：在安裝虛擬音訊線的電腦上，送進通話的譯文會以你自己語言的第三個幽靈人聲返回。",
            "字幕更乾淨：句末不再黏連單字，重複的句子會被移除，過長的行在句子結束處拆分。",
            "字幕檔案（SRT/VTT）現在依可讀寬度換行，並與本次對話的錄音對齊。",
            "會議模式區分雙方：螢幕上和儲存的紀錄中，每一行都有標記。",
            "新增：設定中的「會議術語」欄位 — 列出會議中會用到的名稱，翻譯就會寫對。",
        ],
    },
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
        "it": [
            "Scegli se la voce tradotta suona femminile o maschile, con un'impostazione separata per la voce con cui l'altra persona ti sente in modalità Riunione.",
            "I nomi di marchi e prodotti sono scritti correttamente sin da subito: Voxis include ora un elenco di termini pronto e i tuoi termini si trovano in Impostazioni › Traduzione.",
            "Le novità ora sono nell'app: dopo ogni aggiornamento vedi una volta che cosa è cambiato, nella tua lingua.",
        ],
        "cs": [
            "Vyber, zda má přeložený hlas znít žensky nebo mužsky — s vlastním nastavením pro hlas, kterým tě ostatní slyší v režimu schůzky.",
            "Názvy firem a produktů se píší správně hned od začátku: Voxis nyní obsahuje připravený seznam pojmů a tvoje vlastní pojmy najdeš v Nastavení › Překlad.",
            "Poznámky k verzi jsou nově přímo v aplikaci: po každé aktualizaci jednou uvidíš, co se změnilo, ve svém jazyce.",
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
        "id": [
            "Pilih apakah suara terjemahan terdengar perempuan atau laki-laki — dengan pengaturan terpisah untuk suara yang didengar orang lain sebagai kamu di mode Rapat.",
            "Nama merek dan produk langsung ditulis dengan benar: Voxis kini membawa daftar istilah siap pakai, dan istilahmu sendiri pindah ke Pengaturan › Terjemahan.",
            "Catatan rilis kini ada di dalam aplikasi: setiap selesai memperbarui, kamu melihat sekali apa yang berubah dalam bahasamu.",
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
        "nl": [
            "Kies of de vertaalde stem vrouwelijk of mannelijk klinkt — met een aparte instelling voor de stem waarin de ander jou hoort in de vergadermodus.",
            "Merk- en productnamen worden meteen goed geschreven: Voxis bevat nu een kant-en-klare termenlijst en je eigen termen staan in Instellingen › Vertaling.",
            "Release-opmerkingen staan nu in de app: na elke update zie je één keer wat er is veranderd, in je eigen taal.",
        ],
        "pl": [
            "Wybierz, czy przetłumaczony głos ma brzmieć kobieco czy męsko — z osobnym ustawieniem głosu, którym słyszy Cię druga osoba w trybie spotkania.",
            "Nazwy marek i produktów są od razu pisane poprawnie: Voxis zawiera teraz gotową listę terminów, a Twoje własne terminy trafiły do Ustawienia › Tłumaczenie.",
            "Informacje o zmianach są teraz w aplikacji: po każdej aktualizacji raz zobaczysz, co się zmieniło, w swoim języku.",
        ],
        "ro": [
            "Alege dacă vocea tradusă sună feminin sau masculin — cu o setare separată pentru vocea în care cealaltă persoană te aude în modul Întâlnire.",
            "Numele de mărci și produse sunt scrise corect din start: Voxis include acum o listă de termeni gata făcută, iar termenii tăi au trecut în Setări › Traducere.",
            "Notele de versiune sunt acum în aplicație: după fiecare actualizare vezi o dată ce s-a schimbat, în limba ta.",
        ],
        "ru": [
            "Выберите, будет ли переведённый голос женским или мужским — и отдельно голос, которым собеседник слышит вас в режиме встречи.",
            "Названия брендов и продуктов сразу пишутся правильно: в Voxis теперь есть готовый список терминов, а ваши собственные термины переехали в «Настройки › Перевод».",
            "Список изменений теперь внутри приложения: после каждого обновления вы один раз увидите, что нового, на своём языке.",
        ],
        "sr": [
            "Izaberi da li prevedeni glas zvuči kao ženski ili muški — uz posebno podešavanje za glas kojim te druga osoba sluša u režimu sastanka.",
            "Imena brendova i proizvoda odmah se pišu ispravno: Voxis sada dolazi sa gotovim spiskom pojmova, a tvoji sopstveni pojmovi su prešli u Podešavanja › Prevod.",
            "Beleške o verziji su sada u aplikaciji: posle svakog ažuriranja jednom vidiš šta se promenilo, na svom jeziku.",
        ],
        "sv": [
            "Välj om den översatta rösten ska låta kvinnlig eller manlig — med en separat inställning för rösten som den andra personen hör dig i, i mötesläget.",
            "Varumärkes- och produktnamn stavas rätt från början: Voxis har nu en färdig termlista och dina egna termer finns under Inställningar › Översättning.",
            "Versionsnyheterna finns nu i appen: efter varje uppdatering ser du en gång vad som ändrats, på ditt språk.",
        ],
        "th": [
            "เลือกได้ว่าเสียงแปลจะเป็นเสียงผู้หญิงหรือผู้ชาย พร้อมการตั้งค่าแยกสำหรับเสียงที่อีกฝ่ายได้ยินเป็นคุณในโหมดประชุม",
            "ชื่อแบรนด์และชื่อสินค้าสะกดถูกตั้งแต่แรก: Voxis มีรายการคำศัพท์พร้อมใช้มาให้แล้ว และคำศัพท์ของคุณย้ายไปที่ ตั้งค่า › การแปล",
            "บันทึกรุ่นอยู่ในแอปแล้ว: หลังอัปเดตทุกครั้ง คุณจะเห็นสิ่งที่เปลี่ยนไปหนึ่งครั้งในภาษาของคุณ",
        ],
        "vi": [
            "Chọn giọng dịch là nữ hay nam — kèm thiết lập riêng cho giọng mà người kia nghe thấy bạn trong chế độ Họp.",
            "Tên thương hiệu và sản phẩm được viết đúng ngay từ đầu: Voxis nay có sẵn danh sách thuật ngữ, còn thuật ngữ của bạn chuyển sang Cài đặt › Dịch.",
            "Ghi chú phát hành giờ nằm trong ứng dụng: sau mỗi lần cập nhật, bạn xem một lần những gì đã thay đổi bằng ngôn ngữ của mình.",
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
    },
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
    "1.0.52": {
        "cs": [
            "Voxis se teď ozve, když nic neslyší: pokud k němu nepřichází žádný zvuk, řekne to během několika sekund, místo aby vás nechal koukat na tichou obrazovku. Režim Video překládá zvuk vycházející z počítače — ne to, co říkáte do mikrofonu.",
            "První sekundy relace už nejsou prázdné: vidíte, že se připojuje, a dozvíte se, že první překlad přijde několik sekund po začátku řeči.",
            "Poznámky k verzi teď pokrývají i verze, které jste přeskočili, takže aktualizace na pozadí přes několik verzí neschová, co se změnilo mezi nimi.",
        ],
        "de": [
            "Voxis sagt jetzt Bescheid, wenn es nichts hört: Kommt kein Ton an, meldet es sich innerhalb von Sekunden, statt dich vor einem stillen Bildschirm sitzen zu lassen. Der Video-Modus übersetzt den Ton, der aus deinem Computer kommt — nicht das, was du ins Mikrofon sprichst.",
            "Die ersten Sekunden einer Sitzung sind nicht mehr leer: Du siehst, dass verbunden wird, und erfährst, dass die erste Übersetzung wenige Sekunden nach dem Sprechbeginn kommt.",
            "Die Versionshinweise umfassen jetzt auch übersprungene Versionen — ein Hintergrund-Update über mehrere Versionen verbirgt nicht mehr, was dazwischen passiert ist.",
        ],
        "en": [
            "Voxis now speaks up when it can't hear anything: if no sound is reaching it, it says so within seconds instead of leaving you in front of a silent screen. Video mode translates the sound coming out of your computer — not what you say into your microphone.",
            "The first seconds of a session are no longer blank: you can see it connecting, and it tells you the first translation arrives a few seconds after someone starts speaking.",
            "Release notes now cover the versions you skipped, so a background update that jumps several versions no longer hides what changed in between.",
        ],
        "es": [
            "Voxis ahora avisa cuando no oye nada: si no le llega ningún sonido, lo dice en segundos en vez de dejarte delante de una pantalla en silencio. El modo Vídeo traduce el sonido que sale de tu ordenador, no lo que dices al micrófono.",
            "Los primeros segundos de una sesión ya no están en blanco: ves que se está conectando y te avisa de que la primera traducción llega unos segundos después de que alguien empiece a hablar.",
            "Las notas de la versión ahora incluyen las versiones que te saltaste, así una actualización en segundo plano que salta varias versiones no oculta lo que cambió en medio.",
        ],
        "fr": [
            "Voxis vous prévient maintenant quand il n'entend rien : si aucun son ne lui parvient, il le dit en quelques secondes au lieu de vous laisser devant un écran muet. Le mode Vidéo traduit le son qui sort de votre ordinateur, pas ce que vous dites dans le micro.",
            "Les premières secondes d'une session ne sont plus vides : vous voyez la connexion en cours, et il vous indique que la première traduction arrive quelques secondes après le début de la parole.",
            "Les notes de version couvrent désormais les versions sautées : une mise à jour en arrière-plan qui saute plusieurs versions ne cache plus ce qui a changé entretemps.",
        ],
        "hi": [
            "अब Voxis बता देता है जब उसे कुछ सुनाई नहीं देता: अगर कोई आवाज़ नहीं पहुँच रही, तो वह कुछ सेकंड में यह बता देता है, आपको खाली स्क्रीन के सामने नहीं छोड़ता। वीडियो मोड कंप्यूटर से निकलने वाली आवाज़ का अनुवाद करता है — माइक्रोफ़ोन में बोली गई बात का नहीं।",
            "सेशन के पहले कुछ सेकंड अब खाली नहीं रहते: आप देख सकते हैं कि कनेक्ट हो रहा है, और पता चलता है कि बोलना शुरू होने के कुछ सेकंड बाद पहला अनुवाद आएगा।",
            "रिलीज़ नोट्स अब उन वर्शन को भी दिखाते हैं जो आपसे छूट गए, इसलिए कई वर्शन एक साथ छोड़ने वाला अपडेट बीच के बदलाव नहीं छिपाता।",
        ],
        "hu": [
            "A Voxis most már jelez, ha nem hall semmit: ha nem érkezik hang, pár másodperc alatt szól, ahelyett hogy egy néma képernyő előtt hagyna. A Videó mód a számítógépből kijövő hangot fordítja — nem azt, amit a mikrofonba mondasz.",
            "A munkamenet első másodpercei már nem üresek: látod, hogy kapcsolódik, és megtudod, hogy az első fordítás pár másodperccel a beszéd kezdete után jön meg.",
            "A verziójegyzet mostantól a kihagyott verziókra is kitér, így egy több verziót átlépő háttérfrissítés nem rejti el, mi változott közben.",
        ],
        "id": [
            "Voxis kini memberi tahu Anda saat tidak mendengar apa pun: kalau tidak ada suara yang masuk, ia mengatakannya dalam hitungan detik alih-alih membiarkan Anda menatap layar yang senyap. Mode Video menerjemahkan suara yang keluar dari komputer — bukan yang Anda ucapkan ke mikrofon.",
            "Beberapa detik pertama sesi tidak lagi kosong: Anda bisa melihat prosesnya menyambung, dan diberi tahu bahwa terjemahan pertama datang beberapa detik setelah orang mulai bicara.",
            "Catatan rilis sekarang mencakup versi yang Anda lewati, jadi pembaruan latar belakang yang melompati beberapa versi tidak lagi menyembunyikan perubahan di antaranya.",
        ],
        "it": [
            "Ora Voxis lo dice quando non sente nulla: se non gli arriva alcun suono, te lo segnala in pochi secondi invece di lasciarti davanti a uno schermo muto. La modalità Video traduce il suono che esce dal computer, non quello che dici al microfono.",
            "I primi secondi di una sessione non sono più vuoti: vedi che si sta connettendo e ti dice che la prima traduzione arriva qualche secondo dopo l'inizio del parlato.",
            "Le note di versione ora coprono anche le versioni saltate, così un aggiornamento in background che salta più versioni non nasconde più ciò che è cambiato nel frattempo.",
        ],
        "ja": [
            "音がまったく届いていないとき、Voxis がそれを知らせるようになりました。静かな画面の前で待たせる代わりに、数秒で状況を伝えます。ビデオモードが訳すのはパソコンから出る音で、マイクに話した声ではありません。",
            "セッション開始からの数秒が空白ではなくなりました。接続中であることが見え、最初の翻訳は誰かが話し始めてから数秒後に届くことも表示されます。",
            "リリースノートが飛ばしたバージョンもカバーするようになりました。バックグラウンド更新で複数のバージョンを一度に飛び越えても、その間の変更が見えなくなりません。",
        ],
        "ko": [
            "이제 Voxis가 아무 소리도 들리지 않을 때 알려줍니다. 소리가 들어오지 않으면 조용한 화면 앞에 두는 대신 몇 초 안에 상황을 말해 줍니다. 비디오 모드는 컴퓨터에서 나오는 소리를 번역합니다 — 마이크에 말한 내용이 아닙니다.",
            "세션의 첫 몇 초가 더 이상 비어 있지 않습니다. 연결 중임을 볼 수 있고, 누군가 말을 시작한 뒤 몇 초 후에 첫 번역이 나온다는 안내도 표시됩니다.",
            "릴리스 노트가 건너뛴 버전까지 다룹니다. 여러 버전을 한 번에 넘기는 백그라운드 업데이트도 그 사이의 변경 사항을 숨기지 않습니다.",
        ],
        "nl": [
            "Voxis laat het nu weten als het niets hoort: komt er geen geluid binnen, dan zegt het dat binnen enkele seconden in plaats van je voor een stil scherm te laten zitten. De Video-modus vertaalt het geluid dat uit je computer komt — niet wat je in de microfoon zegt.",
            "De eerste seconden van een sessie zijn niet langer leeg: je ziet dat er verbinding wordt gemaakt en je hoort dat de eerste vertaling een paar seconden na het begin van het spreken komt.",
            "De releasenotes dekken nu ook overgeslagen versies, zodat een achtergrondupdate over meerdere versies niet meer verbergt wat er tussendoor is veranderd.",
        ],
        "pl": [
            "Voxis teraz mówi, kiedy nic nie słyszy: jeśli nie dochodzi żaden dźwięk, informuje o tym w ciągu kilku sekund, zamiast zostawiać cię przed cichym ekranem. Tryb Wideo tłumaczy dźwięk wychodzący z komputera, a nie to, co mówisz do mikrofonu.",
            "Pierwsze sekundy sesji nie są już puste: widzisz, że trwa łączenie, i dowiadujesz się, że pierwsze tłumaczenie pojawi się kilka sekund po rozpoczęciu mowy.",
            "Informacje o wersji obejmują teraz pominięte wersje, więc aktualizacja w tle przeskakująca kilka wersji nie ukrywa już tego, co zmieniło się w międzyczasie.",
        ],
        "pt": [
            "Agora o Voxis avisa quando não ouve nada: se nenhum som está chegando, ele diz isso em segundos em vez de deixar você diante de uma tela silenciosa. O modo Vídeo traduz o som que sai do seu computador — não o que você fala no microfone.",
            "Os primeiros segundos de uma sessão não ficam mais em branco: você vê a conexão sendo feita e é avisado de que a primeira tradução chega alguns segundos depois de alguém começar a falar.",
            "As notas de versão agora cobrem as versões que você pulou, então uma atualização em segundo plano que salta várias versões não esconde mais o que mudou no meio.",
        ],
        "ro": [
            "Voxis te anunță acum când nu aude nimic: dacă nu ajunge niciun sunet, o spune în câteva secunde, în loc să te lase în fața unui ecran mut. Modul Video traduce sunetul care iese din computer — nu ce spui în microfon.",
            "Primele secunde ale unei sesiuni nu mai sunt goale: vezi că se conectează și afli că prima traducere vine câteva secunde după ce cineva începe să vorbească.",
            "Notele de versiune acoperă acum și versiunile sărite, așa că o actualizare din fundal care trece peste mai multe versiuni nu mai ascunde ce s-a schimbat între ele.",
        ],
        "ru": [
            "Теперь Voxis сообщает, когда вообще ничего не слышит: если звук не доходит, он говорит об этом за несколько секунд, а не оставляет вас перед молчащим экраном. Режим «Видео» переводит звук, выходящий из компьютера, а не то, что вы говорите в микрофон.",
            "Первые секунды сеанса больше не пустые: видно, что идёт подключение, и сообщается, что первый перевод придёт через несколько секунд после начала речи.",
            "Список изменений теперь охватывает и пропущенные версии, поэтому фоновое обновление через несколько версий больше не скрывает, что изменилось между ними.",
        ],
        "sr": [
            "Voxis sada kaže kada ništa ne čuje: ako zvuk ne dolazi, javi to za nekoliko sekundi umesto da te ostavi pred nemim ekranom. Video režim prevodi zvuk koji izlazi iz računara — a ne ono što govoriš u mikrofon.",
            "Prve sekunde sesije više nisu prazne: vidiš da se povezuje i saznaješ da prvi prevod dolazi nekoliko sekundi nakon što neko počne da govori.",
            "Beleške o verziji sada pokrivaju i verzije koje si preskočio, pa ažuriranje u pozadini koje preskoči više verzija ne skriva šta se u međuvremenu promenilo.",
        ],
        "sv": [
            "Voxis säger nu till när det inte hör något: om inget ljud kommer fram säger det det inom några sekunder i stället för att lämna dig framför en tyst skärm. Videoläget översätter ljudet som kommer ut ur datorn — inte det du säger i mikrofonen.",
            "De första sekunderna av en session är inte längre tomma: du ser att den ansluter och får veta att den första översättningen kommer några sekunder efter att någon börjat tala.",
            "Versionsinformationen täcker nu även versioner du hoppat över, så en bakgrundsuppdatering som hoppar flera versioner döljer inte längre vad som ändrats däremellan.",
        ],
        "th": [
            "ตอนนี้ Voxis จะบอกเมื่อไม่ได้ยินเสียงอะไรเลย: ถ้าไม่มีเสียงเข้ามา จะแจ้งให้ทราบภายในไม่กี่วินาที แทนที่จะปล่อยให้คุณนั่งมองหน้าจอที่เงียบอยู่ โหมดวิดีโอแปลเสียงที่ออกจากคอมพิวเตอร์ ไม่ใช่เสียงที่คุณพูดใส่ไมโครโฟน",
            "ไม่กี่วินาทีแรกของเซสชันไม่ว่างเปล่าอีกแล้ว: คุณเห็นว่ากำลังเชื่อมต่อ และได้รู้ว่าคำแปลแรกจะมาถึงไม่กี่วินาทีหลังจากมีคนเริ่มพูด",
            "บันทึกรุ่นครอบคลุมรุ่นที่คุณข้ามไปด้วย ดังนั้นการอัปเดตเบื้องหลังที่ข้ามหลายรุ่นจะไม่ซ่อนสิ่งที่เปลี่ยนไปในระหว่างนั้นอีก",
        ],
        "tr": [
            "Voxis hiçbir ses duymadığında artık söylüyor: ses ulaşmıyorsa sizi sessiz bir ekranın karşısında bırakmak yerine saniyeler içinde bunu bildiriyor. Video modu bilgisayarınızdan çıkan sesi çeviriyor — mikrofonunuza söylediklerinizi değil.",
            "Oturumun ilk saniyeleri artık boş değil: bağlandığını görüyorsunuz ve ilk çevirinin konuşma başladıktan birkaç saniye sonra geleceğini size söylüyor.",
            "Sürüm notları artık atladığınız sürümleri de kapsıyor; arka planda birkaç sürüm birden atlayan bir güncelleme aradaki değişiklikleri gizlemiyor.",
        ],
        "vi": [
            "Giờ đây Voxis lên tiếng khi không nghe thấy gì: nếu không có âm thanh nào đến, nó nói ngay trong vài giây thay vì để bạn ngồi trước một màn hình im lặng. Chế độ Video dịch âm thanh phát ra từ máy tính — không phải những gì bạn nói vào micrô.",
            "Những giây đầu của một phiên không còn trống trải: bạn thấy nó đang kết nối, và được cho biết bản dịch đầu tiên sẽ đến vài giây sau khi có người bắt đầu nói.",
            "Ghi chú phát hành giờ bao gồm cả những phiên bản bạn đã bỏ qua, nên một bản cập nhật ngầm nhảy qua nhiều phiên bản không còn che mất những thay đổi ở giữa.",
        ],
        "zh": [
            "现在听不到任何声音时，Voxis 会主动告诉你：如果没有声音传入，它会在几秒内说明，而不是让你对着安静的界面干等。视频模式翻译的是电脑播放出来的声音，不是你对着麦克风说的话。",
            "会话开始的头几秒不再是空白：你能看到正在连接，也会知道第一句翻译会在有人开口后的几秒内出现。",
            "版本说明现在会涵盖你跳过的版本，后台一次跨过好几个版本的更新，不会再让中间的改动无声无息。",
        ],
        "zh-Hant": [
            "現在聽不到任何聲音時，Voxis 會主動告訴你：如果沒有聲音傳入，它會在幾秒內說明，而不是讓你對著安靜的畫面乾等。影片模式翻譯的是電腦播放出來的聲音，不是你對著麥克風說的話。",
            "工作階段開始的頭幾秒不再是空白：你能看到正在連線，也會知道第一句翻譯會在有人開口後的幾秒內出現。",
            "版本說明現在會涵蓋你跳過的版本，背景一次跨過好幾個版本的更新，不會再讓中間的變更無聲無息。",
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
