"""Expansion only: keep the legacy column until a later reviewed contract release."""
import django.core.validators
from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [('academics', '0025_profile_grading_scale')]
    operations = [
        migrations.AlterField(
            model_name='studentprofile', name='matric_number',
            field=models.CharField(blank=True, db_default='', editable=False, max_length=32,
                validators=[django.core.validators.RegexValidator(
                    r'^[A-Za-z0-9][A-Za-z0-9/._-]{0,31}$', 'Use letters, digits and / . _ - only.')]),
        ),
    ]
