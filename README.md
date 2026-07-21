# Multi-Agent Trading Intelligence

A standalone, modular decision-support and trade-governance system. It produces auditable trade decisions; a broker-specific execution adapter is deliberately isolated from all market-intelligence components.

> Status: scaffold only. It does not connect to a broker, place orders, or make profitability claims. Use paper trading and independent validation before considering any live deployment.

## Design

```text
Market / calendar / news inputs
            |
  Signal AI · News AI · Session AI
            |
     Consensus Engine ----> Learning AI <---- trade outcomes
            |
          Risk AI
            |
   Execution Interface (adapter boundary)
            |
         Broker / simulator

Database <---- all decision and outcome records ----> Dashboard / Backtester
```

The execution layer accepts only a `TradeDecision` that has passed consensus and risk checks. It is a port, not an MT5 implementation; an MT5 adapter can be added later without changing the domain or agents.

## Included components

| Component | Responsibility |
| --- | --- |
| Signal AI | Create evidence-backed candidate trade signals. |
| Consensus Engine | Combine specialist opinions into a single decision. |
| Risk AI | Enforce exposure, drawdown, sizing, and kill-switch rules. |
| Learning AI | Record and analyze completed-decision outcomes. |
| News AI | Convert event risk into a tradability assessment. |
| Session AI | Apply market-session policies. |
| Execution Interface | Define the safe boundary for broker or simulator adapters. |
| Database | Persist signals, decisions, execution reports, and outcomes. |
| Dashboard | Read-only operational views and health metrics. |
| Backtester | Replays historical data through the same decision pipeline. |

## Quick start

Requires Python 3.11+.

```bash
cd multi_agent_trading_intelligence
python -m venv .venv
source .venv/bin/activate
pip install -e '.[dev]'
pytest
```

## Project layout

```text
src/trading_intelligence/
  domain/        Immutable business models and value objects
  interfaces/    Ports for data, execution, storage, and agents
  agents/        Specialist-agent skeletons
  application/   Pipeline orchestration
  adapters/      Future MT5, API, market-data, and storage adapters
  database/      Repository implementations and migrations
  dashboard/     Read-only presentation application
  backtesting/   Historical replay infrastructure
docs/            Architecture and implementation roadmap
```

## Safety and operating principles

- Treat model output as untrusted input; validate every field and limit every action.
- Keep final order placement deterministic, idempotent, and independently risk-gated.
- Persist each input, agent output, policy version, decision, and execution report for auditability.
- Start with simulation and walk-forward tests; do not let the learning module silently alter live-risk limits.
- Store credentials outside source control. `.env.example` lists expected configuration names.

See [architecture.md](docs/architecture.md) and [roadmap.md](docs/roadmap.md).
