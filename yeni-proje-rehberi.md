# Yeni proje rehberi (Kararsızım yolunu tekrar etmek için)

Bu dosya, Kararsızım'da izlediğimiz yolu başka bir projede (ör. chatbot) aynı düzenle tekrarlamak içindir.
İki tür adım var:

- 🧑 **SEN yaparsın** (hesap, panel, parola, gizli değer). Bunları Claude yapmaz.
- 🤖 **Claude yapar** (kod, test, commit). Sen sadece "şu fazı yap" dersin.

Yeni projenin ürün kuralları farklı olacak; aşağıdaki sıra, kurallar ve komutlar aynı kalır.

---

## 0. Çalışma biçimi (Kararsızım'dan taşınacak kurallar)

1. **Tek doğruluk kaynağı bir plan dosyası:** `docs/<proje>-proje-plani.md`. Ürün özeti, kurallar, veri modeli, uçlar, arayüz yönü ve fazlar orada. Claude her oturumda önce onu okur.
2. **Fazlarla ilerle.** Sadece söylediğin fazı yapar, kabul kriterleri sağlanınca durur ve özet verir. Sonraki faza kendiliğinden geçmez.
3. **Karar planda yoksa önce sorar**, netleşen karar planın "Netleştirilen kararlar" bölümüne yazılır.
4. **Yeni bağımlılık eklemeden önce sorar** (prototip ilkesi).
5. **Her fazda test yazılır** (`manage.py test`), faz bitince commit + push.
6. **Gizli değerler yalnızca ortam değişkeninde.** Claude gizli anahtar üretip dosyaya yazmaz; sen Vercel paneline/`.env`'ye girersin. `.env` git'e girmez.
7. **İsteğe bağlı güvenlik taraması:** `code-review-security` skill'i sadece sen istediğinde çalışır ("projeyi güvenlik açısından incele"). Faz 5 (yayın) öncesi önerilir.

İlk mesajın için şablon:

```
Yeni bir proje başlatıyorum: <bir cümlelik fikir>.
Kararsızım projesindeki yolu izle (Django + Supabase Postgres + Vercel, fazlı ilerleme, plan dosyası, CLAUDE.md).
Önce docs/ altında proje planını birlikte yazalım; kod yazmadan bana ürün kurallarıyla ilgili sorular sor.
```

---

## 1. Hazırlık (bir kez, yeni projede tekrar gerekmez)

| Gereken | Durum |
|---|---|
| Python 3.12 | 🧑 Kurulu olmalı (`python --version`) |
| Git + GitHub hesabı | 🧑 |
| Claude Code (bu uygulama) | 🧑 |
| Supabase hesabı | 🧑 Aynı hesap kullanılır |
| Vercel hesabı | 🧑 Aynı hesap kullanılır (ekip: MagNet/Hobby) |

---

## 2. Yeni proje oluşturma (Faz 0 öncesi)

### 2.1 Klasör ve GitHub deposu

🧑 Yeni klasörü oluştur ve Claude Code'u orada aç (ör. `C:\Users\unaln\PycharmProjects\dev\<yeni-proje>`).

🧑 GitHub'da **boş** bir depo aç (README/.gitignore ekleme): https://github.com/new
Depo adı proje adıyla aynı olsun. Adresi Claude'a söyle.

🤖 Claude şunları yapar:

```powershell
git init -b main
git remote add origin https://github.com/unalnamdar/<yeni-proje>.git
python -m venv .venv
.venv/Scripts/python.exe -m pip install Django==5.2.19 "psycopg[binary]==3.3.9" dj-database-url==3.1.2 python-dotenv==1.2.4
.venv/Scripts/python.exe -m pip freeze > requirements.txt   # sadeleştirilir: yalnızca 4 satır kalır
.venv/Scripts/django-admin.exe startproject config .
```

Ayrıca: `.gitignore` (`.env`, `.venv/`, `db.sqlite3`, `staticfiles/`, `.idea/`), `.env.example`, `.python-version` (`3.12`), `vercel.json`, `CLAUDE.md`, `README.md`.

`vercel.json` (veritabanıyla aynı bölge):

```json
{
  "$schema": "https://openapi.vercel.sh/vercel.json",
  "regions": ["fra1"]
}
```

### 2.2 `CLAUDE.md` içeriği

Kararsızım'daki `CLAUDE.md`'yi kopyala, şunları değiştir: proje adı, plan dosyası yolu, Supabase proje adı/ref, yayın adresi, GitHub adresi. "Çalışma şekli", "Kod kuralları", "Komutlar" ve "Git" bölümleri aynen kalır.

### 2.3 `settings.py` kalıpları (Claude yazar, referans)

