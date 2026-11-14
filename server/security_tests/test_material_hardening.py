"""Review follow-ups: real concurrent quota, startup grant checks, TRUNCATE and file integrity."""
import time
from threading import Event, Thread, current_thread
from unittest.mock import patch
from django.core.exceptions import ImproperlyConfigured
from django.db import connections, DatabaseError, transaction
from psycopg import sql
from academics import services
from academics.ownership import require_runtime_role
from academics.services import MaterialRecords, StorageQuotaExceeded, StoredFileDamaged, materials
from .base import StudentSecurityCase

CONTENT = b"Synthetic notes"


class MaterialHardeningTests(StudentSecurityCase):
    def upload(self, title="Synthetic notes"):
        return materials.create_with_file(self.a, title=title, course_id=self.course_a.pk,
                                          original_filename="notes.txt", file_type="txt", content=CONTENT)

    def migrator(self, statement):
        role = connections["runtime"].settings_dict["USER"]
        with connections["default"].cursor() as cursor:
            cursor.execute(sql.SQL(statement).format(role=sql.Identifier(role)))

    def wait_for_advisory_locks(self, granted, waiting):
        deadline = time.monotonic() + 10
        while time.monotonic() < deadline:
            with connections["default"].cursor() as cursor:
                cursor.execute("""SELECT count(*) FILTER (WHERE granted), count(*) FILTER (WHERE NOT granted)
                                  FROM pg_locks WHERE locktype = 'advisory' AND database =
                                  (SELECT oid FROM pg_database WHERE datname = current_database())""")
                if cursor.fetchone() == (granted, waiting):
                    return
            time.sleep(0.05)
        self.fail(f"advisory locks never reached granted={granted}, waiting={waiting}")

    def test_simultaneous_uploads_cannot_both_pass_the_quota(self):
        """Two real connections: the second upload must wait for the lock, then see the first file."""
        original_create, release, results = MaterialRecords.create, Event(), {}

        def held_create(records, identity, **fields):
            if current_thread().name == "first-upload":
                release.wait(10)  # holds the lock, quota already checked, nothing committed yet
            return original_create(records, identity, **fields)

        def upload_in_thread(name):
            try:
                self.upload(name)
                results[name] = "saved"
            except StorageQuotaExceeded:
                results[name] = "full"
            finally:
                connections.close_all()

        with patch.object(services, "MAX_FILES_PER_STUDENT", 1), patch.object(MaterialRecords, "create", held_create):
            first = Thread(target=upload_in_thread, args=("first-upload",), name="first-upload", daemon=True)
            first.start()
            self.wait_for_advisory_locks(granted=1, waiting=0)
            second = Thread(target=upload_in_thread, args=("second-upload",), name="second-upload", daemon=True)
            second.start()
            self.wait_for_advisory_locks(granted=1, waiting=1)
            release.set()
            first.join(15)
            second.join(15)
        self.assertEqual(results, {"first-upload": "saved", "second-upload": "full"})
        self.assertEqual(len(materials.list(self.a)), 1)

    def test_runtime_cannot_truncate_material_tables(self):
        for table in ("academics_studymaterial", "academics_materialfile"):
            with self.assertRaises(DatabaseError), transaction.atomic(using="runtime"):
                with connections["runtime"].cursor() as cursor:
                    cursor.execute(f"TRUNCATE {table} CASCADE")

    def test_startup_check_rejects_missing_rls_on_stored_files(self):
        self.migrator("ALTER TABLE academics_materialfile NO FORCE ROW LEVEL SECURITY")
        try:
            with self.assertRaises(ImproperlyConfigured):
                require_runtime_role(connections["runtime"])
        finally:
            self.migrator("ALTER TABLE academics_materialfile FORCE ROW LEVEL SECURITY")
        require_runtime_role(connections["runtime"])

    def test_startup_check_rejects_stray_update_or_truncate_grants(self):
        for grant, revoke in (
            ("GRANT UPDATE (content) ON academics_materialfile TO {role}",
             "REVOKE UPDATE (content) ON academics_materialfile FROM {role}"),
            ("GRANT TRUNCATE ON academics_studymaterial TO {role}",
             "REVOKE TRUNCATE ON academics_studymaterial FROM {role}"),
        ):
            self.migrator(grant)
            try:
                with self.assertRaises(ImproperlyConfigured):
                    require_runtime_role(connections["runtime"])
            finally:
                self.migrator(revoke)
        require_runtime_role(connections["runtime"])

    def test_quota_counts_the_stored_bytes(self):
        with patch.object(services, "MAX_STORED_BYTES_PER_STUDENT", len(CONTENT) * 2):
            self.upload()
            self.upload()
            with self.assertRaises(StorageQuotaExceeded):
                self.upload()

    def test_damaged_file_is_refused_with_its_own_error(self):
        material = self.upload()

        with patch.object(services, "fingerprint", return_value="0" * 64):
            with self.assertRaises(StoredFileDamaged):
                materials.read_file(self.a, material.pk)
