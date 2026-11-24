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
