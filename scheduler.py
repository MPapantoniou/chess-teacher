import sqlite3
from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger
import pytz

from chess_api import get_recent_games, get_todays_games
from analyzer import analyze_games
from emailer import send_feedback_email


def run_daily_emails():
    """Send daily coaching emails to all active subscribers."""
    conn = sqlite3.connect("chess_teacher.db")
    conn.row_factory = sqlite3.Row
    try:
        subs = conn.execute("SELECT * FROM subscriptions").fetchall()
        for sub in subs:
            try:
                username = sub["username"]
                count = sub["games_per_email"]
                mode = sub["mode"]  # 'recent' or 'today'

                if mode == "today":
                    games = get_todays_games(username)
                    if not games:
                        continue  # no games today, skip
                else:
                    games = get_recent_games(username, count)

                if not games:
                    continue

                feedback = analyze_games(games, username)
                send_feedback_email(sub["email"], username, feedback, len(games))
                print(f"[scheduler] Sent to {sub['email']} for {username}")
            except Exception as e:
                print(f"[scheduler] Failed for {sub['email']}: {e}")
    finally:
        conn.close()


def start_scheduler():
    scheduler = BackgroundScheduler()
    # 8am UTC daily
    scheduler.add_job(run_daily_emails, CronTrigger(hour=8, minute=0, timezone=pytz.UTC))
    scheduler.start()
    return scheduler
