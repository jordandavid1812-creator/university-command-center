from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [("academics", "0002_owner_relationships")]
    operations = [
        migrations.AddField("semester", "record_version", models.PositiveBigIntegerField(default=1)),
        migrations.AddConstraint("semester", models.CheckConstraint(
            condition=models.Q(record_version__gte=1), name="semester_version_positive")),
    ]
