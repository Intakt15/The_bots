# Delivery roadmap

## Phase 1 — safe vertical slice

- Implement a replay market-data adapter and SQLite repository.
- Implement deterministic trend/liquidity signal agents and fixed risk policy.
- Add a paper execution adapter with idempotency tests.
- Build a small decision-log dashboard.

## Phase 2 — research and validation

- Create historical-data normalization and walk-forward backtests.
- Define transaction-cost, spread, slippage, and latency assumptions explicitly.
- Add performance reports by instrument, session, regime, and decision version.

## Phase 3 — controlled integrations

- Add news-calendar and MT5 adapters behind the existing ports.
- Run in observation mode, then paper mode, with alerts and a manual kill switch.
- Require a documented risk review before any live broker credentials are enabled.

## Phase 4 — learning workflow

- Add offline feature evaluation and recommendations.
- Version datasets, models, policies, and experiment results.
- Promote changes only through review, reproducible backtests, and forward testing.
