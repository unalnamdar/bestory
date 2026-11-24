# Bestory

Ürün kategorisi analiz uygulaması (Django + Supabase Postgres + Vercel). Ayrıntılı plan için `CLAUDE.md`.

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

- Ana sayfa: http://127.0.0.1:8000/ — sağlık kontrolü: http://127.0.0.1:8000/api/health/
- Hızlı test (SQLite, Supabase'e dokunmaz): `$env:DATABASE_URL=""; .venv\Scripts\python.exe manage.py test`

## Arayüzü deneme (mock veri)

`LLM_PROVIDER=mock` iken arama sahte "kablosuz kulaklık" verisi döndürür (1,5 sn yapay gecikme, `MOCK_DELAY_SECONDS`). Her sorgu aynı örnek ürünleri gösterir; mod, bütçe, puan ve sonuç sayısı filtreleri listeye uygulanır. Hata ekranını görmek için "Bana bir şiir yaz" ara (ürün değil → 422). Paylaşılabilir link örneği: `/?q=kablosuz+kulakl%C4%B1k&country=TR&mode=value`.

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

### Ortak davranış

- **Önbellek:** aynı (ürün, ülke, mod, filtre, özel istek, sağlayıcı) 24 saat (`CACHE_TTL_HOURS`) saklanır, limitten düşmez. Süresi dolanları silmek için: `python manage.py purge_search_cache`.
- **Limit:** üye olmayan IP başına günde 5, üye başına 20 yeni analiz (son 24 saat, kayan pencere). Lokal denemede sık arıyorsan `.env`'de `RATE_LIMIT_ANON_PER_DAY` değerini yükselt. Lokal `.env` Supabase'e bağlıysa arama kayıtları (`SearchLog`) orada tutulur.

## Ortam değişkenleri

`.env.example` dosyasına bak. `.env` asla git'e girmez. Önemli olanlar:

| Değişken | Açıklama |
|---|---|
| `DJANGO_SECRET_KEY` | Rastgele uzun dize. `DJANGO_DEBUG=False` iken zorunlu. |
| `DATABASE_URL` | Lokal: Supabase **Session pooler** (5432). Vercel: **Transaction pooler** (6543). Boşsa SQLite. |
| `LLM_PROVIDER` | `mock` (anahtarsız) veya `anthropic` (Faz 2). |

Secret key üretmek için:

```powershell
.venv\Scripts\python.exe -c "from django.core.management.utils import get_random_secret_key as k; print(k())"
```

## Supabase güvenliği

Uygulama Supabase Data API'sini kullanmaz. `core/migrations/0001_enable_rls.py` migration'ı, o an var olan tüm `public` tablolarında RLS'i (politikasız) açar. **Yeni model/tablo eklediğinde** aynısını o tablo için de yap (SQL Editor):

```sql
alter table public.<tablo_adi> enable row level security;
```

Kontrol: Supabase → Advisors → Security.

## Deploy (Vercel)

1. Kodu GitHub'a it, https://vercel.com/new ile depoyu içe aktar (framework Django olarak algılanır).
2. Deploy'dan önce Environment Variables (Production + Preview): `DJANGO_SECRET_KEY` (yeni üret), `DATABASE_URL` (Transaction pooler, 6543), `DJANGO_DEBUG=False`. Sonradan değiştirirsen **Redeploy** et.
3. Migration'lar Vercel build'inde çalışmaz; şema değişince önce lokalden `migrate` çalıştır, sonra push et.
4. Statik dosyalar: `STATIC_ROOT` tanımlı olduğu için Vercel build sırasında `collectstatic` çalıştırır.
5. Canlıda `/api/health/` → `{"status":"ok","db":true}` dönmeli.

## Bilinen sınırlamalar

Bkz. `CLAUDE.md` bölüm 15.
