# 3D Print Studio — Blender eklentisi

3D baskı için tasarlanan modellerin, gerçekten basılmış gibi görünen
fotogerçekçi görsellerini üretmek için Blender eklentisi (Blender 4.2+, 5.2 ile test edildi).
Arayüz İngilizcedir.

*A Blender add-on that turns 3D-print models into photorealistic "already printed" renders:
real sliced layer geometry at true scale, slicer-accurate top/bottom skin, printer flaws,
filament palette, scanned photo textures and ready-made rooms and props. UI in English.*

![Turuncu PLA Benchy, 0.2 mm katman, 1:1 ölçek](docs/images/benchy_orange.jpg)

| %100 yakın plan | Masa sahnesi | Üst yüzey testi |
|---|---|---|
| ![](docs/images/benchy_orange_100pct.jpg) | ![](docs/images/desk_scene.jpg) | ![](docs/images/top_layer_test.jpg) |

## Kurulum

1. Zip'i oluşturun (Blender'ın kendi Python'u ile):
   `"C:/Program Files/Blender Foundation/Blender 5.2/blender.exe" -b --factory-startup --python tools/paketle.py`
   → `dist/print3d_studio-1.0.0.zip` oluşur.
2. Blender → *Edit > Preferences > Get Extensions* → sağ üstteki ▾ → **Install from Disk…** → zip'i seçin.
3. 3D görünümde **N** → **3D Print** sekmesi.

Geliştirme sırasında kurmadan denemek için:

```bash
"C:/Program Files/Blender Foundation/Blender 5.2/blender.exe" --python tools/dev_start.py
```

## Hızlı kullanım

1. STL/3MF modelinizi içe aktarın ve seçin.
2. **One-Click Scene** → model mm'den gerçek boyuta ölçeklenir, filament malzemesi
   uygulanır, oda + masa + dekor (kesim matı, lamba, makara, bitki, kitaplar, kupa)
   kurulur, model mata oturtulur, ışık, ürün kamerası ve Cycles ayarları yapılır,
   görünüm kameraya geçer.
3. **Render > Render Image** (F12).

## Paneller

| Panel | İçerik |
|---|---|
| Print & Filament | Type / Color, Layer Height, Line Width, **Direction** (basım yönü: Z+/Z-/X/Y/Custom Angle), Layer Visibility, Layer Irregularity, Seam, Top Surface Lines, Color Cycle Height. Değişiklikler canlı uygulanır. |
| Material Library | Ahşap, metal, taş, kumaş, deri, cam, seramik, duvar/zemin, kesim matı, PEI… Her malzeme kendi yüzey kabartmasıyla (bump) gelir. |
| Room & Environment | Ölçülü oda (duvar/zemin, pencere, tavan, süpürgelik) veya kıvrımlı stüdyo fonu. |
| Props | Masa, sehpa, sandalye, kitaplık, raf, kitaplar (kapak + sayfa bloğu), masa lambası (gerçek ışıklı), sukulent, kupa, kalemlik, kesim matı, PEI tabla, filament makarası, laptop, halı, tablo + kendi kütüphaneniz. |
| Lighting & Camera | Daylight (Window), Golden Hour, Studio, Evening, HDRI. Ürün kamerası: odak, diyafram (bokeh), açı. |
| Render | Preview / Final / Ultra, sosyal medya boyutları, GPU. |
| Extend Palette | Kalıcı yeni filament rengi ve yeni malzeme. |

## Gerçekçilik notları

- Masa: yağlı meşe, birleştirilmiş lamellerle (her lamel farklı ton), düzensiz yıllık
  halkalar, lif çizgileri, gözenek kabartması ve saten (dağınık) parlaklık.
- Kesim matı: mat PVC mikro dokusu, nane yeşili ızgara, kenarda cetvel çizgileri,
  çapraz kılavuz çizgileri, hafif bıçak izleri, kenarda açık renkli çekirdek katmanı.
- Katman çizgileri gerçek ölçekte hesaplanır (bump mesafesi = bir gerçek katman, abartı yok);
  yakın çekimde ve 2K+ çözünürlükte belirginleşir.
- **Real Layer Geometry** (varsayılan açık): model bir slicer gibi her katmanın ortasından
  kesilip katman kalınlığında yeniden kurulur (`scene/slicer.py`). Eğimli tavanlar gerçek
  teraslar, siluetler gerçek merdiven olur. Orijinal mesh saklanır; kapatınca geri gelir
  (modeli düzenlemek için kapatın). Benchy: 240 katman, ~5 sn. Delikli (manifold olmayan)
  mesh'lerde açık konturlar 5 katman yüksekliğine kadar boşluklardan birleştirilir.
