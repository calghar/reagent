"""Seed the reagent SQLite DB with realistic cost entries for dashboard testing."""

# ruff: noqa: S311

import random
import sqlite3
import uuid
from datetime import UTC, datetime, timedelta
from pathlib import Path

DB_PATH = Path.home() / ".reagent" / "reagent.db"

# Provider pricing per million tokens
PROVIDERS = [
    {
        "provider": "anthropic",
        "model": "claude-sonnet-4-20250514",
        "input_price_per_m": 3.00,
        "output_price_per_m": 15.00,
    },
    {
        "provider": "openai",
        "model": "gpt-4o",
        "input_price_per_m": 2.50,
        "output_price_per_m": 10.00,
    },
    {
        "provider": "google",
        "model": "gemini-2.5-pro",
        "input_price_per_m": 1.25,
        "output_price_per_m": 5.00,
    },
]

ASSET_TYPES = ["agent", "skill", "hook", "command", "claude_md"]

ASSET_NAMES = {
    "agent": ["review", "debug", "deploy", "test-runner", "docs-writer"],
    "skill": ["lint-fix", "refactor", "migrate-db", "api-gen", "test-gen"],
    "hook": ["pre-commit", "post-merge", "pre-push"],
    "command": ["build", "deploy", "rollback", "status"],
    "claude_md": ["CLAUDE.md"],
}

NUM_ENTRIES = 50
DAYS_BACK = 14


def _calculate_cost(
    input_tokens: int,
    output_tokens: int,
    input_price_per_m: float,
    output_price_per_m: float,
) -> float:
    input_cost = (input_tokens / 1_000_000) * input_price_per_m
    output_cost = (output_tokens / 1_000_000) * output_price_per_m
    return round(input_cost + output_cost, 6)


def seed() -> None:
    """Insert 50 realistic cost entries into the DB."""
    if not DB_PATH.exists():
        print(f"Database not found at {DB_PATH}")
        print("Run 'reagent evaluate .' first to create the database.")
        return

    conn = sqlite3.connect(DB_PATH)
    conn.execute("PRAGMA journal_mode=WAL")

    now = datetime.now(UTC)
    random.seed(42)  # reproducible

    rows: list[tuple[str, str, str, str, str, str, int, int, float, int, str, int]] = []

    for _ in range(NUM_ENTRIES):
        provider_info = random.choice(PROVIDERS)
        provider = provider_info["provider"]
        model = provider_info["model"]

        asset_type = random.choice(ASSET_TYPES)
        asset_name = random.choice(ASSET_NAMES[asset_type])

        input_tokens = random.randint(500, 2000)
        output_tokens = random.randint(200, 1500)

        cost_usd = _calculate_cost(
            input_tokens,
            output_tokens,
            provider_info["input_price_per_m"],
            provider_info["output_price_per_m"],
        )

        # Spread across last 14 days
        offset_seconds = random.randint(0, DAYS_BACK * 86400)
        timestamp = now - timedelta(seconds=offset_seconds)
        ts_str = timestamp.strftime("%Y-%m-%dT%H:%M:%S")

        latency_ms = random.randint(200, 3000)
        tier = random.choice(["demo", "demo", "demo", "fast"])
        was_fallback = 1 if random.random() < 0.1 else 0

        rows.append(
            (
                str(uuid.uuid4()),
                ts_str,
                provider,
                model,
                asset_type,
                asset_name,
                input_tokens,
                output_tokens,
                cost_usd,
                latency_ms,
                tier,
                was_fallback,
            )
        )

    conn.executemany(
        """
        INSERT OR IGNORE INTO cost_entries
            (cost_id, timestamp, provider, model, asset_type, asset_name,
             input_tokens, output_tokens, cost_usd, latency_ms, tier, was_fallback)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        rows,
    )
    conn.commit()

    # Verify totals
    cursor = conn.execute(
        "SELECT COUNT(*) AS cnt, SUM(cost_usd) AS total FROM cost_entries"
    )
    result = cursor.fetchone()
    count, total = result[0], result[1]
    print(f"Seeded {len(rows)} cost entries (DB now has {count} total)")
    print(f"Total cost in DB: ${total:.4f}")

    # Show breakdown by provider
    cursor = conn.execute(
        "SELECT provider, COUNT(*), SUM(cost_usd) FROM cost_entries GROUP BY provider"
    )
    for row in cursor.fetchall():
        print(f"  {row[0]}: {row[1]} entries, ${row[2]:.4f}")

    conn.close()


if __name__ == "__main__":
    seed()
