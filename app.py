from flask import Flask, request, jsonify, render_template
from flask_cors import CORS
from dotenv import load_dotenv
import sqlite3
import os
from datetime import datetime, timezone

load_dotenv()

from chess_api import get_recent_games
from analyzer import analyze_games, analyze_single_game
from scheduler import start_scheduler

app = Flask(__name__)
CORS(app)

OWNER_USERNAME = "zingpap"
FREE_MONTHLY_LIMIT = 3
# Monthly API budget in USD (£1 ≈ $1.27)
MONTHLY_BUDGET_USD = float(os.environ.get("MONTHLY_BUDGET_USD", "1.27"))
ADMIN_KEY = os.environ.get("ADMIN_KEY", "changeme")


def get_db():
    conn = sqlite3.connect("chess_teacher.db")
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    with get_db() as db:
        db.execute("""
            CREATE TABLE IF NOT EXISTS subscriptions (
                id INTEGER PRIMARY KEY,
                username TEXT NOT NULL,
                email TEXT NOT NULL,
                games_per_email INTEGER DEFAULT 1,
                mode TEXT DEFAULT 'recent',
                created_at TEXT,
                UNIQUE(username, email)
            )
        """)
        db.execute("""
            CREATE TABLE IF NOT EXISTS usage_log (
                id INTEGER PRIMARY KEY,
                username TEXT NOT NULL,
                ip TEXT,
                games_analyzed INTEGER,
                question TEXT,
                input_tokens INTEGER,
                output_tokens INTEGER,
                cost_usd REAL,
                created_at TEXT
            )
        """)


def get_month_start():
    now = datetime.now(timezone.utc)
    return now.replace(day=1, hour=0, minute=0, second=0, microsecond=0).isoformat()


def get_monthly_usage_count(username: str) -> int:
    with get_db() as db:
        row = db.execute(
            "SELECT COUNT(*) as n FROM usage_log WHERE username=? AND created_at>=?",
            (username, get_month_start()),
        ).fetchone()
    return row["n"] if row else 0


def get_monthly_spend_usd() -> float:
    with get_db() as db:
        row = db.execute(
            "SELECT SUM(cost_usd) as total FROM usage_log WHERE created_at>=?",
            (get_month_start(),),
        ).fetchone()
    return row["total"] or 0.0


def log_usage(username, ip, games_analyzed, question, input_tokens, output_tokens, cost_usd):
    with get_db() as db:
        db.execute("""
            INSERT INTO usage_log
            (username, ip, games_analyzed, question, input_tokens, output_tokens, cost_usd, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """, (username, ip, games_analyzed, question, input_tokens, output_tokens, cost_usd,
              datetime.now(timezone.utc).isoformat()))


@app.route("/")
def index():
    return render_template("index.html")


@app.route("/api/analyze", methods=["POST"])
def analyze():
    data = request.json or {}
    username = data.get("username", "").strip().lower()
    count = max(1, min(int(data.get("count", 3)), 10))
    question = data.get("question", "").strip()
    ip = request.headers.get("X-Forwarded-For", request.remote_addr)

    if not username:
        return jsonify({"error": "Username is required"}), 400

    # Monthly budget guard — applies to everyone
    monthly_spend = get_monthly_spend_usd()
    if monthly_spend >= MONTHLY_BUDGET_USD:
        return jsonify({
            "error": "Monthly analysis budget reached. Please try again next month.",
            "limit_type": "budget"
        }), 429

    # Per-user monthly cap (owner is exempt)
    if username != OWNER_USERNAME.lower():
        usage_count = get_monthly_usage_count(username)
        if usage_count >= FREE_MONTHLY_LIMIT:
            return jsonify({
                "error": f"You've used all {FREE_MONTHLY_LIMIT} free analyses for this month. Come back next month!",
                "limit_type": "user",
                "used": usage_count,
                "limit": FREE_MONTHLY_LIMIT,
            }), 429

    try:
        games = get_recent_games(username, count)
    except ValueError as e:
        return jsonify({"error": str(e)}), 404

    if not games:
        return jsonify({"error": "No games found for this username"}), 404

    feedback, input_tokens, output_tokens, cost_usd = analyze_games(games, username, question)

    log_usage(username, ip, len(games), question, input_tokens, output_tokens, cost_usd)

    return jsonify({
        "feedback": feedback,
        "games_analyzed": len(games),
        "username": username,
        "first_pgn": games[0].get("pgn", "") if games else "",
    })


