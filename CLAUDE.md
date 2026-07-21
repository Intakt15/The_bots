# Claude Code Guide

## Project purpose

This is a standalone modular trading-intelligence system. It is not INTAKT Engine v7 and must not import, edit, or depend on that project.

The current goal is a safe, testable research and paper-trading system. Do not add live trading behavior unless explicitly requested after paper-trading validation.

## Architecture rules

- Keep `domain/` framework-free and immutable; never import broker SDKs, database drivers, web frameworks, or AI-provider SDKs there.
- Add external systems only as `adapters/` implementing the `Protocol` interfaces in `interfaces/ports.py`.
- Keep broker order placement behind `ExecutionGateway`.
- Route every executable trade through `DecisionPipeline`: signal -> consensus -> risk -> execution.
- `RiskGuardian` has final veto authority. Never allow an agent, dashboard, learning job, or adapter to bypass it.
- `LearningAI` may generate recommendations only. It must not apply policy or risk-limit changes automatically.
- Keep the dashboard read-only.

## Safety requirements

- Default to paper or replay operation. Do not include broker credentials in source or logs.
- Treat model and vendor responses as untrusted data; validate symbols, price fields, side, confidence, quantity, timestamps, and IDs.
- Make execution idempotent using the decision ID.
- Persist decisions, agent assessments, policy versions, executions, and outcomes for auditability.
- Do not promise or imply profitability. Backtests must model costs, spread, slippage, and data limitations.

## Development workflow

1. Define or update a domain contract and its port before creating an adapter.
2. Add fixture-backed tests for adapters and deterministic tests for policy changes.
3. Preserve the existing conservative default: abstain if no signal exists.
4. Run `python3 -m compileall -q src` and, when installed, `python3 -m pytest -q` before completing a change.

## First recommended implementation slice

Implement a CSV market-replay adapter, SQLite decision repository, deterministic signal strategy, fixed risk policy, paper execution adapter, and a decision-log dashboard—then validate the complete path with backtests and paper trading.
