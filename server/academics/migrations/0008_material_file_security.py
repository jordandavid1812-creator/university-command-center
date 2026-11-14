"""Material files: same-owner material link and forced row-level security."""
from django.db import migrations


class Migration(migrations.Migration):
    dependencies = [("academics", "0007_material_file")]
    operations = [
        migrations.RunSQL(
            sql="""
                ALTER TABLE academics_materialfile
                ADD CONSTRAINT materialfile_material_same_owner
                FOREIGN KEY (material_id, owner_id)
                REFERENCES academics_studymaterial (id, owner_id)
                ON DELETE NO ACTION ON UPDATE NO ACTION NOT DEFERRABLE;

                ALTER TABLE academics_materialfile ENABLE ROW LEVEL SECURITY;
                ALTER TABLE academics_materialfile FORCE ROW LEVEL SECURITY;
                CREATE POLICY student_owner ON academics_materialfile
                FOR ALL TO PUBLIC
                USING (owner_id = (SELECT ucc_security.current_student()))
                WITH CHECK (owner_id = (SELECT ucc_security.current_student()));
            """,
            reverse_sql="""
                DROP POLICY student_owner ON academics_materialfile;
                ALTER TABLE academics_materialfile NO FORCE ROW LEVEL SECURITY;
                ALTER TABLE academics_materialfile DISABLE ROW LEVEL SECURITY;
                ALTER TABLE academics_materialfile DROP CONSTRAINT materialfile_material_same_owner;
            """,
        ),
    ]
