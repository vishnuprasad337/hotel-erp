import uuid
from django.db import migrations

def gen_uuid(apps, schema_editor):
    SubscriptionPlan = apps.get_model('accounts', 'SubscriptionPlan')
    db_alias = schema_editor.connection.alias
    for plan in SubscriptionPlan.objects.using(db_alias).all():
        plan.uuid = uuid.uuid4()
        plan.save(update_fields=['uuid'])

class Migration(migrations.Migration):
    dependencies = [
        ('accounts', '0023_subscriptionplan_uuid'),  # match whatever number Step 1 actually created
    ]
    operations = [
        migrations.RunPython(gen_uuid, migrations.RunPython.noop),
    ]