@app.route("/api/subscribe", methods=["POST"])
def subscribe():
    data = request.json or {}
    username = data.get("username", "").strip()
    email = data.get("email", "").strip()
    games = max(1, min(int(data.get("games", 1)), 5))
    mode = data.get("mode", "recent")

    if not username or not email:
        return jsonify({"error": "Username and email are required"}), 400

    with get_db() as db:
        db.execute("""
            INSERT OR REPLACE INTO subscriptions
            (username, email, games_per_email, mode, created_at)
            VALUES (?, ?, ?, ?, ?)
        """, (username, email, games, mode, datetime.now(timezone.utc).isoformat()))

    return jsonify({"success": True, "message": f"Subscribed! Daily feedback will arrive at {email}"})


@app.route("/api/unsubscribe", methods=["POST"])
def unsubscribe():
    data = request.json or {}
    username = data.get("username", "").strip()
    email = data.get("email", "").strip()

    with get_db() as db:
        db.execute(
            "DELETE FROM subscriptions WHERE username=? AND email=?",
            (username, email),
        )

    return jsonify({"success": True, "message": "Unsubscribed successfully"})


@app.route("/unsubscribe")
def unsubscribe_page():
    email = request.args.get("email", "")
    username = request.args.get("username", "")
    if email and username:
        with get_db() as db:
            db.execute(
                "DELETE FROM subscriptions WHERE username=? AND email=?",
                (username, email),
            )
    return "<p style='font-family:sans-serif;text-align:center;padding:40px'>Unsubscribed. <a href='/'>Back to Chess Teacher</a></p>"


@app.route("/api/games/<username>")
def list_games(username):
    username = username.strip().lower()
    try:
        games = get_recent_games(username, 20)
    except ValueError as e:
        return jsonify({"error": str(e)}), 404

    from datetime import datetime as dt
    result_map = {
        "win": "Won", "lose": "Lost", "draw": "Drew",
        "agreed": "Drew", "repetition": "Drew", "stalemate": "Drew",
        "insufficient": "Drew", "timeout": "Timeout",
        "resigned": "Resigned", "checkmated": "Checkmated",
    }
    items = []
    for i, g in enumerate(games):
        white = g.get("white", {})
        black = g.get("black", {})
        is_white = white.get("username", "").lower() == username
        player = white if is_white else black
        opponent = black if is_white else white
        ts = g.get("end_time", 0)
        items.append({
            "index": i,
            "pgn": g.get("pgn", ""),
            "time_class": g.get("time_class", ""),
            "time_control": g.get("time_control", ""),
            "color": "White" if is_white else "Black",
            "rating": player.get("rating", "?"),
            "opponent": opponent.get("username", "?"),
            "opponent_rating": opponent.get("rating", "?"),
            "result": result_map.get(player.get("result", ""), "?"),
            "date": dt.fromtimestamp(ts).strftime("%d %b %Y") if ts else "",
        })
    return jsonify({"games": items, "username": username})


@app.route("/api/analyze-game", methods=["POST"])
def analyze_game_route():
    data = request.json or {}
    username = data.get("username", "").strip().lower()
    pgn = data.get("pgn", "").strip()
    move_number = data.get("move_number")
    fen = data.get("fen", "")
    ip = request.headers.get("X-Forwarded-For", request.remote_addr)

    if not username or not pgn:
        return jsonify({"error": "Username and PGN required"}), 400

    if get_monthly_spend_usd() >= MONTHLY_BUDGET_USD:
        return jsonify({"error": "Monthly budget reached. Try again next month."}), 429

    if username != OWNER_USERNAME.lower():
        if get_monthly_usage_count(username) >= FREE_MONTHLY_LIMIT:
            return jsonify({"error": f"{FREE_MONTHLY_LIMIT} free analyses used this month."}), 429

    feedback, tok_in, tok_out, cost = analyze_single_game(pgn, username, move_number, fen)
    log_usage(username, ip, 1, f"game_review:{move_number}", tok_in, tok_out, cost)
    return jsonify({"feedback": feedback})


