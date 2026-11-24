import os
import sys
import time

from django.apps import AppConfig

_migration_checked = False


class InvestorsConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'investors'

    def ready(self):
        from django.core.signals import request_started

        request_started.connect(apply_migrations_once, dispatch_uid="investors.apply_migrations_once")


def apply_migrations_once(sender, **kwargs):
    """Login reads Profile.employee_id. Apply any unrun migrations before that query."""
    global _migration_checked
    if _migration_checked:
        return
    _migration_checked = True
    if any(cmd in sys.argv for cmd in ("makemigrations", "migrate", "collectstatic", "test", "shell")):
        return
    ensure_pending_migrations()


def ensure_pending_migrations():
    """Apply unrun migrations once. Gunicorn workers start together, so take a lock."""
    from pathlib import Path

    from django.conf import settings
    from django.core.management import call_command
    from django.db import connection
    from django.db.migrations.executor import MigrationExecutor

    lock_path = Path(settings.BASE_DIR) / ".migrate.lock"
    deadline = time.time() + 90
    while True:
        try:
            fd = os.open(str(lock_path), os.O_CREAT | os.O_EXCL | os.O_WRONLY)
            break
        except FileExistsError:
            if time.time() > deadline:
                try:
                    if time.time() - lock_path.stat().st_mtime > 90:
                        lock_path.unlink()
                        continue
                except OSError:
                    return
                return
            time.sleep(0.25)

    try:
        executor = MigrationExecutor(connection)
        plan = executor.migration_plan(executor.loader.graph.leaf_nodes())
        if plan:
            call_command("migrate", interactive=False, verbosity=1)
    finally:
        os.close(fd)
        try:
            lock_path.unlink()
        except OSError:
            pass
