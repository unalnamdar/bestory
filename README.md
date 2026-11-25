# Bestory

Bir ürün kategorisini (ör. "kablosuz kulaklık") seçtiğin ülkedeki güncel verilere göre analiz eden web uygulaması: en çok satanlar, en yüksek puanlılar, fiyat/performans ya da kendi yazdığın ölçüt. Canlı: https://bestory.vercel.app

Ayrıntılı plan ve tüm tasarım kararları için `CLAUDE.md`.

## Mimari (özet)

```
Tarayıcı (templates/ + static/js, framework yok)
   │  POST /api/search/  (JSON, CSRF header)
   ▼
Django 5.2 (Vercel Python function, bestory/wsgi.py)
   ├─ search/   istek doğrulama (pydantic) → önbellek → günlük limit → sağlayıcı → şema + fiyat kontrolleri → SearchLog
   │    └─ providers/  mock | anthropic | gemini | tavily_gemini   (LLM_PROVIDER ile seçilir)
   ├─ accounts/ custom User, kayıt / giriş (e-posta veya kullanıcı adı) / çıkış / profil, giriş denemesi sınırı
   └─ core/     ana sayfa, /api/health/, 404/500, robots.txt
   │
   ▼
Supabase Postgres (yalnızca veritabanı; Supabase Auth ve Data API kullanılmaz, tüm tablolarda RLS açık)
```

- Statik dosyalar WhiteNoise ile, hash'li adlarla sunulur (Vercel build'inde `collectstatic`).
- Oturumlar veritabanında tutulur (serverless ile uyumlu). Ham IP adresi hiçbir yerde saklanmaz (tuzlu SHA-256).
- Kullanıcı ve LLM metinleri tarayıcıda yalnızca `textContent` ile basılır; yalnızca `https://` linkler tıklanabilir.

## Lokal kurulum (Windows / PowerShell)

```powershell
python -m venv .venv
.venv\Scripts\Activate.ps1
pip install -r requirements.txt
Copy-Item .env.example .env        # sonra .env içini doldur
.venv\Scripts\python.exe check_setup.py
.venv\Scripts\python.exe manage.py migrate
.venv\Scripts\python.exe manage.py createsuperuser
.venv\Scripts\python.exe manage.py runserver
```

- Ana sayfa: http://127.0.0.1:8000/ — sağlık kontrolü: http://127.0.0.1:8000/api/health/ — admin: http://127.0.0.1:8000/admin/
- `.env` içinde `DATABASE_URL` boşsa ya da `sqlite:///db.sqlite3` ise uygulama lokal SQLite kullanır; Supabase'e hiç bağlanmadan denemek için kullanışlıdır (o zaman önce `migrate`).
- **Dikkat (PowerShell):** `$env:DATABASE_URL=''` değişkeni boşaltmaz, **siler**; o zaman `.env`'deki Supabase adresi devreye girer. Tek seferlik SQLite için `$env:DATABASE_URL='sqlite:///db.sqlite3'` kullan.

### Testler

```powershell
.venv\Scripts\python.exe manage.py check
.venv\Scripts\python.exe manage.py test
```

