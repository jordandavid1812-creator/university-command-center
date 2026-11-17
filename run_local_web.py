"""Run the University Command Center website locally for manual testing.

Lives OUTSIDE the repository. Uses the disposable local test cluster, separate
local-only roles and a separate database, never the automated test databases.

  python run_local_web.py setup   once: create roles, database and private secrets
  python run_local_web.py ai      add, change or remove a Gemini/Grok API key and model
  python run_local_web.py         each time: migrate + provision, then start the site

Secrets are random, stored only in a private file next to this script, and never
printed. The website process gets only the restricted runtime and auth logins, plus any
AI keys you saved with the "ai" command. Migration steps never receive AI keys.
"""
import getpass
import json
import os
import re
import secrets
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
SECRETS = HERE / "local-web-secrets.json"
REPO = Path(os.environ.get("UCC_REPO", Path.cwd()))
HOST = os.environ.get("UCC_LOCAL_PGHOST", "127.0.0.1")
PORT = os.environ.get("UCC_LOCAL_PGPORT", "55432")
ADMIN = os.environ.get("UCC_LOCAL_PGADMIN", "ucc_test_admin")
DATABASE = "ucc_local_web"
ROLES = {"migrator": "ucc_local_migrator", "runtime": "ucc_local_runtime", "auth": "ucc_local_auth"}
# Same rules as server/student_web/ai_providers.py.
AI_VARIABLES = {"gemini": ("UCC_GEMINI_API_KEY", "UCC_GEMINI_MODEL"), "grok": ("UCC_GROK_API_KEY", "UCC_GROK_MODEL")}
AI_NAMES = {"gemini": "Gemini (Google)", "grok": "Grok (xAI)"}
KEY_PATTERN = r"[\x21-\x7e]{8,512}"
MODEL_PATTERN = r"[a-z0-9][a-z0-9.\-]{0,63}"


def setup():
    import psycopg
    from psycopg import sql
    if SECRETS.exists():
        raise SystemExit("Already set up. Delete local-web-secrets.json only if you also drop the local roles.")
    password = getpass.getpass(f"Password for cluster admin {ADMIN} (Enter if none): ")
    values = {name: secrets.token_urlsafe(32) for name in ROLES}
    with psycopg.connect(host=HOST, port=PORT, user=ADMIN, password=password or None,
                         dbname="postgres", autocommit=True) as connection:
        if connection.execute("SELECT 1 FROM pg_roles WHERE rolname = ANY(%s)", (list(ROLES.values()),)).fetchone():
            raise SystemExit("A local role already exists; nothing was changed.")
        if connection.execute("SELECT 1 FROM pg_database WHERE datname = %s", (DATABASE,)).fetchone():
            raise SystemExit("The local database already exists; nothing was changed.")
        with connection.transaction():
            for name, role in ROLES.items():
                connection.execute(sql.SQL(
                    "CREATE ROLE {} LOGIN NOINHERIT NOSUPERUSER NOBYPASSRLS NOCREATEDB NOCREATEROLE PASSWORD {}"
                ).format(sql.Identifier(role), sql.Literal(values[name])))
        connection.execute(sql.SQL("CREATE DATABASE {} OWNER {}").format(
            sql.Identifier(DATABASE), sql.Identifier(ROLES["migrator"])))
    data = {"passwords": values, "django_secret_key": secrets.token_urlsafe(64),
            "context_signing_key": secrets.token_hex(32)}
    SECRETS.write_text(json.dumps(data), encoding="utf-8")
    print("Local roles, database and private secrets created. Nothing secret was printed.")


def load_secrets():
    if not SECRETS.exists():
        raise SystemExit("Run setup first:  python run_local_web.py setup")
    return json.loads(SECRETS.read_text(encoding="utf-8"))


def save_secrets(data):
    temporary = SECRETS.with_suffix(".tmp")
    temporary.write_text(json.dumps(data), encoding="utf-8")
    os.replace(temporary, SECRETS)


