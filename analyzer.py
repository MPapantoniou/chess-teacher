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
