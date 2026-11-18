r"""Run the University Command Center website locally for manual testing.

Run from the repository folder. Uses the disposable local test cluster, separate
local-only roles and a separate database, never the automated test databases.

  python tools/run_local_web.py setup   once: create roles, database and private secrets
  python tools/run_local_web.py ai      add, change or remove a Gemini/Grok API key and model
  python tools/run_local_web.py check   test each saved key and model, and time one tiny answer
  python tools/run_local_web.py         each time: migrate + provision, then start the site

Secrets are random, stored only in a private file OUTSIDE the repository
(%LOCALAPPDATA%\UCC on Windows, ~/.local/share/ucc elsewhere, or UCC_LOCAL_HOME), and never
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
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent


def private_folder():
    """Where the secrets file lives: never inside the repository."""
    if os.environ.get("UCC_LOCAL_HOME"):
        return Path(os.environ["UCC_LOCAL_HOME"])
    if os.name == "nt" and os.environ.get("LOCALAPPDATA"):
        return Path(os.environ["LOCALAPPDATA"]) / "UCC"
    return Path.home() / ".local" / "share" / "ucc"


SECRETS = private_folder() / "local-web-secrets.json"
# The repository: this file's parent folder when it is run from tools/, else the current folder.
REPO = Path(os.environ.get("UCC_REPO") or (HERE.parent if (HERE.parent / "server" / "manage.py").exists()
                                             else Path.cwd()))
if SECRETS.resolve().is_relative_to(REPO.resolve()):
    raise SystemExit("Refusing to keep secrets inside the repository. Set UCC_LOCAL_HOME to a private folder.")
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
    SECRETS.parent.mkdir(parents=True, exist_ok=True)
    SECRETS.write_text(json.dumps(data), encoding="utf-8")
    print("Local roles, database and private secrets created. Nothing secret was printed.")


def load_secrets():
    if not SECRETS.exists():
        raise SystemExit("Run setup first:  python tools/run_local_web.py setup")
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


def _call(host, method, path, headers, body=None):
    """One HTTPS request. Returns (status, parsed JSON or {}, seconds). Never prints the key."""
    import http.client
    import ssl
    connection = http.client.HTTPSConnection(host, 443, timeout=60, context=ssl.create_default_context())
    started = time.monotonic()
    try:
        connection.request(method, path, body=json.dumps(body) if body else None, headers=headers)
        response = connection.getresponse()
        data = response.read(2_000_000)
    except OSError as error:
        raise SystemExit(f"Could not reach {host} ({type(error).__name__}). Check the internet connection.")
    finally:
        connection.close()
    seconds = time.monotonic() - started
    try:
        return response.status, json.loads(data.decode("utf-8")), seconds
    except ValueError:
        return response.status, {}, seconds


def _error_code(data):
    error = data.get("error") if isinstance(data, dict) else None
    if isinstance(error, dict):
        return str(error.get("status") or error.get("code") or "?")
    return str(error or "?")[:40]


def _speed(seconds):
    verdict = "fast" if seconds <= 15 else "slow (over 15 seconds)"
    return f"answered in {seconds:.1f} seconds: {verdict}"


def check_gemini(key, model):
    headers = {"x-goog-api-key": key, "Content-Type": "application/json"}
    host = "generativelanguage.googleapis.com"
    status, data, _ = _call(host, "GET", "/v1beta/models?pageSize=1000", headers)
    print(f"1. Listing models with your key: HTTP {status}" + ("" if status == 200 else f" ({_error_code(data)})"))
    if status != 200:
        print("   The key itself was refused: create a new key at https://aistudio.google.com/apikey and save it")
        print("   again with:  python tools/run_local_web.py ai")
        return
    usable = sorted(item["name"].split("/", 1)[-1] for item in data.get("models", [])
                    if "generateContent" in item.get("supportedGenerationMethods", []))
    flash = [name for name in usable if "flash" in name]
    print(f"   Your key can use {len(usable)} models. Flash models: " + (", ".join(flash) or "none"))
    print(f"   Your saved model '{model}' is " + ("in the list." if model in usable else "NOT in the list."))
    if model not in usable:
        print("   Fix: run  python tools/run_local_web.py ai  and save one of the Flash names above")
        print("   (prefer one without 'preview' or 'exp' in its name).")
        return
    # The same thinking setting the website sends (see server/student_web/ai_providers.py).
    config = {"maxOutputTokens": 200}
    level = os.environ.get("UCC_GEMINI_THINKING", "low")
    if model.startswith("gemini-3") and level in ("minimal", "low", "medium", "high"):
        config["thinkingConfig"] = {"thinkingLevel": level}
    status, data, seconds = _call(host, "POST", f"/v1beta/models/{model}:generateContent", headers,
                                  {"contents": [{"role": "user", "parts": [{"text": "Reply with the single word OK."}]}],
                                   "generationConfig": config})
    print(f"2. Tiny test request to {model}: HTTP {status}" + ("" if status == 200 else f" ({_error_code(data)})"))
    if status == 200:
        print(f"   Gemini works: {_speed(seconds)}.")
    elif status == 400 and "thinkingConfig" in config:
        print("   Google refused the thinking setting for this model. Start the website with")
        print('   $env:UCC_GEMINI_THINKING="default"  in the same PowerShell window first, and tell Claude.')
    elif status == 429:
        print("   Quota or rate limit reached (RESOURCE_EXHAUSTED). Wait a while, or check your limits in")
        print("   Google AI Studio. Smaller files use less of the free quota.")
    else:
        print("   Google refused the request. Share the line above (it contains no key).")


def check_grok(key, model):
    headers = {"Authorization": f"Bearer {key}", "Content-Type": "application/json"}
    host = "api.x.ai"
    status, data, _ = _call(host, "GET", "/v1/models", headers)
    print(f"1. Listing models with your key: HTTP {status}" + ("" if status == 200 else f" ({_error_code(data)})"))
    if status != 200:
        print("   The key itself was refused: create a new key at https://console.x.ai and save it again with:")
        print("   python tools/run_local_web.py ai")
        return
    usable = sorted(item.get("id", "") for item in data.get("data", []) if isinstance(item, dict))
    print(f"   Your key can use: " + (", ".join(usable) or "none"))
    print(f"   Your saved model '{model}' is " + ("in the list." if model in usable else "NOT in the list."))
    if model not in usable:
        print("   Fix: run  python tools/run_local_web.py ai  and save one of the names above.")
        return
    status, data, seconds = _call(host, "POST", "/v1/chat/completions", headers,
                                  {"model": model, "max_tokens": 50,
                                   "messages": [{"role": "user", "content": "Reply with the single word OK."}]})
    print(f"2. Tiny test request to {model}: HTTP {status}" + ("" if status == 200 else f" ({_error_code(data)})"))
    if status == 200:
        print(f"   Grok works: {_speed(seconds)}.")
    elif status == 429:
        print("   Rate limit or credits used up. Check your account at https://console.x.ai")
    else:
        print("   xAI refused the request. Share the line above (it contains no key).")


def check():
    """Test each saved AI key and model and time one tiny answer. Prints only HTTP status codes,
    short error codes, model names and timings; never the key."""
    saved = load_secrets().get("ai", {})
    if not saved:
        raise SystemExit("No AI key saved yet. Run:  python tools/run_local_web.py ai")
    for provider, test in (("gemini", check_gemini), ("grok", check_grok)):
        if provider in saved:
            print(f"\n== {AI_NAMES[provider]} ==")
            test(saved[provider]["key"], saved[provider]["model"])


def base_environment(data):
    env = {key: value for key, value in os.environ.items()
           if not key.startswith(("PG", "UCC_", "DJANGO_"))}
    env.update(PGHOST=HOST, PGPORT=PORT, PGDATABASE=DATABASE,
               DJANGO_SECRET_KEY=data["django_secret_key"],
               UCC_CONTEXT_SIGNING_KEY=data["context_signing_key"],
               UCC_RUNTIME_ROLE=ROLES["runtime"], UCC_AUTH_ROLE=ROLES["auth"])
    # Windows app-control policies can block the DLL inside psycopg-binary. PostgreSQL's own
    # client library (already trusted, it runs the database) works through psycopg's pure
    # Python implementation.
    postgres_bin = Path(os.environ.get("ProgramFiles", r"C:\Program Files")) / "PostgreSQL" / "17" / "bin"
    if os.name == "nt" and (postgres_bin / "libpq.dll").exists():
        env["PATH"] = str(postgres_bin) + os.pathsep + env.get("PATH", "")
        env["PSYCOPG_IMPL"] = "python"
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
    # Optional: Gemini thinking level (minimal/low/medium/high, or "default" to send none).
    if os.environ.get("UCC_GEMINI_THINKING"):
        web["UCC_GEMINI_THINKING"] = os.environ["UCC_GEMINI_THINKING"]
    ready = [AI_NAMES[p] for p in data.get("ai", {})]
    print("\nAI services set up:", ", ".join(ready) or "none (add one with: python tools/run_local_web.py ai)")
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
    elif command == ["check"]:
        check()
    elif not command:
        run()
    else:
        raise SystemExit("Use: python tools/run_local_web.py [setup | ai | check]")