- `LANGUAGE_CODE = "tr"`, `TIME_ZONE = "Europe/Istanbul"`, `USE_TZ = True`
- `SECRET_KEY`, `DEBUG`, `DATABASE_URL` ortam değişkenlerinden (`python-dotenv`)
- `DATABASE_URL` boşsa SQLite; doluysa `dj_database_url.parse(..., conn_max_age=0, ssl_require=not DEBUG)`
- Postgres için: `DISABLE_SERVER_SIDE_CURSORS = True` ve `OPTIONS["prepare_threshold"] = None` (Transaction pooler prepared statement desteklemez)
- `ALLOWED_HOSTS = [".vercel.app", "localhost", "127.0.0.1"]`, `CSRF_TRUSTED_ORIGINS = ["https://*.vercel.app"]`
- `STATIC_ROOT = BASE_DIR / "staticfiles"` (Vercel `collectstatic`'i kendisi çalıştırır)
- `DEBUG=False` iken: güvenli çerezler, `SECURE_PROXY_SSL_HEADER`, `SECURE_SSL_REDIRECT`, HSTS
- Özel kullanıcı modeli gerekiyorsa **ilk migration'dan önce** tanımlanır (`AUTH_USER_MODEL`)

---

## 3. Supabase: yeni proje açmak gerekir mi?

**Evet, her uygulama için ayrı Supabase projesi aç.** Aynı projeyi paylaşırsan tablolar, RLS ayarları ve parola tek yerde karışır; birini silmek ya da duraklatmak ötekini etkiler. (Ücretsiz planda aktif proje sayısı sınırlıdır; sınıra takılırsan eski bir projeyi duraklat veya sil.)

🧑 Adımlar:

1. https://supabase.com/dashboard → **New project**
2. Ad: proje adıyla aynı (ör. `<yeni-proje>`). Bölge: **Central EU (Frankfurt) `eu-central-1`** (Vercel `fra1` ile aynı bölge).
3. **Database password**: güçlü bir parola belirle ve bir yere kaydet. Claude'a yazma, sohbete yapıştırma; sadece `.env`'ye ve Vercel paneline gireceksin.
4. Proje hazır olunca **Connect** düğmesine bas ve iki bağlantı dizesini kopyala:
   - **Session pooler** (port `5432`): yerel `.env` ve migration'lar için.
   - **Transaction pooler** (port `6543`): Vercel için.
5. Host adı projeye göre değişir (Kararsızım'da `aws-1-eu-central-1.pooler.supabase.com`, `aws-0` değil). Panelden kopyaladığını kullan, elle yazma.

Dize kalıbı (parolayı sen yazarsın):

```
postgresql://postgres.<proje-ref>:<PAROLA>@aws-1-eu-central-1.pooler.supabase.com:5432/postgres   # Session  (.env)
postgresql://postgres.<proje-ref>:<PAROLA>@aws-1-eu-central-1.pooler.supabase.com:6543/postgres   # Transaction (Vercel)
```

> Parolada `@ : / ? #` gibi özel karakter varsa URL'de kodlanması gerekir; en kolayı parolayı yalnızca harf ve rakamdan oluşturmak.

🧑 Yerel `.env` dosyasını oluştur (`.env.example`'dan kopyala) ve doldur:

```powershell
Copy-Item .env.example .env
```

```
SECRET_KEY=<aşağıdaki komutla üret>
DEBUG=True
DATABASE_URL=<Session pooler dizesi, port 5432>
```

`SECRET_KEY` üretmek (çıktıyı doğrudan `.env`'ye ve Vercel'e yapıştır, başka yere yazma):

```powershell
.venv/Scripts/python.exe -c "from django.core.management.utils import get_random_secret_key as k; print(k())"
```

### 3.1 Migration'ları Supabase'e uygulama (🧑 veya 🤖, `.env` Supabase'e bağlıyken)

```powershell
.venv/Scripts/python.exe manage.py migrate
```

- Migration'lar **Vercel build'inde çalışmaz**; her şema değişikliğinde yerelden uygulanır.
- **Sıra önemli:** yeni bir migration içeren kodu pushlamadan **önce** migration'ı Supabase'e uygula; yoksa canlı site hata verir.

### 3.2 RLS (güvenlik, her yeni tablodan sonra)

Supabase `public` şemasındaki tabloları Data API ile dışarı açabilir. Django tablo sahibi olduğu için RLS'ten etkilenmez, o yüzden tüm tablolarda RLS'i politikasız aç:

```sql
alter table public.<tablo_adi> enable row level security;
```

Supabase panelinde **SQL Editor**'e yapıştırabilirsin ya da Claude'a "RLS aç ve güvenlik uyarılarını kontrol et" de (Supabase bağlantı aracıyla yapar). Kararsızım'da ayrıca `anon`/`authenticated` yetkileri geri alındı. Aynısını istersen Claude'dan iste.
Kontrol: Supabase → **Advisors → Security** sayfasında uyarı kalmamalı.

---

## 4. Vercel: yeni proje açmak gerekir mi?

**Evet, her uygulama için ayrı Vercel projesi.** Her projenin kendi ortam değişkenleri ve adresi olur.

🧑 Adımlar (kodun GitHub `main` dalında olduğundan emin olduktan sonra):

1. https://vercel.com/new → doğru ekibi seç (MagNet / Hobby) → GitHub deposunu **Import** et. (Depo listede yoksa **Adjust GitHub App Permissions** ile erişim ver.)
2. Framework **Django** olarak algılanır; **Build / Output ayarlarına dokunma.**
3. **Deploy'a basmadan önce** Environment Variables bölümüne ekle (Production, Preview ve Development kutularını işaretle):

   | Ad | Değer | Not |
   |---|---|---|
   | `SECRET_KEY` | Yeni üretilmiş uzun rastgele dize | **Sensitive** işaretle. Kararsızım'ınkini kullanma, yenisini üret. |
   | `DATABASE_URL` | **Transaction pooler** dizesi (6543) | **Sensitive** işaretle. |
   | `DEBUG` | `False` (ya da hiç tanımlama) | |

   (Projeye göre ekler: `EMAIL_*` için SMTP değerleri, chatbot için API anahtarı. Bkz. 6. bölüm.)
4. **Deploy**'a bas, build'in bitmesini bekle.
5. Canlı adresi **Project → Settings → Domains** sayfasından teyit et ve Claude'a söyle. Vercel proje adı başkasına aitse adrese ek getirir (Kararsızım'da `kararsizim.vercel.app` başkasına aitti, bizimki `kararsizim-orcin.vercel.app`). Claude, adresi teyit etmeden canlıya istek atmaz.
6. Ortam değişkenini sonradan eklersen/değiştirirsen: **Deployments → son deploy → ⋯ → Redeploy** (yoksa eski değerle çalışır).

Yönetici hesabı (Django admin kullanılacaksa), `.env` Supabase'e bağlıyken yerelde:

```powershell
.venv/Scripts/python.exe manage.py createsuperuser
```

Parolayı komut sorar; sohbete yazma.

---

## 5. Faz sırası (Kararsızım'daki gibi)

Her faz: 🤖 kod + test → 🤖 commit + push → 🧑 kabul kriterlerini gözle → sonraki faz.

| Faz | İçerik | Senin işin |
|---|---|---|
| **Plan** | Ürün özeti, kurallar, veri modeli, uçlar, arayüz yönü, fazlar `docs/` altında yazılır | Soruları yanıtla, planı onayla |
| **0 İskelet** | Django projesi, settings, `.env.example`, `CLAUDE.md`, tokens.css, taban şablon | GitHub deposunu aç, `.env` oluştur |
| **1 Üyelik** | Kayıt/giriş/çıkış (gerekiyorsa) | Yerelde dene |
| **2…4** | Ürünün asıl özellikleri, sonra arayüz cilası | Yerelde dene, geri bildirim ver |
| **5 Yayın** | Supabase + Vercel kurulumu, RLS, `check --deploy` | 3. ve 4. bölümdeki adımlar |
| **6 Sonrası** | İstenirse: e-posta, alan adı, ek özellikler | İstediğini seç |

Yerelde çalıştırma ve test:

```powershell
.venv/Scripts/python.exe manage.py runserver
.venv/Scripts/python.exe manage.py test
.venv/Scripts/python.exe manage.py makemigrations
.venv/Scripts/python.exe manage.py migrate
```

- **Hızlı test (SQLite):** `.env` Supabase'e bağlıysa bile `.env`'ye dokunmadan: `$env:DATABASE_URL=""; .venv/Scripts/python.exe manage.py test`
- **Supabase'e karşı test:** `manage.py test --keepdb` (~3 dk; pooler açık bağlantı tuttuğu için test veritabanı silinemez).
- **Yayın öncesi ayar denetimi:**

```powershell
$env:DEBUG="False"; $env:SECRET_KEY="<uzun-rastgele>"; .venv/Scripts/python.exe manage.py check --deploy
```

Her faz sonunda commit mesajı İngilizce, dosyalar tek tek eklenir (`git add -A` yok), `.env` ve `.idea/` commit'lenmez:

```powershell
git add <dosya1> <dosya2>
git commit -m "Phase N: short description"
git push origin main
```

(İlk pushta: `git push -u origin main`.)

---

## 6. Chatbot projesine özel eklemeler

Kararsızım'da yapay zekâ API'si **yok**; chatbot için şunları ekleyeceğiz. Bunlar planda karara bağlanmalı (Claude kod yazmadan önce soracak):

1. **Hangi model/API?** Anthropic (Claude), OpenAI vb. Seçime göre SDK bağımlılığı eklenir (`anthropic` paketi gibi); bağımlılık kuralı gereği Claude önce sorar.
2. **API anahtarı:** 🧑 sağlayıcının konsolundan **yeni, yalnızca bu proje için** bir anahtar oluştur (ör. Anthropic Console → API Keys). Anahtar:
   - yerelde `.env`'ye (`ANTHROPIC_API_KEY=...`), Vercel'de **Sensitive** ortam değişkeni olarak girilir;
   - sohbete yapıştırılmaz, koda yazılmaz, git'e girmez, tarayıcıya (JS) gönderilmez. Tüm çağrılar sunucudan yapılır.
   - Sağlayıcı panelinde **harcama limiti** koy; kullanım ücretlidir.
3. **Maliyet ve kötüye kullanım koruması:** Kararsızım'daki yaklaşım taşınır: kullanıcı/IP başına istek sınırı (`RateLimitEvent` benzeri, veritabanı destekli), mesaj uzunluğu sınırı, giriş zorunluluğu kararı. Anonim herkese açık chatbot, API faturanı başkalarının kullanımına açar; bunu planda netleştir.
4. **Vercel süre sınırı:** serverless fonksiyonların çalışma süresi sınırlıdır; uzun yanıtlar için akış (streaming) ya da kısa yanıt tasarla. Claude, güncel sınırı Vercel dokümanından kontrol eder.
5. **Konuşma geçmişi:** Supabase'te tablo olarak tutulur (dosya sistemi kalıcı değil). Yeni tablo → RLS aç (3.2). Kişisel veri sakladığın için gizlilik kuralı (ör. e-posta görünmez) planda yazılmalı.
6. **Güvenlik:** kullanıcı metni modele giderken "prompt injection" riskini planda ele al (modele sistem komutu dışında yetki verme, çıktıyı HTML olarak güvenli göster/kaçışla).
7. **Test:** API çağrıları testlerde taklit (mock) edilir; testler gerçek API'ye istek atmaz ve para harcamaz.

---

## 7. Hızlı kontrol listesi (yeni proje için)

🧑 Yapılacaklar sırasıyla:

- [ ] Yeni klasör + Claude Code oturumu, ilk mesaj (0. bölüm şablonu)
- [ ] Plan dosyasındaki soruları yanıtla, planı onayla
- [ ] GitHub'da boş depo aç
- [ ] Supabase'de **yeni proje** aç (Frankfurt), veritabanı parolasını kaydet
- [ ] Session pooler (5432) ve Transaction pooler (6543) dizelerini kopyala
- [ ] Yerel `.env` oluştur: `SECRET_KEY`, `DEBUG=True`, `DATABASE_URL` (Session)
- [ ] (Chatbot) API anahtarı oluştur, harcama limiti koy, `.env`'ye ekle
- [ ] Fazları sırayla yaptır; her faz sonunda yerelde dene
- [ ] Faz 5'te: `migrate` (Supabase'e), RLS aç, Advisors'ta uyarı kalmadığını gör
- [ ] Vercel'de **yeni proje** → depoyu içe aktar → ortam değişkenlerini ekle (Sensitive) → Deploy
- [ ] Domains sayfasındaki canlı adresi Claude'a söyle, canlı testi yaptır
- [ ] `createsuperuser` (gerekiyorsa)
- [ ] (İsteğe bağlı) "projeyi güvenlik açısından incele" de

## 8. Sık karşılaşılan sorunlar

| Belirti | Neden / çözüm |
|---|---|
| Canlıda 500, loglarda "relation does not exist" | Migration Supabase'e uygulanmamış; yerelden `migrate` çalıştır |
| Canlıda `DisallowedHost` / CSRF hatası | `ALLOWED_HOSTS` / `CSRF_TRUSTED_ORIGINS` alan adını kapsamıyor (özel alan adı eklediysen güncelle) |
| `prepared statement ... does not exist` | `DATABASE_URL` Transaction pooler'da ama `prepare_threshold=None` ayarı eksik |
| Yerelde bağlanamıyor / zaman aşımı | `.env`'deki dize Session pooler (5432) olmalı; host panelden kopyalanmalı |
| Ortam değişkenini ekledim ama etkisi yok | Vercel'de **Redeploy** gerekir |
| Test Supabase'te "database is being accessed" | `--keepdb` kullan |
| Vercel ortam değişkeni sızdı sanıyorsan | Anahtarı sağlayıcı panelinden iptal edip yenisini oluştur, Vercel'de güncelle, Redeploy |