@app.route("/admin")
def admin():
    key = request.args.get("key", "")
    if key != ADMIN_KEY:
        return "Not found", 404  # looks like a missing page, not a login wall

    with get_db() as db:
        logs = db.execute(
            "SELECT * FROM usage_log ORDER BY created_at DESC LIMIT 200"
        ).fetchall()
        monthly_spend = get_monthly_spend_usd()
        monthly_analyses = db.execute(
            "SELECT COUNT(*) as n FROM usage_log WHERE created_at>=?",
            (get_month_start(),)
        ).fetchone()["n"]
        top_users = db.execute("""
            SELECT username, COUNT(*) as n, SUM(cost_usd) as cost
            FROM usage_log GROUP BY username ORDER BY n DESC LIMIT 20
        """).fetchall()

    budget_pct = (monthly_spend / MONTHLY_BUDGET_USD) * 100

    rows_html = ""
    for r in logs:
        cost_p = round(r["cost_usd"] * 100 / 1.27, 2)  # USD → pence
        rows_html += f"""<tr>
            <td>{r['created_at'][:16].replace('T',' ')}</td>
            <td><strong>{r['username']}</strong></td>
            <td>{r['ip']}</td>
            <td>{r['games_analyzed']}</td>
            <td style='color:#888;font-size:0.85em'>{(r['question'] or '')[:40]}</td>
            <td>{r['input_tokens']}</td>
            <td>{r['output_tokens']}</td>
            <td>{cost_p}p</td>
        </tr>"""

    top_html = ""
    for u in top_users:
        cost_p = round((u["cost"] or 0) * 100 / 1.27, 1)
        top_html += f"<tr><td>{u['username']}</td><td>{u['n']}</td><td>{cost_p}p</td></tr>"

    return f"""<!DOCTYPE html>
<html><head><title>Chess Teacher — Admin</title>
<style>
body{{font-family:sans-serif;background:#111;color:#ddd;padding:24px;}}
h2{{color:#4caf50;}} h3{{color:#888;margin-top:32px;}}
table{{border-collapse:collapse;width:100%;margin-top:12px;font-size:0.85rem;}}
th{{background:#222;padding:8px 12px;text-align:left;color:#aaa;}}
td{{padding:6px 12px;border-bottom:1px solid #222;}}
.stat{{display:inline-block;background:#1a2a1a;border:1px solid #2c5f2e;
       border-radius:8px;padding:16px 24px;margin:8px 8px 8px 0;}}
.stat .val{{font-size:1.8rem;color:#4caf50;font-weight:bold;}}
.stat .lbl{{font-size:0.75rem;color:#888;text-transform:uppercase;}}
.bar-wrap{{background:#222;border-radius:4px;height:10px;width:200px;display:inline-block;vertical-align:middle;margin-left:12px;}}
.bar{{background:#4caf50;height:10px;border-radius:4px;width:{min(budget_pct,100):.0f}%;}}
</style></head><body>
<h2>♟ Chess Teacher — Admin</h2>
<div>
  <div class="stat"><div class="val">{monthly_analyses}</div><div class="lbl">Analyses this month</div></div>
  <div class="stat"><div class="val">{round(monthly_spend*100/1.27,1)}p</div><div class="lbl">Spent this month</div>
    <div style="margin-top:6px"><span style="font-size:0.8rem;color:#888">{budget_pct:.0f}% of £1 budget</span>
    <span class="bar-wrap"><span class="bar"></span></span></div>
  </div>
  <div class="stat"><div class="val">{len(logs)}</div><div class="lbl">Total analyses (all time)</div></div>
</div>
<h3>Top users</h3>
<table><tr><th>Username</th><th>Analyses</th><th>Cost</th></tr>{top_html}</table>
<h3>Recent analyses</h3>
<table>
  <tr><th>Time (UTC)</th><th>Username</th><th>IP</th><th>Games</th><th>Question</th><th>In tokens</th><th>Out tokens</th><th>Cost</th></tr>
  {rows_html}
</table>
</body></html>"""


# Run on startup regardless of whether launched via gunicorn or directly
init_db()
start_scheduler()

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5858))
    app.run(debug=False, host="0.0.0.0", port=port)
