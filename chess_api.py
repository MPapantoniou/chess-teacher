import requests
from datetime import datetime, timezone

HEADERS = {"User-Agent": "ChessTeacher/1.0 mikaelpapa@gmail.com"}


def get_recent_games(username: str, count: int = 3) -> list[dict]:
    """Fetch the most recent N games for a Chess.com username."""
    try:
        resp = requests.get(
            f"https://api.chess.com/pub/player/{username}/games/archives",
            headers=HEADERS,
            timeout=10,
        )
        if resp.status_code == 404:
            raise ValueError(f"Username '{username}' not found on Chess.com")
        resp.raise_for_status()

        archives = resp.json().get("archives", [])
        if not archives:
            return []

        games = []
        for archive_url in reversed(archives):
            resp = requests.get(archive_url, headers=HEADERS, timeout=10)
            if resp.status_code != 200:
                continue
            month_games = resp.json().get("games", [])
            month_games.sort(key=lambda g: g.get("end_time", 0), reverse=True)
            games.extend(month_games)
            if len(games) >= count:
                break

        return games[:count]
    except ValueError:
        raise
    except Exception as e:
        print(f"Error fetching games for {username}: {e}")
        return []


def get_todays_games(username: str) -> list[dict]:
    """Fetch games played today (UTC) for a username."""
    today = datetime.now(timezone.utc)
    try:
        archive_url = (
            f"https://api.chess.com/pub/player/{username}"
            f"/games/{today.year}/{today.month:02d}"
        )
        resp = requests.get(archive_url, headers=HEADERS, timeout=10)
        if resp.status_code != 200:
            return []

        today_start = today.replace(hour=0, minute=0, second=0, microsecond=0)
        today_ts = int(today_start.timestamp())

        return [
            g
            for g in resp.json().get("games", [])
            if g.get("end_time", 0) >= today_ts
        ]
    except Exception as e:
        print(f"Error fetching today's games for {username}: {e}")
        return []


def format_game_for_analysis(game: dict, player_username: str) -> str:
    """Format a single game into a readable block for Claude."""
    white = game.get("white", {})
    black = game.get("black", {})
    player_color = "White" if white.get("username", "").lower() == player_username.lower() else "Black"

    result_map = {"win": "Won", "lose": "Lost", "draw": "Drew", "agreed": "Drew", "repetition": "Drew",
                  "stalemate": "Drew", "insufficient": "Drew", "timeout": "Lost (timeout)",
                  "resigned": "Lost (resigned)", "checkmated": "Lost (checkmated)"}

    player_side = white if player_color == "White" else black
    opponent_side = black if player_color == "White" else white

    player_result = result_map.get(player_side.get("result", ""), player_side.get("result", "?"))

    lines = [
        f"Time control: {game.get('time_class', 'unknown')} ({game.get('time_control', '')})",
        f"Player: {player_username} ({player_color}, {player_side.get('rating', '?')}) — {player_result}",
        f"Opponent: {opponent_side.get('username', '?')} ({opponent_side.get('rating', '?')})",
    ]

    pgn = game.get("pgn", "")
    if pgn:
        lines.append(f"\nPGN:\n{pgn}")

    return "\n".join(lines)
