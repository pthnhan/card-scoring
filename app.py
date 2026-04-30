from flask import Flask, jsonify, request, render_template, session, redirect
import os
import time
import secrets

app = Flask(__name__)
app.secret_key = os.environ.get("FLASK_SECRET_KEY", "dev-secret")

# ── In-memory games (multi-room) ──────────────────────────────────────────────
GAME_TTL_SECONDS = 6 * 60 * 60  # 6 hours
games = {}  # code -> {"state": {...}, "last_access": float}
VALID_ADMIN_MODES = {"none", "fixed", "rotating", "manual"}
MIN_PLAYERS = 2
MAX_PLAYERS = 10
MAX_PLAYER_NAME_LENGTH = 40


def _new_game_state():
    return {
        "players": [],          # list of {"name": str, "initial": int}
        "admin_mode": "none",   # "none" | "fixed" | "rotating" | "manual"
        "admin_config": {},     # {"fixed_index": int} | {"every": int, "start": int}
        "rounds": [],           # list of {"scores": {name: delta}, "admin": str|None}
        "started": False,
    }


def _cleanup_expired_games():
    now = time.time()
    expired = [code for code, g in games.items() if now - g["last_access"] > GAME_TTL_SECONDS]
    for code in expired:
        games.pop(code, None)


def _generate_code(length: int = 6) -> str:
    alphabet = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"
    return "".join(secrets.choice(alphabet) for _ in range(length))


def _touch_game(code: str):
    if code in games:
        games[code]["last_access"] = time.time()


def _get_game_from_session():
    _cleanup_expired_games()
    code = session.get("game_code")
    if not code:
        return None, None
    game = games.get(code)
    if not game:
        session.pop("game_code", None)
        return None, None
    _touch_game(code)
    return code, game["state"]


def _json_body():
    data = request.get_json(silent=True) or {}
    return data if isinstance(data, dict) else {}


def get_totals(game_state):
    players = game_state["players"]
    totals = {p["name"]: p["initial"] for p in players}
    for rnd in game_state["rounds"]:
        for name, delta in rnd["scores"].items():
            totals[name] = totals.get(name, 0) + delta
    return totals


