# Voxis Live

**[English](README.md)** | **Türkçe** | **[Deutsch](README.de.md)**

![GitHub stars](https://img.shields.io/github/stars/VoxisLive/voxislive?style=social)
![License](https://img.shields.io/badge/license-All%20Rights%20Reserved-blue)

**VoxisLive, bilgisayarında çalan sesi (video, oyun, toplantı) gerçek zamanlı çeviren ve çeviriyi kendi dilinde sesli okuyan bir masaüstü uygulamasıdır (Windows; Linux için Snap Store): altyazı değil, bir ses duyarsın.** İki yönlü Toplantı modunda karşı taraf da seni sanal bir mikrofon üzerinden kendi dilinde duyar. 79 hedef dil; günde 10 dakikalık ücretsiz katman (79 dilin 35'i sesli); ön ödemeli dakikalar, abonelik yok; Microsoft Store'da.

Ücretsiz günlük dakikalar Video ve Oyun modunda geçerli; ücretsiz sesi olmayan 44 dil canlı altyazı olarak gelir. Ücretli dakika paketleri 79 dilin hepsini seslendirir ve Toplantı modunu açar.

**İndir:** [Microsoft Store](https://apps.microsoft.com/detail/9P5Z0KVS58RS) (Windows 10 ve 11) · [Snap Store](https://snapcraft.io/voxis) (Linux) · Site: **[voxislive.com](https://voxislive.com)** · [Fiyatlar](https://voxislive.com/pricing)

> [!WARNING]
> **Bu depo Voxis'i çalıştırmanın bir yolunu sunmaz.** Sesin nasıl yakalandığını, iletildiğini ve saklandığını herkesin doğrulayabilmesi için motorun ses işleyen kodundan seçilmiş, salt okunur bir kesittir — aşağıdaki [Kaynağı denetle](#kaynağı-denetle) bölümüne bak. **Yalnızca [Microsoft Store](https://apps.microsoft.com/detail/9P5Z0KVS58RS), [Snap Store](https://snapcraft.io/voxis) ve [voxislive.com](https://voxislive.com) üzerinden gelen indirmelere güven** — bu depoda indirilecek bir şey yok. Bu deponun başka GitHub hesaplarında kopyaları bulundu, bazıları başka yerlerde barındırılan yükleyicilere yönlendiriyor — bunlar **resmi değildir** ve kötü amaçlı olabilir. Bir fork ya da klon "Voxis'i buradan derleyip çalıştırabilirsin" diyorsa bu iddia yanlıştır; [support@voxislive.com](mailto:support@voxislive.com) adresine bildir.

---

## Genel bakış

Voxis **sistem sesini doğrudan okur** (Windows'ta WASAPI, Linux'ta PipeWire), bu yüzden bilgisayarında ne çalıyorsa onunla çalışır — yerel oyunlar, masaüstü Zoom/Teams/Discord görüşmeleri, yerel bir video oynatıcı ya da herhangi bir tarayıcıdaki video.

Voxis, sistem sesini (video, oyun ya da görüşmeden) yakalar, bulut tabanlı bir sesten sese çeviri modeline akıtır ve konuşan kişi konuşurken çevrilmiş konuşmayı gerçek zamanlı olarak çalar — bu bir konuşma-metin → çeviri → metin-konuşma zinciri değil, doğal bir **simültane tercüman**dır.

İki çalışma modu:

- **Video / Oyun** — tek yönlü gelen çeviri; çeviri konuşurken orijinal ses kısılır.
- **Toplantı** — iki yönlü: karşı tarafın sesi senin diline, senin sesin karşı tarafın diline çevrilir ve görüşmeye sanal mikrofon olarak verilir.

Her oturum kaydedilip **TXT / SRT / VTT** olarak dışa aktarılabilir; geçmiş oturumlar uygulama içindeki Geçmiş panelinde aranabilir kalır.

---

## Kaynağı denetle

"Görüşmelerini kaydetmiyoruz" sözüne körü körüne inanmanı beklemiyoruz. Bu depo, gerçek Voxis motorundan **açıkça izin listesine alınmış**, üretim kaynağından birebir kopyalanmış (gösteriş için yeniden yazılmamış) küçük bir kesit yayınlıyor — sesinin geçtiği zinciri tam olarak kapsayan:

```
sistem sesi ──► yakalama ──► yerel VAD kapısı ──► çeviri oturumu ──► oynatıcı
           (process_loopback.py,     (vad.py,        (base_translator.py,      (audio_io.py,
            session_duck.py,          konuşma          translator.py — Live      mix_core.py)
            win_audio.py)             olmayanı yerelde  oturumu bağlantısı)
                                      filtreler)
```

Bu dosyalarla neleri doğrulayabilirsin:

- **`app/base_translator.py`**, iki gerçek zamanlı çeviri motorumuzun Live gidiş-dönüşü için kullandığı oturum durum makinesidir — bağlan, ses gönder, çevrilmiş sesi al, hata olursa yeniden bağlan. Baştan sona oku: arka planda yükleme ya da söylenenlerin kaydı yoktur. Ücretsiz katmanın günlük dakikaları ayrı bir istek yolu kullanır — algılanan her konuşma parçası için bir HTTPS çağrısı yapılır, geriye çevrilmiş metin gelir ve cihazında seslendirilir; bu yol yayınlanmayan orkestrasyon katmanındadır. Önünde yine aynı türden yerel bir konuşma algılama kapısı durur.
- **`app/translator.py`**, bu bağlantının somut ve eksiksiz bir örneğidir (Gemini entegrasyonumuz) — bir taslak değil.
- **`app/vad.py`**, yerel konuşma kapısıdır: kapının konuşma olmadığına karar verdiği ses, gönderilmeden önce dijital sessizlikle değiştirilir; böylece müzik, gürültü ve ortam sesi cihazdan ses olarak çıkmaz. Kapı kararı buradadır; değiştirme adımı yayınlanmayan orkestrasyon katmanındadır.
- **`app/audio_recorder.py`**, yerel ses kaydının isteğe bağlı olduğunu, varsayılan olarak kapalı geldiğini ve **Toplantı modunda açılmasının imkânsız olduğunu** gösterir — bu kontrol koddadır, yalnızca bir ayar değildir.
- **`app/transcript_store.py`**, transkriptlerin sen açıkça dışa aktarmadıkça ya da paylaşmadıkça yalnızca kendi diskine yazıldığını gösterir.
- **`app/report_scrub.py`**, isteğe bağlı bir hata raporu cihazından çıkmadan önce tam olarak neyin (anahtarlar, token'lar, e-postalar, yerel kullanıcı adları) silindiğini gösterir.
- **`app/i18n.py`**, uygulamanın bu konuda ekranda gösterdiği gerçek metindir — uygulama içi gizlilik açıklaması dahil.

`docs/PRIVACY.md`, `docs/TERMS.md` ve `docs/` altındaki diğer dosyalar aynı iddiaların sade dildeki halidir.

**Burada olmayanlar ve nedeni:** orkestrasyon katmanı, arayüz, ücretli çeviri motoru entegrasyonlarımız, kalite ayarları ve hesap/faturalama kodu yayınlanmıyor. Hiçbiri yukarıdaki yakalama ve konuşma kapısı zincirini değiştirmiyor; bu zincir her motorun önünde durur — ve bunları yayınlamak, şeffaflığa hiçbir katkı sağlamadan rakiplere ayarlarımızı ve iş mantığımızı verir. `scripts/check_release_hygiene.py`, bu sınırın kaymasını mekanik olarak engelleyen kapıdır; bu depoda izlenen her dosya orada açıkça adıyla yazılmak zorundadır.

Bu depodaki kod **[tüm hakları saklı bir bildirim](LICENSE)** altında yayınlanmıştır: okuyabilirsin, ama kullanma, kopyalama, yeniden dağıtma, çatallama (fork) ya da türev eser oluşturma hakkı vermez — kişisel veya ticari olmayan kullanım dahil. Aşağıdaki [Lisans](#lisans) bölümüne bak.

---

## Mimari (yayınlanan dosyalar)

| Modül | Ne gösteriyor |
| --- | --- |
| `app/process_loopback.py` | Sürücüsüz WASAPI loopback yakalama; Voxis'in kendi ses çıkışını dışarıda bırakır, böylece kendi sesini asla yeniden çevirmez |
| `app/session_duck.py`, `app/win_audio.py` | Diğer uygulamaların sesinin nasıl kısıldığı ve çıkış uç noktalarının nasıl değiştirildiği — süreç içinde ses başka bir yere kopyalanmaz |
| `app/audio_io.py`, `app/mix_core.py` | Cihazdan yakalama, stereo oynatıcı ve look-ahead limiter |
| `app/vad.py` | Yerel Silero VAD kapısı — bir şey gönderilmeden önce konuşma olmayan ses susturulur |
| `app/base_translator.py` | Gerçek zamanlı motorların çeviri oturumu durum makinesi — Live oturumunun ağ bağlantısı |
| `app/translator.py` | Eksiksiz, somut bir çeviri motoru bağlantısı (Gemini) |
| `app/audio_recorder.py` | İsteğe bağlı yerel çift kanallı kayıt — varsayılan kapalı, yalnızca Video/Oyun modu |
| `app/transcript_store.py` | Yalnızca yerel transkript saklama ve TXT/SRT/VTT dışa aktarma |
| `app/report_scrub.py` | İsteğe bağlı bir hata raporu gönderilmeden önce istemci tarafında yapılan temizleme |
| `app/i18n.py` | Uygulama içindeki gerçek durum ve gizlilik açıklaması metni |
| `app/paths.py` | Yerel verilerin (transkriptler, modeller) diskte gerçekte nerede durduğu |

`tests/` altındaki birkaç dosya bu modülleri doğrudan çalıştırır (`test_mix_core.py`, `test_ring.py`, `test_player_volume.py`, `test_audio_test_tone.py`, `test_speech_gate.py`, `test_session_duck.py`, `test_report_scrub.py`, `test_transcript_export.py`, `test_audio_recorder.py`) ve her push'ta CI'da koşar — bkz. [Quality workflow](.github/workflows/quality.yml). Bunlar okunmak ve aynı iddiaların ikinci, çalıştırılabilir bir biçimi olsun diye burada — bu ağaçtan uygulamanın tamamını derlemeye bir davet değil.

---

## Toplantı modu kurulumu (iki yönlü çeviri)

Bu bölüm kurulu uygulamayı kullananlar için; kaynaktan derlemekle ilgili değil.

**Hedef:** sen Türkçe konuşursun → karşı taraf İngilizce duyar; karşı taraf İngilizce konuşur → sen Türkçe duyarsın.

| Yön | Ne yapar | Gereksinim |
| --- | --- | --- |
| **Gelen** (karşı tarafı kendi dilinde duyarsın) | Sistem sesini dinler, çevirir, kulaklığına çalar | Toplantı modunun parçası; Toplantı modu aşağıdaki sanal kabloyu gerektirir |
| **Giden** (sesin çevrilerek gider) | Mikrofonunu çevirir, sanal bir mikrofona verir | Sanal mikrofon (VB-CABLE) gerekir |

Windows'ta bir toplantı uygulamasının (Teams/Zoom/Meet) seçebileceği bir "mikrofon" sunmanın tek yolu sanal bir ses sürücüsüdür, bu yüzden giden yön buna ihtiyaç duyar. **Windows'ta sanal kablo kurulu değilse Toplantı modu başlamaz.**

1. Ücretsiz bir sanal kablo kur, örneğin [VB-CABLE](https://vb-audio.com/Cable/) — yükleyicisini yönetici olarak çalıştır, bilgisayarı yeniden başlat.
2. Voxis'te **Çıkış cihazı**'nı gerçek kulaklığına, **Mikrofon**'u gerçekten konuştuğun cihaza ayarla. Kurulu sanal kablo otomatik algılanır; elle yönlendirme gerekmez.
3. Toplantı uygulamanda **mikrofonu** kablonun *kayıt* cihazına ayarla (örneğin "CABLE Output") — Voxis çevrilmiş sesini buraya yazar.
4. Voxis'i başlat → **Toplantı** modu. Kendi dilinde konuş → çevrilerek gider; karşı taraf kendi dilinde konuşur → sen çevrilmiş halini duyarsın.

---

## Gecikme ve simültane çeviri

Gecikme, çeviri modelinin tasarımı gereği olan *kulak-ses aralığıdır* — bir insan simültane tercüman gibi, doğru çevirmek için yeterli bağlamı bekler — istemci tarafında bir tampon değildir. Uygulamadaki **Hızlı mod** altyazıyı hemen gösterir ve çevrilmiş sesin 1,5×'e kadar hızlanarak yetişmesini sağlar; modelin aralığını kısaltmaz.

---

## Sorun giderme

| Belirti | Neden | Çözüm |
| --- | --- | --- |
| Toplantı modu başlamıyor (Windows) | Sanal kablo kurulu değil | VB-CABLE gibi bir sanal kablo kur (yukarıya bak), sonra Toplantı'yı yeniden başlat |
| Çeviri sesi duyulmuyor | Çıkış cihazı sanal kabloya ayarlı | Çıkış cihazını gerçek kulaklığına yönlendir |
| `PaError -9999` | Windows ses cihazı listesi eskimiş | Ses cihazını çıkarıp yeniden tak, Voxis'i yeniden başlat |

Başka bir sorun için uygulama içindeki **Sorun bildir**'i kullan (gönderilmeden önce tam olarak neyin silindiğini `app/report_scrub.py`'de görebilirsin) ya da bir [GitHub Issue](https://github.com/VoxisLive/voxislive/issues) aç.

---

## Lisans

Bu depo, gizlilik iddialarımızı kendin doğrulayabilesin diye var — yukarıdaki [Kaynağı denetle](#kaynağı-denetle) bölümüne bak. Okumak ücretsizdir ve lisans gerektirmez; üzerine bir şey inşa etmek gerektirir. Bu, kaynağı görülebilen ama kullanım için lisanslanmamış bir kesittir ve **[tüm hakları saklı bir bildirim](LICENSE)** altında yayınlanmıştır.

- ✅ Kodu okuyabilir; yorum, eleştiri ya da güvenlik araştırması için kısa alıntılar yapabilirsin.
- ❌ Kullanma, kopyalama, dağıtma, çatallama (fork) ya da türev eser oluşturma hakkı **vermez** — ticari olsun olmasın, kişisel kullanım dahil. Voxis Live bedava dağıtılmaz, satılır: dağıttığımız şey resmi uygulamadır; kendi API anahtarınla kullanım (BYOK) da o uygulamanın içinde tek seferlik bir kilit açma olarak satılır. Burada hiçbir şey bunu değiştirmez.

**Ticari lisanslama ya da bu kesiti okumanın ötesindeki her kullanım** (ticari ürünler, SaaS, white-label): **<https://voxislive.com/licensing>**.

Bu depoya kod katkısı kabul etmiyoruz (bkz. [`.github/CONTRIBUTING.md`](.github/CONTRIBUTING.md)) — katkı yapılabilecek bir lisans yok ve bu, ürünün gerçek kaynak ağacı değil.

---

## Destek

- **Uygulamayla ilgili sorun/hata bildirimi:** [GitHub Issues](https://github.com/VoxisLive/voxislive/issues)
- **Güvenlik:** [`.github/SECURITY.md`](.github/SECURITY.md)
- **Ticari sorular:** <https://voxislive.com/licensing>
- **Gizlilik politikası:** [`docs/PRIVACY.md`](docs/PRIVACY.md)

*Voxis Live — gerçek zamanlı, simültane sesli çeviri.*
