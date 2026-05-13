from __future__ import annotations

import json
import os
import threading
import time
from functools import wraps
from typing import Any, Callable, Dict, List

from flask import (
    Flask,
    Response,
    flash,
    jsonify,
    redirect,
    render_template,
    request,
    session,
    url_for,
)

from .config_store import ConfigStore, _listify
from .docker_control import DockerController
from .immich_client import ImmichClient, ImmichError


def env_bool(name: str, default: bool = False) -> bool:
    value = os.environ.get(name)
    if value is None:
        return default
    return value.lower() in {"1", "true", "yes", "on"}


def env_int(primary: str, fallback: str, default: int) -> int:
    raw = os.environ.get(primary)
    if raw is None:
        raw = os.environ.get(fallback)
    if raw is None:
        return default
    try:
        return int(raw)
    except ValueError:
        return default


def create_app() -> Flask:
    app = Flask(__name__)
    app.secret_key = os.environ.get("SECRET_KEY", "change-me-for-production")

    settings_file = os.environ.get("SETTINGS_FILE", "/config/Settings.json")
    state_file = os.environ.get("STATE_FILE", "/data/sidecar-state.json")
    backup_dir = os.environ.get("BACKUP_DIR")
    store = ConfigStore(settings_file=settings_file, state_file=state_file, backup_dir=backup_dir)
    docker = DockerController(os.environ.get("IMMICHFRAME_CONTAINER", "immichframe"))

    app.config["STORE"] = store
    app.config["DOCKER"] = docker
    app.config["ADMIN_USERNAME"] = os.environ.get("ADMIN_USERNAME", "").strip()
    app.config["ADMIN_PASSWORD"] = os.environ.get("ADMIN_PASSWORD", "")
    app.config["AUTO_RESTART_ON_SYNC"] = env_bool("AUTO_RESTART_ON_SYNC", env_bool("ENABLE_DOCKER_RESTART", True))
    app.config["AUTO_SYNC_INTERVAL_SECONDS"] = env_int("AUTO_SYNC_INTERVAL_SECONDS", "SYNC_INTERVAL_SECONDS", 300)
    app.config["INITIAL_ALBUM_LOAD"] = env_bool("INITIAL_ALBUM_LOAD", True)

    @app.context_processor
    def inject_globals() -> Dict[str, Any]:
        return {
            "settings_file": settings_file,
            "state_file": state_file,
            "auth_enabled": bool(app.config["ADMIN_PASSWORD"]),
            "admin_username": app.config["ADMIN_USERNAME"],
            "docker_available": docker.available(),
            "docker_container": docker.container_name,
            "auto_restart_on_sync": app.config["AUTO_RESTART_ON_SYNC"],
        }

    def require_auth(func: Callable[..., Any]) -> Callable[..., Any]:
        @wraps(func)
        def wrapper(*args: Any, **kwargs: Any) -> Any:
            password = app.config["ADMIN_PASSWORD"]
            if not password:
                return func(*args, **kwargs)
            if session.get("authenticated"):
                return func(*args, **kwargs)
            return redirect(url_for("login", next=request.path))

        return wrapper

    def get_account(index: int) -> Dict[str, Any]:
        settings = store.load_settings()
        accounts = settings.get("Accounts", [])
        if index < 0 or index >= len(accounts):
            raise IndexError("Account index out of range")
        return accounts[index]

    def account_has_credentials(account: Dict[str, Any]) -> bool:
        return bool((account.get("ImmichServerUrl") or "").strip() and ((account.get("ApiKey") or "").strip() or account.get("ApiKeyFile")))

    def make_client(index: int) -> ImmichClient:
        account = get_account(index)
        api_key = account.get("ApiKey") or ""
        api_key_file = account.get("ApiKeyFile")
        if not api_key and api_key_file:
            try:
                api_key = open(str(api_key_file), "r", encoding="utf-8").read().strip()
            except OSError as exc:
                raise ImmichError(f"Could not read ApiKeyFile {api_key_file}: {exc}")
        return ImmichClient(
            base_url=str(account.get("ImmichServerUrl") or ""),
            api_key=str(api_key or ""),
            timeout=int(os.environ.get("IMMICH_TIMEOUT_SECONDS", "15")),
        )

    def refresh_album_cache(index: int, source: str = "immich") -> List[Dict[str, Any]]:
        albums = make_client(index).list_albums()
        store.cache_albums(index, albums, source=source)
        return albums

    def maybe_initial_load_album_cache(index: int) -> None:
        if not app.config["INITIAL_ALBUM_LOAD"]:
            return
        state = store.load_state()
        policy = store.account_state(state, index)
        store.save_state(state)
        if policy.get("album_cache"):
            return
        try:
            account = get_account(index)
            if not account_has_credentials(account):
                return
            refresh_album_cache(index, source="initial-page-load")
            flash("Initial album cache loaded from Immich.", "success")
        except Exception as exc:
            store.record_album_cache_error(index, str(exc))
            flash(f"Could not load initial Immich album cache: {exc}", "warning")

    def apply_policy_for_account(index: int) -> Dict[str, Any]:
        albums = refresh_album_cache(index, source="policy-apply")
        old_settings = store.load_settings()
        old_albums = _listify(old_settings.get("Accounts", [])[index].get("Albums"))
        applied, policy = store.apply_album_policy(index, albums)
        changed = old_albums != applied
        return {"ok": True, "changed": changed, "applied_count": len(applied), "policy": policy}

    @app.route("/healthz")
    def healthz() -> Dict[str, Any]:
        return {"ok": True}

    @app.route("/login", methods=["GET", "POST"])
    def login() -> Any:
        if not app.config["ADMIN_PASSWORD"]:
            return redirect(url_for("index"))
        if request.method == "POST":
            expected_user = app.config["ADMIN_USERNAME"]
            user_ok = True if not expected_user else request.form.get("username", "") == expected_user
            pass_ok = request.form.get("password") == app.config["ADMIN_PASSWORD"]
            if user_ok and pass_ok:
                session["authenticated"] = True
                flash("Logged in.", "success")
                return redirect(request.args.get("next") or url_for("index"))
            flash("Wrong username or password.", "error")
        return render_template("login.html")

    @app.route("/logout")
    def logout() -> Any:
        session.clear()
        return redirect(url_for("login"))

    @app.route("/")
    @require_auth
    def index() -> Any:
        settings = store.ensure_settings()
        state = store.load_state()
        accounts = settings.get("Accounts", [])
        policies = [store.account_state(state, idx) for idx, _ in enumerate(accounts)]
        store.save_state(state)
        return render_template("index.html", settings=settings, state=state, accounts=accounts, policies=policies)

    @app.route("/general", methods=["GET", "POST"])
    @require_auth
    def general() -> Any:
        if request.method == "POST":
            try:
                store.update_general_from_form(request.form)
                flash("General settings saved.", "success")
            except Exception as exc:
                flash(f"Could not save general settings: {exc}", "error")
            return redirect(url_for("general"))
        settings = store.load_settings()
        return render_template("general.html", general=settings.get("General", {}))

    @app.route("/accounts/new", methods=["POST"])
    @require_auth
    def new_account() -> Any:
        name = request.form.get("name") or "Frame account"
        index = store.add_account(name=name)
        flash("Account added. Fill Immich URL and API key, then save; the album cache will be loaded automatically.", "success")
        return redirect(url_for("account", index=index))

    @app.route("/accounts/<int:index>", methods=["GET", "POST"])
    @require_auth
    def account(index: int) -> Any:
        if request.method == "POST":
            try:
                store.update_account_from_form(index, request.form)
                store.update_policy_from_form(index, request.form)
                if "refresh_album_cache_after_save" in request.form:
                    try:
                        albums = refresh_album_cache(index, source="after-save")
                        flash(f"Account, album policy, and cached album list saved. Loaded {len(albums)} album(s).", "success")
                    except Exception as exc:
                        store.record_album_cache_error(index, str(exc))
                        flash(f"Account and policy saved, but album refresh failed: {exc}", "warning")
                else:
                    flash("Account and album policy saved.", "success")
            except Exception as exc:
                flash(f"Could not save account: {exc}", "error")
            return redirect(url_for("account", index=index))

        settings = store.load_settings()
        accounts = settings.get("Accounts", [])
        if index < 0 or index >= len(accounts):
            flash("Account not found.", "error")
            return redirect(url_for("index"))

        maybe_initial_load_album_cache(index)
        state = store.load_state()
        policy = store.account_state(state, index)
        store.save_state(state)
        return render_template("account.html", index=index, account=accounts[index], policy=policy)

    @app.route("/accounts/<int:index>/delete", methods=["POST"])
    @require_auth
    def delete_account(index: int) -> Any:
        try:
            store.delete_account(index)
            flash("Account deleted.", "success")
        except Exception as exc:
            flash(f"Could not delete account: {exc}", "error")
        return redirect(url_for("index"))

    @app.route("/accounts/<int:index>/apply", methods=["POST"])
    @require_auth
    def apply_account(index: int) -> Any:
        try:
            result = apply_policy_for_account(index)
            message = f"Album policy applied: {result['applied_count']} album(s). Album cache refreshed."
            should_restart = request.form.get("restart") == "on" or app.config["AUTO_RESTART_ON_SYNC"]
            if should_restart:
                restart_result = docker.restart()
                if restart_result["ok"]:
                    message += " ImmichFrame restarted."
                    flash(message, "success")
                else:
                    flash(message + f" Restart skipped/failed: {restart_result['message']}", "warning")
            else:
                flash(message, "success")
        except Exception as exc:
            store.record_error(str(exc))
            flash(f"Could not apply album policy: {exc}", "error")
        return redirect(url_for("account", index=index))

    @app.route("/sync", methods=["POST"])
    @require_auth
    def sync_all() -> Any:
        settings = store.load_settings()
        accounts = settings.get("Accounts", [])
        state = store.load_state()
        changed_any = False
        applied_total = 0
        errors: List[str] = []
        for index, _account in enumerate(accounts):
            policy = store.account_state(state, index)
            if not policy.get("auto_sync") and request.form.get("force") != "on":
                continue
            try:
                result = apply_policy_for_account(index)
                changed_any = changed_any or bool(result.get("changed"))
                applied_total += int(result.get("applied_count", 0))
            except Exception as exc:
                errors.append(f"Account {index + 1}: {exc}")
        if changed_any and app.config["AUTO_RESTART_ON_SYNC"]:
            restart_result = docker.restart()
            if not restart_result["ok"]:
                errors.append(str(restart_result["message"]))
        if errors:
            store.record_error(" | ".join(errors))
            flash("Sync completed with errors: " + " | ".join(errors), "warning")
        else:
            flash(f"Sync completed. Applied album references: {applied_total}.", "success")
        return redirect(url_for("index"))

    @app.route("/restart", methods=["POST"])
    @require_auth
    def restart() -> Any:
        result = docker.restart()
        flash(str(result["message"]), "success" if result["ok"] else "error")
        return redirect(request.referrer or url_for("index"))

    @app.route("/raw", methods=["GET", "POST"])
    @require_auth
    def raw_config() -> Any:
        if request.method == "POST":
            raw_text = request.form.get("raw", "")
            try:
                data = json.loads(raw_text)
                store.save_settings(data)
                flash("Raw Settings.json saved.", "success")
                return redirect(url_for("raw_config"))
            except Exception as exc:
                flash(f"Raw JSON not saved: {exc}", "error")
        settings = store.load_settings()
        return render_template("raw.html", raw=json.dumps(settings, indent=2, ensure_ascii=False))

    @app.route("/api/accounts/<int:index>/albums")
    @require_auth
    def api_albums(index: int) -> Any:
        try:
            albums = refresh_album_cache(index, source="manual-refresh")
            return jsonify({"ok": True, "albums": albums, "cached": True})
        except Exception as exc:
            store.record_album_cache_error(index, str(exc))
            return jsonify({"ok": False, "error": str(exc)}), 400

    @app.route("/api/accounts/<int:index>/test", methods=["POST"])
    @require_auth
    def api_test_account(index: int) -> Any:
        try:
            result = make_client(index).test_connection()
            return jsonify(result)
        except Exception as exc:
            return jsonify({"ok": False, "error": str(exc)}), 400

    @app.route("/api/settings")
    @require_auth
    def api_settings() -> Any:
        return jsonify(store.load_settings())

    @app.route("/api/accounts/<int:index>/people")
    @require_auth
    def api_people(index: int) -> Any:
        try:
            people = make_client(index).list_people()
            store.cache_people(index, people)
            return jsonify({"ok": True, "people": people})
        except Exception as exc:
            return jsonify({"ok": False, "error": str(exc)}), 400

    @app.route("/api/accounts/<int:index>/people/<person_id>/thumbnail")
    @require_auth
    def api_person_thumbnail(index: int, person_id: str) -> Any:
        if not person_id.replace("-", "").isalnum():
            return ("", 400)
        try:
            data, content_type = make_client(index).thumbnail_bytes(person_id)
            return Response(data, content_type=content_type)
        except Exception:
            return ("", 404)

    def background_sync_loop() -> None:
        interval = max(30, int(app.config["AUTO_SYNC_INTERVAL_SECONDS"]))
        time.sleep(5)
        while True:
            try:
                with app.app_context():
                    settings = store.load_settings()
                    state = store.load_state()
                    changed_any = False
                    for index, _account in enumerate(settings.get("Accounts", [])):
                        policy = store.account_state(state, index)
                        if not policy.get("auto_sync"):
                            continue
                        result = apply_policy_for_account(index)
                        changed_any = changed_any or bool(result.get("changed"))
                    if changed_any and app.config["AUTO_RESTART_ON_SYNC"]:
                        docker.restart()
            except Exception as exc:  # pragma: no cover - best-effort background worker
                try:
                    store.record_error(str(exc))
                except Exception:
                    pass
            time.sleep(interval)

    if env_bool("ENABLE_BACKGROUND_SYNC", True):
        thread = threading.Thread(target=background_sync_loop, daemon=True)
        thread.start()

    return app


app = create_app()

if __name__ == "__main__":
    port = int(os.environ.get("FLASK_PORT", os.environ.get("PORT", "8099")))
    app.run(host=os.environ.get("FLASK_HOST", "0.0.0.0"), port=port, debug=env_bool("FLASK_DEBUG", False))
