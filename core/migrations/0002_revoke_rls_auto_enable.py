from django.db import migrations

# Supabase's "enable RLS automatically" project option installs
# public.rls_auto_enable(), a SECURITY DEFINER event-trigger function used by
# the `ensure_rls` event trigger. Because it sits in the exposed `public`
# schema, the Data API lists it as callable by anon/authenticated
# (/rest/v1/rpc/rls_auto_enable). It cannot do anything outside an event
# trigger, but nobody needs to call it, so take the grant away. The event
# trigger keeps firing: trigger invocation does not check EXECUTE.

REVOKE_SQL = """
DO $$
BEGIN
  IF to_regprocedure('public.rls_auto_enable()') IS NOT NULL THEN
    REVOKE EXECUTE ON FUNCTION public.rls_auto_enable() FROM PUBLIC, anon, authenticated;
  END IF;
END $$;
"""


def revoke(apps, schema_editor):
    if schema_editor.connection.vendor != "postgresql":
        return
    # The anon/authenticated roles only exist on Supabase; skip plain Postgres.
    with schema_editor.connection.cursor() as cursor:
        cursor.execute("SELECT count(*) FROM pg_roles WHERE rolname IN ('anon', 'authenticated')")
        if cursor.fetchone()[0] != 2:
            return
    schema_editor.execute(REVOKE_SQL, params=None)


class Migration(migrations.Migration):
    dependencies = [
        ("core", "0001_enable_rls"),
    ]

    operations = [
        migrations.RunPython(revoke, migrations.RunPython.noop),
    ]
