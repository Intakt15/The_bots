# Architecture

## Boundaries

The project uses ports-and-adapters architecture. `domain` never imports a broker SDK, database driver, dashboard framework, or AI provider. `interfaces` declares what the application needs. `adapters` supplies technology-specific implementations.

## Decision lifecycle

1. Data adapters build a timestamped `MarketSnapshot`.
2. Signal, news, and session agents independently return structured assessments.
3. Consensus combines eligible assessments into a `TradeDecision` candidate.
4. Risk evaluates the candidate against account state and policy; it may reject or resize it.
5. The application submits only approved decisions through `ExecutionGateway`.
6. Storage records all artifacts; the learning agent consumes closed outcomes offline or in a controlled review job.

## Non-negotiable control points

- `RiskGuardian` is the final approval authority before execution.
- `ExecutionGateway` owns idempotency and broker acknowledgement handling.
- `LearningAgent` can recommend policy changes but cannot apply them directly.
- `Dashboard` is read-only against operational data.
- Backtesting uses the same domain pipeline and marks every result as simulated.

## Initial integration choices

| Need | Initial boundary | Future adapter examples |
| --- | --- | --- |
| Market data | `MarketDataProvider` | MT5 feed, vendor REST, CSV replay |
| News calendar | `NewsProvider` | economic-calendar API, curated feed |
| Execution | `ExecutionGateway` | paper broker, MT5 bridge |
| Storage | `DecisionRepository` | SQLite, PostgreSQL |
| Dashboard | `DashboardQueryService` | FastAPI, Streamlit, React API |

No adapter belongs in the initial domain implementation. Add a real adapter only after its contract has a simulator-backed test.
