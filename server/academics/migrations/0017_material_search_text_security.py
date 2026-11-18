"""Search text: same-owner material link and forced row-level security (like stored files)."""
from django.db import migrations


class Migration(migrations.Migration):
    dependencies = [("academics", "0016_material_search_text")]
    operations = [
        migrations.RunSQL(
            sql="""
                ALTER TABLE academics_materialtext
                ADD CONSTRAINT materialtext_material_same_owner
                FOREIGN KEY (material_id, owner_id)
                REFERENCES academics_studymaterial (id, owner_id)
                ON DELETE NO ACTION ON UPDATE NO ACTION NOT DEFERRABLE;

                ALTER TABLE academics_materialtext ENABLE ROW LEVEL SECURITY;
                ALTER TABLE academics_materialtext FORCE ROW LEVEL SECURITY;
                CREATE POLICY student_owner ON academics_materialtext
                FOR ALL TO PUBLIC
                USING (owner_id = (SELECT ucc_security.current_student()))
                WITH CHECK (owner_id = (SELECT ucc_security.current_student()));
            """,
            reverse_sql="""
                DROP POLICY student_owner ON academics_materialtext;
                ALTER TABLE academics_materialtext NO FORCE ROW LEVEL SECURITY;
                ALTER TABLE academics_materialtext DISABLE ROW LEVEL SECURITY;
                ALTER TABLE academics_materialtext DROP CONSTRAINT materialtext_material_same_owner;
            """,
        ),
    ]
