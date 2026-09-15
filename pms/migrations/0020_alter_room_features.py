import ast
import json
from django.db import migrations, models


def fix_blank_features(apps, schema_editor):
    """
    Normalize every Room.features value into valid JSON text before
    the column type changes to JSONField. Handles:
      - NULL / empty string          -> []
      - Python list repr with single quotes e.g. "['WiFi', 'AC']" -> proper JSON
      - Comma-separated plain text e.g. "WiFi,AC"                 -> proper JSON
      - Already-valid JSON text                                   -> left as-is
    """
    connection = schema_editor.connection
    with connection.cursor() as cursor:
        cursor.execute("SELECT id, features FROM pms_room")
        rows = cursor.fetchall()

        for room_id, raw in rows:
            fixed = None

            if raw is None or raw.strip() == "":
                fixed = []
            else:
                # Try parsing as valid JSON first
                try:
                    parsed = json.loads(raw)
                    if isinstance(parsed, list):
                        fixed = parsed
                except (json.JSONDecodeError, TypeError):
                    pass

                # Try parsing as a Python literal, e.g. "['WiFi', 'AC']"
                if fixed is None:
                    try:
                        parsed = ast.literal_eval(raw)
                        if isinstance(parsed, list):
                            fixed = [str(x) for x in parsed]
                    except (ValueError, SyntaxError):
                        pass

                # Fall back to comma-separated plain text, e.g. "WiFi,AC"
                if fixed is None:
                    fixed = [f.strip() for f in raw.split(",") if f.strip()]

            cursor.execute(
                "UPDATE pms_room SET features = %s WHERE id = %s",
                [json.dumps(fixed), room_id],
            )


class Migration(migrations.Migration):

    dependencies = [
        ('pms', '0019_room_features'),
    ]

    operations = [
        migrations.RunPython(fix_blank_features, migrations.RunPython.noop),
        migrations.AlterField(
            model_name='room',
            name='features',
            field=models.JSONField(blank=True, default=list),
        ),
    ]