def get_admin_for_round(game_state, round_index: int) -> str | None:
    """Return the admin player name for a given round index (0-based)."""
    mode = game_state["admin_mode"]
    players = game_state["players"]
    cfg = game_state["admin_config"]

    if mode == "none":
        return None
    if mode == "fixed":
        idx = cfg.get("fixed_index", 0)
        if idx < 0 or idx >= len(players):
            return None
        return players[idx]["name"]
    if mode == "rotating":
        every = cfg.get("every", 1)
        start = cfg.get("start", 0)
        if every < 1 or start < 0 or start >= len(players):
            return None
        idx = (start + round_index // every) % len(players)
        return players[idx]["name"]
    if mode == "manual":
        # manual admins are stored per-round; return None here (caller provides)
        return None
    return None


# ── Routes ────────────────────────────────────────────────────────────────────
@app.route("/")
def index():
    return redirect("/setup")


@app.route("/setup")
def setup():
    return render_template("setup.html")


@app.route("/game")
def game():
    return render_template("game.html")


@app.route("/api/start", methods=["POST"])
def start_game():
    _cleanup_expired_games()
    data = _json_body()
    players = data.get("players", [])          # [{"name": str, "initial": int}]
    admin_mode = data.get("admin_mode", "none")
    admin_config = data.get("admin_config", {})

    validation_error = _validate_start_payload(players, admin_mode, admin_config)
    if validation_error:
        return jsonify({"ok": False, "error": validation_error}), 400

    # Create new game code
    code = _generate_code()
    while code in games:
        code = _generate_code()

    game_state = _new_game_state()
    game_state["players"] = players
    game_state["admin_mode"] = admin_mode
    game_state["admin_config"] = admin_config
    game_state["rounds"] = []
    game_state["started"] = True

    games[code] = {"state": game_state, "last_access": time.time()}
    session["game_code"] = code

    return jsonify({"ok": True, "state": _state_response(game_state, code)})


@app.route("/api/join", methods=["POST"])
def join_game():
    _cleanup_expired_games()
    data = _json_body()
    code = (data.get("code") or "").strip().upper()
    if not code:
        return jsonify({"ok": False, "error": "Vui lòng nhập mã ván"}), 400
    game = games.get(code)
    if not game:
        return jsonify({"ok": False, "error": "Mã ván không tồn tại hoặc đã hết hạn"}), 404
    session["game_code"] = code
    _touch_game(code)
    return jsonify({"ok": True, "state": _state_response(game["state"], code)})


@app.route("/api/state", methods=["GET"])
def get_state():
    code, game_state = _get_game_from_session()
    if not game_state:
        return jsonify({"started": False})
    return jsonify(_state_response(game_state, code))


@app.route("/api/round", methods=["POST"])
def submit_round():
    code, game_state = _get_game_from_session()
    if not game_state or not game_state["started"]:
        return jsonify({"ok": False, "error": "Game not started"}), 400

    data = _json_body()
    scores = data.get("scores", {})   # {player_name: delta_int}
    manual_admin = data.get("admin", None)  # only used in manual mode

    valid_names = {p["name"] for p in game_state["players"]}
    if not isinstance(scores, dict) or set(scores.keys()) != valid_names:
        return jsonify({"ok": False, "error": "Danh sách người chơi không hợp lệ"}), 400

    # Validate types
    for name, val in scores.items():
        if not _is_int(val):
            return jsonify({"ok": False, "error": f"Điểm phải là số nguyên cho {name}"}), 400

    mode = game_state["admin_mode"]

    # Determine admin for this round
    round_index = len(game_state["rounds"])
    admin = None
    if mode != "none":
        if manual_admin is not None:
            if manual_admin not in valid_names:
                return jsonify({"ok": False, "error": "Admin không hợp lệ"}), 400
            admin = manual_admin
        else:
            admin = get_admin_for_round(game_state, round_index)
        if admin is None:
            return jsonify({"ok": False, "error": "Admin không hợp lệ"}), 400

    # Zero-sum check (no-admin mode)
    if mode == "none":
        total = sum(scores.values())
        if total != 0:
            return jsonify({"ok": False, "error": f"Tổng điểm phải = 0 (hiện tại = {total:+d})"}), 400

    game_state["rounds"].append({"scores": scores, "admin": admin})
    _touch_game(code)
    return jsonify({"ok": True, "state": _state_response(game_state, code)})


@app.route("/api/undo", methods=["POST"])
def undo_round():
    code, game_state = _get_game_from_session()
    if not game_state:
        return jsonify({"ok": False, "error": "Game not started"}), 400
    if game_state["rounds"]:
        game_state["rounds"].pop()
        _touch_game(code)
        return jsonify({"ok": True, "state": _state_response(game_state, code)})
    return jsonify({"ok": False, "error": "Không có lượt nào để hoàn tác"}), 400


@app.route("/api/reset", methods=["POST"])
def reset_game():
    code = session.get("game_code")
    if code:
        games.pop(code, None)
    session.pop("game_code", None)
    return jsonify({"ok": True})


# ── Helpers ───────────────────────────────────────────────────────────────────
def _state_response(game_state, code: str):
    players = game_state["players"]
    totals = get_totals(game_state)
    round_index = len(game_state["rounds"])

    # Compute next admin
    mode = game_state["admin_mode"]
    if mode == "manual":
        next_admin = None  # Will be chosen by user each round
    else:
        next_admin = get_admin_for_round(game_state, round_index)

    return {
        "started": game_state["started"],
        "game_code": code,
        "players": [p["name"] for p in players],
        "admin_mode": game_state["admin_mode"],
        "admin_config": game_state["admin_config"],
        "rounds": game_state["rounds"],
        "totals": totals,
        "next_admin": next_admin,
        "round_number": round_index + 1,
    }


def _is_int(value) -> bool:
    return isinstance(value, int) and not isinstance(value, bool)


def _validate_start_payload(players, admin_mode, admin_config) -> str | None:
    if not isinstance(players, list):
        return "Danh sách người chơi không hợp lệ"
    if len(players) < MIN_PLAYERS or len(players) > MAX_PLAYERS:
        return f"Số người chơi phải từ {MIN_PLAYERS} đến {MAX_PLAYERS}"
    if admin_mode not in VALID_ADMIN_MODES:
        return "Chế độ Admin không hợp lệ"
    if not isinstance(admin_config, dict):
        return "Cấu hình Admin không hợp lệ"

    names = []
    for idx, player in enumerate(players, start=1):
        if not isinstance(player, dict):
            return "Danh sách người chơi không hợp lệ"
        name = player.get("name")
        initial = player.get("initial")
        if not isinstance(name, str):
            return f"Tên người chơi {idx} không hợp lệ"
        name = name.strip()
        if not name:
            return f"Tên người chơi {idx} không được để trống"
        if len(name) > MAX_PLAYER_NAME_LENGTH:
            return f"Tên người chơi {idx} quá dài"
        if not _is_int(initial):
            return f"Điểm ban đầu phải là số nguyên cho {name}"
        names.append(name)
        player["name"] = name

    if len(set(names)) != len(names):
        return "Tên người chơi không được trùng nhau"

    if admin_mode == "fixed":
        fixed_index = admin_config.get("fixed_index")
        if not _is_int(fixed_index) or fixed_index < 0 or fixed_index >= len(players):
            return "Admin mặc định không hợp lệ"
    elif admin_mode == "rotating":
        every = admin_config.get("every")
        start = admin_config.get("start")
        if not _is_int(every) or every < 1 or every > 20:
            return "Số lượt đổi Admin không hợp lệ"
        if not _is_int(start) or start < 0 or start >= len(players):
            return "Admin đầu tiên không hợp lệ"

    return None


if __name__ == "__main__":
    app.run(debug=True)
