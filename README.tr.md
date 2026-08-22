# Voxis Live

**[English](README.md)** | **Türkçe** | **[Deutsch](README.de.md)**

![GitHub stars](https://img.shields.io/github/stars/VoxisLive/voxislive?style=social)
![License](https://img.shields.io/badge/license-PolyForm%20Strict%201.0.0-blue)

> Windows için gerçek zamanlı sesli çeviri — herhangi bir videoyu, oyunu veya toplantıyı canlı olarak kendi dilinizde dinleyin.
>
> Marka: **Voxis** · Site: **[voxislive.com](https://voxislive.com)** · Uygulamayı edinin: **[Microsoft Store](https://voxislive.com)**

> [!WARNING]
> **Bu depo Voxis'i çalıştırmanın bir yolunu sağlamaz.** Sesin nasıl yakalandığını, iletildiğini ve depolandığını herkesin doğrulayabilmesi için motorun ses-işleme kodundan derlenmiş, salt-okunur, seçilmiş bir kesittir — aşağıdaki [Kaynağı denetleyin](#kaynağı-denetleyin) bölümüne bakın. **Yalnızca [voxislive.com](https://voxislive.com), Microsoft Store listesi veya `github.com/VoxisLive/voxislive` adresindeki bu depoya güvenin.** Bu deponun başka GitHub hesaplarında kopyaları bulundu, bazıları başka yerlerde barındırılan yükleyicilere yönlendiriyor — bunlar **resmi değildir** ve kötü amaçlı olabilir. Bir fork veya klon "buradan Voxis'i derleyip çalıştırabilirsiniz" diyorsa bu iddia yanlıştır; [support@voxislive.com](mailto:support@voxislive.com) adresine bildirin.

---

## Genel bakış

Tarayıcı sekmesi dublajcıları yalnızca bir Chrome sekmesinde çalan sesi çevirebilir. Voxis **Windows sistem sesini doğrudan okur**, bu yüzden bilgisayarınızın çaldığı her şeyde çalışır — native oyunlar, masaüstü Zoom/Teams/Discord görüşmeleri, herhangi bir yerel video oynatıcı — sadece bir tarayıcı sekmesinde açık olanla sınırlı değil.

Voxis, Windows sistem sesini (video, oyun veya görüşmeden) yakalar, bulut tabanlı bir sesten-sese çeviri modeline akıtır ve konuşmacı konuşurken çevrilmiş konuşmayı gerçek zamanlı olarak geri oynatır — bu bir konuşma-metin → çeviri → metin-konuşma zinciri değil, native bir **simültane tercüman**dır.

İki çalışma modu:

- **Video / Oyun** — tek yönlü gelen çeviri; çeviri konuşurken orijinal ses kısılır.
- **Toplantı** — iki yönlü: karşı tarafın sesi sizin dilinize, sizin sesiniz karşı tarafın diline çevrilir ve görüşmeye sanal mikrofon olarak beslenir.

Her oturum kaydedilip **TXT / SRT / VTT** olarak dışa aktarılabilir; geçmiş oturumlar uygulama içi Geçmiş panelinde aranabilir kalır.

---

## Kaynağı denetleyin

"Görüşmelerinizi kaydetmiyoruz" sözünü size inanmanız için söylemiyoruz. Bu depo, gerçek Voxis motorundan **açıkça izin listelenmiş**, üretim kaynağından birebir kopyalanmış (gösteriş için yeniden yazılmamış) küçük bir kesit yayınlıyor — sesinizin geçtiği zinciri tam olarak kapsayan:

```
sistem sesi ──► yakalama ──► yerel VAD kapısı ──► çeviri oturumu ──► oynatıcı
           (process_loopback.py,     (vad.py,        (base_translator.py,      (audio_io.py,
            session_duck.py,          konuşma          translator.py — ağa       mix_core.py)
            win_audio.py)             olmayanı yerelde  çıkan TEK nokta)
                                      filtreler)
```

Bu dosyaların doğrulamanıza izin verdiği şeyler:

- **`app/base_translator.py`**, her iki çeviri motorumuzun da ağ gidiş-dönüşü için kullandığı paylaşılan oturum durum makinesidir — bağlan, ses gönder, çevrilmiş sesi al, hata durumunda yeniden bağlan. Sesin cihazdan çıktığı TEK yer burasıdır. Baştan sona okuyun: ikinci bir kanal, arka planda yükleme veya söylenenin loglanması yoktur.
- **`app/translator.py`**, bu bağlantının somut, eksiksiz bir örneğidir (Gemini entegrasyonumuz) — bir taslak değil.
- **`app/vad.py`**, sessizliğin hiçbir zaman ağa ulaşmadığını gösterir; sadece algılanan konuşma gönderilir.
- **`app/audio_recorder.py`**, yerel ses kaydının opt-in olduğunu, varsayılan olarak kapalı olduğunu ve **Toplantı modunda etkinleştirilmesinin imkansız olduğunu** gösterir — bu kontrol koddadır, sadece bir ayar değildir.
- **`app/transcript_store.py`**, transkriptlerin siz açıkça dışa aktarmadıkça veya paylaşmadıkça sadece kendi diskinize yazıldığını gösterir.
- **`app/report_scrub.py`**, opsiyonel bir hata raporu cihazınızdan çıkmadan önce tam olarak neyin (anahtarlar, token'lar, e-postalar, yerel kullanıcı adları) silindiğini gösterir.
- **`app/i18n.py`**, uygulamanın bu konuda ekranda gösterdiği gerçek metindir — uygulama içi gizlilik açıklaması dahil.

`docs/PRIVACY.md`, `docs/TERMS.md` ve `docs/` altındaki diğer dosyalar aynı iddiaların sade dildeki halidir.

**Burada olmayan ve neden olmadığı:** orkestrasyon katmanı, arayüz, ücretli çeviri motoru entegrasyonlarımız, kalite ayarları ve hesap/faturalama kodu yayınlanmıyor. Hiçbiri sesin nasıl işlendiğini değiştirmiyor — yukarıdaki mekanizma hangi motor aktif olursa olsun aynı — ve bunu yayınlamak şeffaflık açısından hiçbir fayda sağlamadan rakiplere ayar ve iş mantığımızı verir. `scripts/check_release_hygiene.py`, bu sınırın kaymasını mekanik olarak engelleyen kapıdır; bu depoda tracked olan her dosya orada açıkça adlandırılmak zorundadır.

Bu depo **[PolyForm Strict 1.0.0](LICENSE)** ile lisanslıdır: okuyabilir ve alıntılayabilirsiniz, ama yeniden dağıtma, çatallama (fork) veya türev eser oluşturma hakkı vermez. Bkz. [Lisans](#lisans--polyform-strict-100).

---

## Mimari (yayınlanan dosyalar)

| Modül | Ne gösteriyor |
| --- | --- |
| `app/process_loopback.py` | Driverless WASAPI loopback yakalama; Voxis'in kendi ses çıktısını dışlar, kendi sesini asla tekrar çevirmez |
| `app/session_duck.py`, `app/win_audio.py` | Diğer uygulamaların nasıl kısıldığı ve çıkış uç noktalarının nasıl değiştirildiği — süreç içinde ses başka bir yere kopyalanmaz |
| `app/audio_io.py`, `app/mix_core.py` | Cihaz yakalama, stereo oynatıcı ve look-ahead limiter |
| `app/vad.py` | Yerel Silero VAD kapısı — bir şey gönderilmeden önce sessizlik filtrelenir |
| `app/base_translator.py` | Paylaşılan çeviri-oturumu durum makinesi — tek ağ çıkış noktası |
| `app/translator.py` | Eksiksiz, somut bir çeviri motoru bağlantısı (Gemini) |
| `app/audio_recorder.py` | Opsiyonel yerel çift-track kayıt — opt-in, sadece Video/Oyun modu |
| `app/transcript_store.py` | Sadece yerel transkript kalıcılığı ve TXT/SRT/VTT dışa aktarımı |
| `app/report_scrub.py` | Opsiyonel bir hata raporu gönderilmeden önce uygulanan istemci tarafı silme |
| `app/i18n.py` | Uygulama içi gerçek durum ve gizlilik açıklaması metni |
| `app/paths.py` | Yerel verinin (transkriptler, modeller) diskte gerçekte nerede durduğu |

`tests/` altında birkaç dosya bu modülleri doğrudan çalıştırır (`test_mix_core.py`, `test_ring.py`, `test_player_volume.py`, `test_audio_test_tone.py`, `test_speech_gate.py`, `test_session_duck.py`, `test_report_scrub.py`, `test_transcript_export.py`, `test_audio_recorder.py`) ve her push'ta CI'da çalışır — bkz. [Quality workflow](.github/workflows/quality.yml). Bunlar okumak ve aynı iddiaların ikinci, çalıştırılabilir bir biçimi olsun diye eklendi — bu ağaçtan tam uygulamayı derlemeye bir davet değil.

---

## Toplantı modu kurulumu (iki yönlü çeviri)

Bu bölüm kurulu uygulamayı kullananlar için; kaynaktan derlemekle ilgili değil.

**Hedef:** siz Türkçe konuşun → karşı taraf İngilizce duysun; karşı taraf İngilizce konuşsun → siz Türkçe duyun.

| Yön | Ne yapar | Gereksinim |
| --- | --- | --- |
| **Gelen** (karşı tarafı kendi dilinizde duyarsınız) | Sistem sesini dinler, çevirir, kulaklığınıza çalar | Ek kurulum yok |
| **Giden** (sesiniz çevrilerek gider) | Mikrofonunuzu çevirir, sanal bir mikrofona besler | Sanal mikrofon (VB-CABLE) gerekir |

Windows'ta bir toplantı uygulamasının (Teams/Zoom/Meet) seçebileceği bir "mikrofon" sunmanın tek yolu sanal bir ses sürücüsüdür, bu yüzden giden yön buna ihtiyaç duyar. Kurulu değilse toplantılar otomatik olarak **sadece dinleme** modunda çalışır.

1. Ücretsiz bir sanal kablo kurun, örn. [VB-CABLE](https://vb-audio.com/Cable/) — yükleyicisini yönetici olarak çalıştırın, yeniden başlatın.
2. Voxis'te **Çıkış cihazı**nı gerçek kulaklığınıza, **Mikrofon**u gerçekten konuştuğunuz cihaza ayarlayın. Kurulu sanal kablo otomatik algılanır; elle yönlendirme gerekmez.
3. Toplantı uygulamanızda **mikrofonu** kablonun *kayıt* cihazına ayarlayın (örn. "CABLE Output") — Voxis çevrilmiş sesinizi buraya yazar.
4. Voxis'i başlatın → **Toplantı** modu. Kendi dilinizde konuşun → çevrilerek gider; karşı taraf kendi dilinde konuşsun → siz çevrilmiş olarak duyarsınız.

---

## Gecikme ve simültane çeviri

Uçtan uca gecikme kabaca cümle uzunluğu artı birkaç saniyedir — bu, çeviri modelinin tasarlanmış *kulak-ses aralığıdır* (bir insan simültane tercümanın yaptığı gibi, doğru çevirmek için yeterli bağlamı bekler), istemci tarafı bir ayar değildir. "Daha hızlı" diye bir anahtar yoktur; daha kısa bir tampon gecikmeyi kaldırmaz, doğruluğu hıza feda eder.

---

## Sorun giderme

| Belirti | Neden | Çözüm |
| --- | --- | --- |
| Toplantı sadece dinleme modunda | Sanal mikrofon kurulu değil | Sanal kablo kurun (yukarıya bakın) |
| Çeviri sesi duyulmuyor | Çıkış cihazı sanal kabloya ayarlı | Çıkış cihazını gerçek kulaklığınıza yönlendirin |
| `PaError -9999` | Eski Windows ses cihazı listesi | Ses cihazını çıkarıp takın, Voxis'i yeniden başlatın |

Başka bir sorun için uygulama içi **Sorun bildir**i kullanın (gönderilmeden önce tam olarak neyin silindiği için `app/report_scrub.py`'ye bakın) veya bir [GitHub Issue](https://github.com/VoxisLive/voxislive/issues) açın.

---

## Lisans — PolyForm Strict 1.0.0

Bu depo **[PolyForm Strict License 1.0.0](LICENSE)** ile lisanslıdır.

- ✅ Okuyabilir, alıntılayabilir, kişisel/ticari olmayan referans amaçlı kullanabilirsiniz.
- ❌ Kopyalarını dağıtma, çatallama (fork) veya bundan bir türev eser — Voxis'in değiştirilmiş veya "özgür" bir derlemesi dahil — oluşturma hakkı **vermez**.

**Ticari lisanslama, veya bu kesiti okumanın ötesindeki her kullanım** (ticari ürünler, SaaS, white-label): **<https://voxislive.com/licensing>**.

Bu depoya kod katkısı kabul etmiyoruz (bkz. [`.github/CONTRIBUTING.md`](.github/CONTRIBUTING.md)) — altında bir türev eser hakkı verilmediği ve bu, ürünün gerçek kaynak ağacı olmadığı için.

---

## Destek

- **Uygulamayla ilgili sorun/hata bildirimi:** [GitHub Issues](https://github.com/VoxisLive/voxislive/issues)
- **Güvenlik:** [`.github/SECURITY.md`](.github/SECURITY.md)
- **Ticari sorular:** <https://voxislive.com/licensing>
- **Gizlilik politikası:** [`docs/PRIVACY.md`](docs/PRIVACY.md)

*Voxis Live — gerçek zamanlı, simültane sesli çeviri.*