def ai():
    """Save, replace or remove one provider's key and model. The key is typed hidden and never shown."""
    data = load_secrets()
    saved = data.setdefault("ai", {})
    print("AI services set up now:", ", ".join(AI_NAMES[p] for p in saved) or "none")
    choice = input("Which service? Type gemini or grok: ").strip().lower()
    if choice not in AI_NAMES:
        raise SystemExit("Nothing changed: type gemini or grok.")
    action = input(f"Type save to add or replace {AI_NAMES[choice]}, or remove to delete it: ").strip().lower()
    if action == "remove":
        saved.pop(choice, None)
        save_secrets(data)
        print(f"{AI_NAMES[choice]} removed from this computer. (Revoke the key on the provider's website too.)")
        return
    if action != "save":
        raise SystemExit("Nothing changed: type save or remove.")
    model = input("Model name exactly as the provider lists it (for example lowercase-with-dashes): ").strip()
    if not re.fullmatch(MODEL_PATTERN, model):
        raise SystemExit("Nothing changed: model names use only lowercase letters, digits, dots and dashes.")
    key = getpass.getpass("Paste the API key (it will not be shown), then press Enter: ").strip()
    if not re.fullmatch(KEY_PATTERN, key):
        raise SystemExit("Nothing changed: that does not look like an API key (no spaces, 8-512 characters).")
    saved[choice] = {"model": model, "key": key}
    save_secrets(data)
    print(f"{AI_NAMES[choice]} saved with model {model}. The key was not shown or printed.")


def base_environment(data):
    env = {key: value for key, value in os.environ.items()
           if not key.startswith(("PG", "UCC_", "DJANGO_"))}
    env.update(PGHOST=HOST, PGPORT=PORT, PGDATABASE=DATABASE,
               DJANGO_SECRET_KEY=data["django_secret_key"],
               UCC_CONTEXT_SIGNING_KEY=data["context_signing_key"],
               UCC_RUNTIME_ROLE=ROLES["runtime"], UCC_AUTH_ROLE=ROLES["auth"])
    return env


def manage(arguments, env):
    command = [sys.executable, str(REPO / "server" / "manage.py")] + arguments
    if subprocess.run(command, env=env, cwd=REPO).returncode != 0:
        raise SystemExit("Stopped: " + " ".join(arguments[:1]) + " failed (see the message above).")


def run():
    data = load_secrets()
    if not (REPO / "server" / "manage.py").exists():
        raise SystemExit("Run this from your university-command-center folder.")
    passwords = data["passwords"]

    # 1. Offline migration and provisioning with the MIGRATOR login only.
    migrator = base_environment(data)
    migrator.update(PGUSER=ROLES["migrator"], PGPASSWORD=passwords["migrator"])
    settings = "--settings=config.settings.auth_migration"
    manage(["migrate", "--noinput", settings], migrator)
    manage(["configure_auth_role", settings], migrator)
    manage(["configure_runtime", settings], migrator)

    # 2. The website with ONLY the restricted runtime and auth logins (and any saved AI
    #    keys). The project's starter serves on 127.0.0.1 after running Django's checks
    #    (runserver cannot start with the runtime login).
    web = base_environment(data)
    web.update(PGUSER=ROLES["runtime"], PGPASSWORD=passwords["runtime"], UCC_AUTH_PASSWORD=passwords["auth"])
    for provider, settings in data.get("ai", {}).items():
        key_variable, model_variable = AI_VARIABLES[provider]
        web.update({key_variable: settings["key"], model_variable: settings["model"]})
    ready = [AI_NAMES[p] for p in data.get("ai", {})]
    print("\nAI services set up:", ", ".join(ready) or "none (add one with: python run_local_web.py ai)")
    print("Open http://127.0.0.1:8000/  (press Ctrl+C here to stop the website)")
    print("Verification emails appear in THIS window. Use made-up details only.\n")
    try:
        subprocess.run([sys.executable, str(REPO / "tools" / "serve_local_website.py")], env=web, cwd=REPO)
    except KeyboardInterrupt:
        print("\nWebsite stopped.")


if __name__ == "__main__":
    command = sys.argv[1:]
    if command == ["setup"]:
        setup()
    elif command == ["ai"]:
        ai()
    elif not command:
        run()
    else:
        raise SystemExit("Use: python run_local_web.py [setup | ai]")
