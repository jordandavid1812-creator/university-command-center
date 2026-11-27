"""A result always has its request's tool: the same-owner key to the request also includes the tool.

Added after stage 1 merged (PR #67 review); 0011 and 0012 are unchanged.
"""

from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("academics", "0012_study_ai_security"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.AddConstraint(
            model_name="studyairequest",
            constraint=models.UniqueConstraint(
                fields=("id", "owner", "tool"), name="airequest_id_owner_tool_unique"
            ),
        ),
        migrations.RunSQL(
            sql="""
                ALTER TABLE academics_studyairesult DROP CONSTRAINT airesult_request_same_owner;
                ALTER TABLE academics_studyairesult
                ADD CONSTRAINT airesult_request_same_owner
                FOREIGN KEY (request_id, owner_id, tool)
                REFERENCES academics_studyairequest (id, owner_id, tool)
                ON DELETE NO ACTION ON UPDATE NO ACTION NOT DEFERRABLE;
            """,
            reverse_sql="""
                ALTER TABLE academics_studyairesult DROP CONSTRAINT airesult_request_same_owner;
                ALTER TABLE academics_studyairesult
                ADD CONSTRAINT airesult_request_same_owner
                FOREIGN KEY (request_id, owner_id)
                REFERENCES academics_studyairequest (id, owner_id)
                ON DELETE NO ACTION ON UPDATE NO ACTION NOT DEFERRABLE;
            """,
        ),
    ]
