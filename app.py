from flask import Flask, jsonify, request, render_template, session, redirect
import os
import time
import secrets

app = Flask(__name__)
app.secret_key = os.environ.get("FLASK_SECRET_KEY", "dev-secret")

# ── In-memory games (multi-room) ──────────────────────────────────────────────
GAME_TTL_SECONDS = 6 * 60 * 60  # 6 hours
games = {}  # code -> {"state": {...}, "last_access": float}


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
        return players[idx]["name"]
    if mode == "rotating":
        every = cfg.get("every", 1)
        start = cfg.get("start", 0)
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
    data = request.get_json()
    players = data.get("players", [])          # [{"name": str, "initial": int}]
    admin_mode = data.get("admin_mode", "none")
    admin_config = data.get("admin_config", {})

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
    data = request.get_json()
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

    data = request.get_json()
    scores = data.get("scores", {})   # {player_name: delta_int}
    manual_admin = data.get("admin", None)  # only used in manual mode

    valid_names = {p["name"] for p in game_state["players"]}
    if not scores or not set(scores.keys()).issubset(valid_names):
        return jsonify({"ok": False, "error": "Danh sách người chơi không hợp lệ"}), 400

    # Validate types
    for name, val in scores.items():
        if not isinstance(val, int):
            return jsonify({"ok": False, "error": f"Điểm phải là số nguyên cho {name}"}), 400

    mode = game_state["admin_mode"]

    # Determine admin for this round
    round_index = len(game_state["rounds"])
    if mode == "manual":
        admin = manual_admin
    else:
        admin = get_admin_for_round(game_state, round_index)

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


if __name__ == "__main__":
    app.run(debug=True)
