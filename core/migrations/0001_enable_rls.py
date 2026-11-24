from django.db import migrations

# Supabase exposes the `public` schema through its Data API (PostgREST).
# Bestory never uses that API, so enable Row Level Security (with no
# policies) on every existing table: the anon/authenticated API roles then
# see nothing, while Django (connecting as the table owner) is unaffected.
#
# This only covers tables that exist when it runs. After adding a new model,
# enable RLS for its table too (see README, "Supabase security").

ENABLE_RLS_SQL = """
DO $$
DECLARE r record;
BEGIN
  FOR r IN SELECT tablename FROM pg_tables WHERE schemaname = 'public' LOOP
    EXECUTE format('ALTER TABLE public.%I ENABLE ROW LEVEL SECURITY', r.tablename);
  END LOOP;
END $$;
"""


def enable_rls(apps, schema_editor):
    if schema_editor.connection.vendor != "postgresql":
        return  # SQLite etc.: nothing to do
    # params=None: the SQL contains '%I' (format()), which must not be
    # treated as a DB-API placeholder.
    schema_editor.execute(ENABLE_RLS_SQL, params=None)


class Migration(migrations.Migration):
    dependencies = [
        ("accounts", "0001_initial"),
        ("search", "0001_initial"),
        ("auth", "0012_alter_user_first_name_max_length"),
        ("admin", "0003_logentry_add_action_flag_choices"),
        ("contenttypes", "0002_remove_content_type_name"),
        ("sessions", "0001_initial"),
    ]

    operations = [
        migrations.RunPython(enable_rls, migrations.RunPython.noop),
    ]