Testler `DATABASE_URL` ne olursa olsun **her zaman geçici bir SQLite veritabanında** çalışır (Supabase'te `test_*` veritabanı açılmaz) ve ağa çıkmaz: LLM ve web araması hep mock'lanır. (Bilerek Postgres'te çalıştırmak için `TEST_ON_DATABASE_URL=1`.)

## Arayüzü deneme (mock veri)

`LLM_PROVIDER=mock` iken arama sahte "kablosuz kulaklık" verisi döndürür (1,5 sn yapay gecikme, `MOCK_DELAY_SECONDS`). Her sorgu aynı örnek ürünleri gösterir; mod, bütçe, puan ve sonuç sayısı filtreleri listeye uygulanır. Hata ekranını görmek için "Bana bir şiir yaz" ara (ürün değil → 422). Paylaşılabilir link örneği: `/?q=kablosuz+kulakl%C4%B1k&country=TR&mode=value`.

## Üyelik

- Sayfalar: `/hesap/kayit/`, `/hesap/giris/` (`?next=` destekli), `/hesap/cikis/` (yalnızca POST), `/hesap/profil/`.
- Giriş e-posta **veya** kullanıcı adıyla yapılır. Kullanıcı adı 3–20 karakter (`a-z`, `0-9`, `_`, `.`), küçük harfe çevrilir; `admin`, `bestory`, `root` gibi adlar yasaktır.
- E-posta hiçbir herkese açık sayfada, API yanıtında veya günlükte görünmez; yalnızca kendi profil sayfanda.
- Profil sayfası son 10 farklı başarılı aramanı listeler; tıklayınca arama aynı filtrelerle yeniden açılır (24 saat içindeyse önbellekten, arama hakkından düşmeden).
- Üyeler günde 20, üye olmayanlar 5 yeni analiz yapabilir. Çok sayıda başarısız girişten sonra kısa süre beklemek gerekir (hesap başına 5, IP başına 10 / 10 dk).

## Gerçek analiz (LLM + web araması)

`LLM_PROVIDER` ile sağlayıcı seçilir: `mock` (anahtarsız), `anthropic`, `gemini` veya `tavily_gemini` (ücretsiz katman dostu).

### Anthropic (Claude)

1. Anthropic Console'dan **yalnızca bu proje için** yeni bir API anahtarı oluştur ve harcama limiti koy.
2. `.env` içinde: `LLM_PROVIDER=anthropic`, `ANTHROPIC_API_KEY=...` (anahtarı sohbete yapıştırma, koda yazma).
3. Web search organizasyon için varsayılan olarak açıktır; bir yönetici kapattıysa API 400 döner. Açmak için Console → Settings → Capabilities.
4. Model `ANTHROPIC_MODEL` ile seçilir (eski `LLM_MODEL` adı da okunur) (`claude-sonnet-5-5`; daha ucuz: `claude-haiku-5-5`). Bir arama 20–60 sn sürebilir.

Maliyet (yaklaşık, tahmin): web search 1000 aramada 10 USD + token ücreti. Sonnet 5.5 için giriş 2 / çıkış 10 USD (1M token başına). 5 aramalı tek bir analiz kabaca 0,10–0,25 USD civarındadır; gerçek tutarı Console'da ilk denemelerden sonra doğrula.

### Google Gemini

1. https://aistudio.google.com adresinden API anahtarı al. **Önemli:** güncel Gemini 3+ modellerinde Google Search ile arama ücretsiz katmanda yok; faturalandırmayı (paid tier) açman gerekir. Ücretler dokümana göre (özet, resmi sayfada doğrula): Gemini 3+ için ayda 5.000 arama sonrası 1.000 arama başına 14 USD; günlük 1.500 arama sınırı. Her model sorgusu birden çok arama yapabilir ve sayısı kısıtlanamaz.
2. `.env`: `LLM_PROVIDER=gemini`, `GEMINI_API_KEY=...` (sohbete yapıştırma). Model `GEMINI_MODEL` ile seçilir, varsayılan `gemini-3.5-flash-lite` (en ucuz kararlı model; kalite için `gemini-3.8-flash` denenebilir).
3. Ücretsiz katmanda içerik Google tarafından ürün geliştirmede kullanılabilir; ücretli katmanda kullanılmaz. Bestory konuşmayı Google'da saklatmaz (`store=false`).
4. Analiz hep "çok yoğun" diyorsa ve günlükte `429 ... check your plan and billing details` görüyorsan anahtar ücretsiz katmandadır; AI Studio'da faturalandırmayı aç.
5. Tek bir gerçek aramayı veritabanına yazmadan denemek için: `.venv\Scripts\python.exe live_check.py` (ücretlidir).
6. Aramalar ülkeye göre yönlendirilemez (ülke yalnızca prompt'ta belirtilir) ve `LLM_MAX_SEARCHES` yalnızca modele "en fazla N arama yap" talimatı olarak gider; kesin sınır değildir. Maliyet kontrolü için günlük limit ve cache önemlidir.

### Tavily + Gemini (ücretsiz seçenek)

Aramayı Tavily yapar, Gemini (arama aracı olmadan) JSON'u yazar. Gemini'nin aramalı çağrısı ücretsiz katmanda kapalı olduğu için bu kombinasyon eklendi.

1. https://www.tavily.com adresinde ücretsiz hesap aç (kart gerekmez: ayda 1.000 kredi, basit arama 1 kredi) ve API anahtarı oluştur.
2. `.env`: `LLM_PROVIDER=tavily_gemini`, `TAVILY_API_KEY=...`, `GEMINI_API_KEY=...` (anahtarları sohbete yapıştırma).
3. Bir analiz en fazla 3 Tavily araması yapar (`LLM_MAX_SEARCHES` ile azaltılabilir) → ayda yaklaşık 300 analiz. Kredi bitince Tavily durur, kullanıcı "Web araması şu an kullanılamıyor" mesajını görür.
4. Kaynak linkleri yalnızca Tavily'nin döndürdüğü adreslerden seçilebilir; modelin uydurduğu link otomatik atılır.
5. Sınırlar: Tavily sonuçları kısa özetlerdir (~500 karakter); fiyat/puan çoğu üründe bulunamayabilir ve boş (`null`) kalır. Model sayfaları kendisi gezip ek arama yapamaz.

### Fiyat doğruluğu

- Her üründe güncel fiyat zorunludur; fiyatı belirlenemeyen ürün listelenmez. Aralık tutarlı olmalıdır (`price_max ≥ price_min`, en fazla 3 kat).
- Bütçe filtresi (en düşük/en yüksek) modele güvenilmeden kodda uygulanır.
- `tavily_gemini` sağlayıcısında fiyat ayrıca doğrulanır: model, fiyatı gösteren metni arama özetinden birebir alıntılamak zorundadır; alıntı özette yoksa ya da fiyatı içermiyorsa ürün atılır. Kartta "Fiyat: <site> · <tarih>" görünür.
- `anthropic` ve `gemini` (kendi aramalı) sağlayıcılarda kaynak metni görünmediği için bu kanıt kontrolü yapılamaz.

### Ortak davranış

- **Önbellek:** aynı (ürün, ülke, mod, filtre, özel istek, sağlayıcı) 24 saat (`CACHE_TTL_HOURS`) saklanır, limitten düşmez. Süresi dolanları silmek için: `python manage.py purge_search_cache`.
- **Limit:** üye olmayan IP başına günde 5, üye başına 20 yeni analiz (son 24 saat, kayan pencere). Lokal denemede sık arıyorsan `.env`'de `RATE_LIMIT_ANON_PER_DAY` değerini yükselt. Lokal `.env` Supabase'e bağlıysa arama kayıtları (`SearchLog`) orada tutulur.

## Ortam değişkenleri

Şablon: `.env.example`. `.env` asla git'e girmez; anahtarları sohbete veya koda yapıştırma.

| Değişken | Lokal | Vercel (Production + Preview) | Açıklama |
|---|---|---|---|
| `DJANGO_SECRET_KEY` | istersen boş | **zorunlu**, yeni üret | `DJANGO_DEBUG=False` iken boşsa uygulama açılmaz. |
| `DJANGO_DEBUG` | `True` | **`False`** | `False` iken HTTPS yönlendirme, güvenli çerezler, HSTS açılır. |
| `DJANGO_ALLOWED_HOSTS` | varsayılan | varsayılan yeter | Varsayılan: `localhost,127.0.0.1,.vercel.app`. Özel alan adında ekle. |
| `CSRF_TRUSTED_ORIGINS` | varsayılan | varsayılan yeter | Varsayılan: `http://localhost:8000,https://*.vercel.app`. |
| `DATABASE_URL` | Session pooler (5432) | **Transaction pooler (6543)** | Supabase → Connect. Boşsa SQLite. |
| `LLM_PROVIDER` | `mock` | `tavily_gemini` (şu anki seçim) | `mock` / `anthropic` / `gemini` / `tavily_gemini`. |
| `ANTHROPIC_API_KEY`, `ANTHROPIC_MODEL` | | sağlayıcıya göre | `anthropic` için. |
| `GEMINI_API_KEY`, `GEMINI_MODEL`, `GEMINI_FALLBACK_MODEL` | | sağlayıcıya göre | `gemini` ve `tavily_gemini` için. Varsayılan model `gemini-3.5-flash-lite`, yedek `gemini-3.6-flash`. |
| `TAVILY_API_KEY` | | sağlayıcıya göre | `tavily_gemini` için. |
| `LLM_MAX_SEARCHES` | `5` | `5` | Analiz başına en fazla web araması. |
| `LLM_TIMEOUT_SECONDS` | `90` | `90` | Toplam süre bütçesi. `vercel.json` `maxDuration` (135 sn) bundan büyük kalmalı. |
| `CACHE_TTL_HOURS` | `24` | `24` | Önbellek süresi. |
| `RATE_LIMIT_ANON_PER_DAY` / `RATE_LIMIT_USER_PER_DAY` | `5` / `20` | `5` / `20` | Günlük yeni analiz sınırı. |
| `IP_HASH_SALT` | herhangi | **zorunlu**, rastgele uzun dize | IP özetleri için tuz. Değiştirirsen sayaçlar sıfırlanır. |
| `DEFAULT_COUNTRY` | `TR` | `TR` | Ülke tespit edilemezse. |
| `SECURE_HSTS_SECONDS` | | opsiyonel | Varsayılan 1 yıl. |

Rastgele anahtar / tuz üretmek için:

```powershell
.venv\Scripts\python.exe -c "from django.core.management.utils import get_random_secret_key as k; print(k())"
```

## Supabase güvenliği

Uygulama Supabase Data API'sini (PostgREST) kullanmaz; Django tablo sahibi rolüyle bağlanır.

- Tüm `public` tablolarında RLS açık ve **hiç policy yok** → `anon`/`authenticated` rolleri hiçbir satırı göremez, Django etkilenmez. `core/migrations/0001_enable_rls.py` mevcut tabloları, yeni tablo ekleyen migration'lar kendi tablolarını açar. Ayrıca projede Supabase'in `ensure_rls` event trigger'ı açık: `public`'te yeni oluşan her tabloda RLS otomatik açılır.
- `core/migrations/0002_revoke_rls_auto_enable.py`, bu trigger'ın `rls_auto_enable()` fonksiyonunu çağırma yetkisini `anon`/`authenticated`'dan alır (Advisors uyarısı).
- Kontrol: Supabase → Advisors → Security. Beklenen tek bulgu her tablo için **INFO** "RLS Enabled No Policy" — bilinçli tercihtir (policy yok = API'den erişim yok).
- Elle kontrol (SQL Editor):

```sql
select relname, relrowsecurity, has_table_privilege('anon', oid, 'SELECT') as anon_select
from pg_class where relnamespace = 'public'::regnamespace and relkind = 'r';
```

Her satırda `relrowsecurity = true` olmalı.

## Deploy (Vercel)

1. Kodu GitHub'a it, https://vercel.com/new ile depoyu içe aktar (framework Django olarak algılanır, giriş `bestory/wsgi.py`).
2. Project → Settings → Environment Variables (Production + Preview): yukarıdaki tablodaki **zorunlu** değerler ve seçtiğin sağlayıcının anahtarları. Değişkenleri sonradan değiştirirsen **Redeploy** et.
3. **Migration'lar Vercel build'inde çalışmaz.** Şema değişen bir commit'i push etmeden **önce** lokalden çalıştır:
   ```powershell
   .venv\Scripts\python.exe manage.py migrate
   ```
   (lokal `.env` Supabase'e bağlıyken). Yeni kolonlar geriye uyumlu (nullable) eklenir; böylece migrate ile yeni deploy arasındaki kısa sürede eski kod çalışmaya devam eder.
4. Statik dosyalar: `STATIC_ROOT` tanımlı olduğu için Vercel build sırasında `collectstatic` çalıştırır.
5. `vercel.json`: bölge `fra1` (Supabase eu-central-1'e yakın), `maxDuration` 135 sn.
6. Admin hesabı: lokal `.env` Supabase'e bağlıyken `.venv\Scripts\python.exe manage.py createsuperuser`.
7. Production güvenlik ayarlarını doğrulamak için:
   ```powershell
   $env:DJANGO_DEBUG='False'; $env:DJANGO_SECRET_KEY='gecici-uzun-rastgele-bir-dize-en-az-50-karakter-olmali-1234567890'; .venv\Scripts\python.exe manage.py check --deploy
   ```
   Beklenen: "no issues (1 silenced)" (HSTS preload uyarısı bilinçli olarak kapalı: `*.vercel.app` zaten preload listesinde). Lokal `.env`'deki `IP_HASH_SALT` kısa/örnek değerse `bestory.W001` uyarısı da çıkar; production'daki değer uzun ve rastgele olmalı. Bu iki değişken o PowerShell penceresinde kalır; sonra pencereyi kapat.

### Canlı duman testi

1. `https://bestory.vercel.app/api/health/` → `{"status": "ok", "db": true}`.
2. Ana sayfa açık ve koyu temada düzgün; tema butonu üç durumu (açık / koyu / otomatik) döndürüyor, sayfa yenilenince tema korunuyor.
3. Üye olmadan bir arama → sonuç kartları, kaynak linkleri yeni sekmede açılıyor; aynı arama tekrar → "önbellekten" etiketi, kalan hak azalmıyor.
4. "Bana bir şiir yaz" → anlaşılır "ürün değil" mesajı.
5. `/hesap/kayit/` → kayıt → başlıkta kullanıcı adı. Çıkış yap → e-posta ile giriş → kullanıcı adıyla giriş.
6. Profil → e-posta yalnızca burada; "Son aramaların" listesinde yaptığın arama var; tıklayınca önbellekten açılıyor.
7. Yanlış parola → "Bilgiler hatalı."; `/olmayan-sayfa` → Bestory 404 sayfası.
8. Telefonda (veya 375 px genişlikte) başlık taşmıyor, kartlar tek sütun.

## Bilinen sınırlamalar

- Veriler LLM + web aramasıyla derlenir; fiyat, puan ve "çok satan" bilgisi hatalı veya eski olabilir. Bu yüzden her üründe kaynak linki zorunlu ve arayüzde uyarı var. Fiyat kanıtı kontrolü yalnızca `tavily_gemini` sağlayıcısında yapılabiliyor.
- Tavily çoğunlukla kategori/liste sayfaları döndürür; puan bilgisi ürünlerin yarısından azında bulunur. Ücretsiz Tavily planı ayda yaklaşık 300 analiz eder.
- Gerçek bir analiz 10–60 sn sürer; Gemini modelleri yoğunlukta 503 verebilir (bir yeniden deneme + yedek model var).
- Günlük limit eşzamanlı isteklerde 1 fazla aşılabilir. Giriş denemesi sınırı, birinin başkasının hesabını 10 dakika kilitlemesine izin verir (prototip için kabul).
- Kayıt formu e-posta/kullanıcı adının kayıtlı olup olmadığını söyler; bot kaydına karşı koruma yok. Parola sıfırlama ve e-posta doğrulama yok.
- Ürün görseli yok (baş harfli yer tutucu). Arayüz yalnızca Türkçe. Paylaşım önizlemesi (Open Graph) görselsiz.
