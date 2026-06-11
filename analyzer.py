import anthropic
from chess_api import format_game_for_analysis

client = anthropic.Anthropic()


def analyze_games(games: list[dict], username: str, question: str = "") -> str:
    """Analyze chess games using Claude and return coaching feedback."""
    game_blocks = [
        f"--- Game {i} ---\n{format_game_for_analysis(g, username)}"
        for i, g in enumerate(games, 1)
    ]
    games_text = "\n\n".join(game_blocks)
    n = len(games)

    if question:
        prompt = f"""You are a friendly chess coach. The player ({username}) has shared {n} recent game(s) and has a specific question.

{games_text}

Their question: {question}

Answer their question with specific references to moves in their games where possible. Be honest and encouraging."""
    else:
        prompt = f"""You are a friendly chess coach reviewing {username}'s {n} most recent game(s).

{games_text}

Give structured coaching feedback with these sections:
## Opening Play
## Middlegame
## Endgame (if applicable)
## Key Patterns (recurring habits — good or bad)
## Top Priority
One concrete thing to focus on to improve fastest.

Be specific (reference actual moves), honest, and encouraging. Keep it readable — no walls of text."""

    response = client.messages.create(
        model="claude-haiku-4-5-20251001",
        max_tokens=1800,
        messages=[{"role": "user", "content": prompt}],
    )

    input_tokens = response.usage.input_tokens
    output_tokens = response.usage.output_tokens
    # Haiku pricing: $0.80/M input, $4.00/M output
    cost_usd = (input_tokens * 0.0000008) + (output_tokens * 0.000004)

    return response.content[0].text, input_tokens, output_tokens, cost_usd


def analyze_single_game(pgn: str, username: str, move_number=None, fen: str = "") -> tuple:
    """Analyze a specific game position or full game for the move-by-move review."""
    if move_number is not None:
        prompt = f"""You are a chess coach. {username} has paused to study this position (move {move_number}).

Game PGN: {pgn[:3000]}
Current FEN: {fen}

Give focused coaching in 2-3 short paragraphs:
1. What are the key features of this position — threats, weak squares, piece activity?
2. Was the last move good or questionable? What was the idea?
3. What should {username} consider doing next?

Name specific squares and pieces. Be concise and direct."""
    else:
        prompt = f"""You are a chess coach reviewing {username}'s complete game.

PGN: {pgn[:4000]}

## Opening
Comment on the opening choices and any early inaccuracies.

## Critical Moments
The 2-3 most important positions. Give the move number and explain what happened and what was better.

## Endgame
Brief comment if relevant.

## Key Lesson
One concrete thing to take from this game.

Reference specific moves and be direct."""

    response = client.messages.create(
        model="claude-haiku-4-5-20251001",
        max_tokens=600 if move_number is not None else 1400,
        messages=[{"role": "user", "content": prompt}],
    )
    tok_in = response.usage.input_tokens
    tok_out = response.usage.output_tokens
    cost = (tok_in * 0.0000008) + (tok_out * 0.000004)
    return response.content[0].text, tok_in, tok_out, cost
