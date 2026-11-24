"""Bestory readiness check. Standard library only, so it runs before pip install.

Usage:  python check_setup.py
"""

import importlib.util
import os
import socket
import sys
from pathlib import Path
from urllib.parse import urlparse

ROOT = Path(__file__).resolve().parent
results = []  # (level, message)  level: OK / WARN / FAIL


def ok(msg):
    results.append(("OK", msg))


def warn(msg):
    results.append(("WARN", msg))


def fail(msg):
    results.append(("FAIL", msg))


def load_env(path):
    env = {}
    if not path.exists():
        return env
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.split(" #")[0].strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, v = line.split("=", 1)
        env[k.strip()] = v.strip().strip('"').strip("'")
    return env


# 1. Python version
v = sys.version_info
if (v.major, v.minor) == (3, 12):
    ok(f"Python {v.major}.{v.minor}.{v.micro}")
else:
    warn(f"Python {v.major}.{v.minor} (project targets 3.12, Vercel default)")

# 2. Virtualenv
if sys.prefix != getattr(sys, "base_prefix", sys.prefix):
    ok(f"Virtualenv active: {sys.prefix}")
else:
    warn("No virtualenv active (activate .venv before pip install)")

# 3. Project files
guide = ROOT / "CLAUDE.md"
if guide.exists():
    ok("CLAUDE.md present")
elif (ROOT / "CLAUDE_bestory.md").exists():
    warn("Guide is named CLAUDE_bestory.md; rename to CLAUDE.md so it auto-loads")
else:
    fail("Project guide not found")
(ok if (ROOT / ".env.example").exists() else fail)(".env.example present")
(ok if (ROOT / ".gitignore").exists() else warn)(
    ".gitignore present"
    if (ROOT / ".gitignore").exists()
    else ".gitignore missing (Phase 0 task; .env must be ignored)"
)

# 4. Packages
for mod, pkg in [
    ("django", "Django"),
    ("dj_database_url", "dj-database-url"),
    ("psycopg", "psycopg[binary]"),
    ("whitenoise", "whitenoise"),
    ("dotenv", "python-dotenv"),
    ("pydantic", "pydantic"),
    ("anthropic", "anthropic"),
]:
    if importlib.util.find_spec(mod):
        ok(f"package {pkg}")
    else:
        warn(f"package {pkg} not installed (Phase 0 will install it)")

# 5. .env
env = load_env(ROOT / ".env")
if not env:
    warn(".env missing: copy .env.example to .env and fill it in")
else:
    ok(".env found")
    for key in ("DJANGO_SECRET_KEY", "IP_HASH_SALT"):
        if env.get(key, "change-me") in ("", "change-me"):
            warn(f"{key} is still 'change-me'")
    provider = env.get("LLM_PROVIDER", "mock")
    if provider == "anthropic" and not env.get("ANTHROPIC_API_KEY"):
        fail("LLM_PROVIDER=anthropic but ANTHROPIC_API_KEY is empty")
    else:
        ok(f"LLM_PROVIDER={provider}")

    # 6. Database reachability (TCP only, no credentials sent)
    url = env.get("DATABASE_URL", "")
    if not url or "<" in url:
        warn("DATABASE_URL not filled in (needs Supabase pooler string)")
    else:
        p = urlparse(url)
        host, port = p.hostname, p.port or 5432
        try:
            socket.create_connection((host, port), timeout=6).close()
            ok(f"Database host reachable ({host}:{port})")
            if port == 5432:
                ok("Session pooler (5432): right choice for local .env and migrations")
        except OSError as e:
            fail(f"Cannot reach database {host}:{port} ({e})")
        if importlib.util.find_spec("psycopg"):
            try:
                import psycopg

                with psycopg.connect(url, connect_timeout=8) as conn:
                    conn.execute("select 1")
                ok("Database login + SELECT 1 works")
            except Exception as e:
                fail(f"Database login failed: {type(e).__name__}")

# 7. Internet
try:
    socket.create_connection(("api.anthropic.com", 443), timeout=6).close()
    ok("Internet: api.anthropic.com reachable")
except OSError:
    warn("Cannot reach api.anthropic.com (only matters for LLM_PROVIDER=anthropic)")

# Report
icons = {"OK": "[ OK ]", "WARN": "[WARN]", "FAIL": "[FAIL]"}
print("\nBestory setup check\n" + "-" * 40)
for lvl, msg in results:
    print(f"{icons[lvl]} {msg}")
n_fail = sum(1 for l, _ in results if l == "FAIL")
n_warn = sum(1 for l, _ in results if l == "WARN")
print("-" * 40)
print(f"{n_fail} fail, {n_warn} warn")
print("Ready for Phase 0." if n_fail == 0 else "Fix FAIL items first.")
sys.exit(1 if n_fail else 0)