- **Yüzey kuralı (slicer gibi):** dilimleyici her kapak yüzünü sınıflandırır (`p3d_skin`):
  üstünde bir sonraki katman yoksa *üst yüzey* (çevre çizgileri + dolgu), altında önceki katman
  yoksa *alt yüzey* (sarkık, mat çizgiler), ilk katman *tabla yüzü* (bastırılmış, parlak).
  Açıklığı ~0.25 mm'den (≈ 0.6 çizgi genişliği) dar çıkıntılar ve üstü kapalı yüzeyler doku
  almaz; z-wobble'ın duvarlarda her katmanda yarattığı mikro basamaklar bu yüzden temiz kalır.
  Sınırı kesen kapak üçgenleri, sınıf netleşene kadar en uzun kenarından bölünür.
- Üst yüzey (top layer): her katman kapağında kenardan içeri 2 çevre çizgisi (gerçek kenar
  mesafesi dilimleyicide `p3d_edge` niteliği olarak hesaplanır; ince duvarlarda daralır), içte
  katman başına yön değiştiren 45° dolgu. Her çizginin yüksekliği/parlaklığı farklı, çizgiler
  hafif dalgalı ve boylarınca ~0.5 mm'lik ekstrüzyon dalgalanması var.
- **Print Imperfections** (1 = iyi ayarlı hobi yazıcı): 8 mm vida adımlı ~0.01 mm z-wobble,
  katmanlar arası ~0.008 mm genişlik farkı, ilk katmanda 0.15 mm elephant foot.
  **Dust & Handling**: üst yüzeylerde seyrek toz zerrecikleri, hafif mat el izleri.
  Tüm kenarlar ~0.07 mm yuvarlatılır (Bevel).
- **Lens Effects** (Render paneli): hafif lens bozulması ve renk saçılması, bloom, vinyet,
  sensör greni. **Camera Roll**: kadraja 0.6° doğal eğim.
- `tools/top_test.py`: ahşap masada 40×40×5 mm kare baskıyı sıyırma ışıkla render eder
  (üst yüzey kontrolü).
- **Fotoğraf dokular (Poly Haven, CC0):** Material Library > Wood içindeki "(Photo)" malzemeler
  ve masa, gerçek taranmış ahşap kullanır (renk + normal + pürüzlülük, gerçek boyutunda;
  ör. Oak Veneer 1.83 m). İlk kullanımda indirilir ve kullanıcı klasöründe saklanır.
  Bunun için *Preferences > System > Network > Allow Online Access* açık olmalı; kapalıysa
  önbellekteki başka bir çözünürlük, o da yoksa prosedürel ahşap kullanılır. Çözünürlük:
  eklenti tercihlerinde *Photo Texture Resolution* (varsayılan 4K ≈ 43 MB/ahşap, 8K ≈ 150 MB).
  Doku pikselinden küçük lif ve gözenekler prosedürel eklenir. Eşyalar gerçek ölçekli
  (1 UV = 1 m) kutu projeksiyonlu UV ile oluşturulur.
- Kapalıyken aynı terasları shader taklit eder (katman başına `katman / tan(eğim)` genişliğinde
  düz teras, yuvarlak çevre kenarı, kenara paralel iki çevre çizgisi, içte çapraz dolgu).
- STL'ler düz gölgeli gelir; malzeme uygulanınca eğri yüzeyler yumuşatılır, 35° üstü kenarlar keskin kalır.
- Kalibrasyon: `tools/benchy_calib.py` modeli 1:1 ölçekte stüdyo fonunda render eder
  (`samples/benchy.stl`, sonuçlar `renders/calib`).

## Paleti genişletmek

- Panelden: **Extend Palette**. Eklenenler kullanıcı klasörüne yazılır
  (`user_filaments.json`, `user_materials.json`), güncellemede kaybolmaz.
- Kendi eşyanız: seçin → **Props > My Asset Library > Save**. Ya da `.blend`
  dosyalarını `print3d_studio/assets/` veya tercihlerdeki *Extra Asset Folder* içine koyun.
- Kodla: `data/filaments.json`, `data/materials.json`, kurucular `materials/surfaces.py`,
  eşyalar `scene/furniture.py` (`@item(...)`).

## Testler

```bash
# arka planda tam sahne + tüm eşyalar
"C:/Program Files/Blender Foundation/Blender 5.2/blender.exe" -b --factory-startup --python tools/test_render.py -- renders/test.png DESK_DAY 64 PLA_SILK --all
# yakın çekim gerçekçilik kontrolü
"C:/Program Files/Blender Foundation/Blender 5.2/blender.exe" -b --factory-startup --python tools/closeup_test.py -- renders/close.png 384 PLA_BASIC 1.15 14
# gerçek Blender penceresinde arayüz testi (ekran görüntüleri renders/ui içine)
"C:/Program Files/Blender Foundation/Blender 5.2/blender.exe" --factory-startup --python tools/ui_test.py -- renders/ui
```

## Lisans ve kaynaklar

- Eklenti kodu: [GPL-3.0-or-later](LICENSE) (Blender eklentileri için gerekli lisans).
- Fotoğraf dokular: [Poly Haven](https://polyhaven.com), CC0. Depoda değil, ilk kullanımda indirilir.
- Örnek model: #3DBenchy, Creative Tools, CC BY-ND 4.0 — bkz. [samples/README.md](samples/README.md).
