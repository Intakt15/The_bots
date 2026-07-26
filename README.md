# Multi-Agent MT5 Trading Intelligence

A production-ready, multi-agent trading system with **full MetaTrader 5 integration**. Five specialized AI agents collaborate through a consensus engine with a final-veto Risk Guardian. All decisions are audited via SQLite.

> **Paper/demo trading is the default.** Live MT5 requires `TRADING_ENVIRONMENT=live` and valid credentials (Windows + MT5 terminal running).

> **Desktop launch:** run `scripts/install_desktop_launcher.sh` once to create a double-clickable macOS `.app` bundle on your Desktop.

## Architecture

```
MT5 Terminal ---> Market Data Adapter (OHLCV + 14 indicators)
                           |
          ┌────────────────┼────────────────┐
          ▼                ▼                ▼
      SignalAI          NewsAI          SessionAI
   (4 strategies)   (calendar blackout)  (forex sessions)
          │                │                │
          └────────────────┼────────────────┘
                           ▼
                  Weighted Consensus
                   (audit trail)
                           │
                           ▼
                  Risk Guardian <-- FINAL VETO
                  (drawdown / correlation / ATR sizing / kill-switch)
                           │
                           ▼
                 Execution Gateway ---> MT5 Terminal (live)
                          │             Paper Simulator (paper)
                          ▼
                     SQLite Audit DB
```

## MT5 Adapters (all fully implemented)

| Adapter | File | What it does |
|---------|------|-------------|
| **MT5 Market Data** | `adapters/mt5_market_data.py` | Connects to MT5 terminal, fetches real-time bid/ask, OHLCV history, computes 14 technical indicators via `ta` library (RSI, MACD, EMA 12/26/50, ATR, Bollinger Bands, ADX, Pivot Points) |
| **MT5 Execution** | `adapters/mt5_execution.py` | Places real orders through MT5 with SL/TP, idempotency via decision_id dedup, connect/login/disconnect lifecycle |
| **Paper Trading** | `adapters/paper_execution.py` | Simulates fills with configurable slippage (0.5 pips default), fill probability (98%), idempotency guard |
| **Mock Data** | `adapters/mock_market_data.py` | Synthetic OHLCV + indicators for macOS/Linux development |
| **REST Trading** | `adapters/rest_execution.py` | Generic HTTP execution gateway for platforms that expose AI-trading APIs and use keyring-stored API keys/pins |

## Components

| Component | Description |
|-----------|-------------|
| **SignalAI** | 4-strategy technical analysis: EMA crossover, RSI momentum, Bollinger Band volatility, Pivot S/R. Requires >=2 agreeing strategies. Produces Signal with SL/TP. |
| **NewsAI** | Economic calendar blackout (+-15 min for NFP, FOMC, CPI). CSV-backed. |
| **SessionAI** | Asian/London/NY session detection with instrument mapping. Overlap = highest eligibility. |
| **RiskManager** | Daily/total drawdown, position caps, correlation basket exposure, ATR-based sizing, volatility kill-switch. **Final veto -- no bypass.** |
| **LearningAI** | Win rate, profit factor, Sharpe, expectancy, regime detection. **Advisory only** -- never auto-applies. |
| **WeightedConsensus** | Configurable agent weights, disagreement detection, tie-breaking, full audit trail. |
| **DecisionPipeline** | Consensus -> Risk -> Execution -> Audit. Only approved decisions reach the broker. |

## Quick Start

```bash
# Clone and install
git clone https://github.com/Intakt15/The_bots.git
cd The_bots
pip install -e '.[dev]'

# Run tests
pytest  # 17 tests, all passing

# Paper trading dry run (works on any OS)
python -m trading_intelligence.main --once

# Live MT5 (Windows only)
# 1. Copy .env.example to .env and fill in credentials
# 2. Ensure MT5 terminal is running and logged in
# 3. Run:
TRADING_ENVIRONMENT=live python -m trading_intelligence.main
```

## Configuration

See `.env.example` for all settings. Key variables for MT5 live mode:

```bash
TRADING_ENVIRONMENT=live
MT5_LOGIN=12345678
MT5_PASSWORD=your_password
MT5_SERVER=BrokerServer
MT5_TERMINAL_PATH=C:\Program Files\MetaTrader 5\terminal64.exe
```

## Project Structure

```
src/trading_intelligence/
  domain/           Immutable models
  interfaces/       Protocol ports
  agents/           5 specialist agents
  application/      Consensus, Pipeline, Engine
  adapters/         MT5 market data, MT5 execution, paper, mock
  database/         SQLite repository
  config.py         Typed settings
  main.py           Entry point
tests/              17 tests
```

## Requirements

- Python 3.11+
- MetaTrader 5 terminal (Windows, for live mode only)
- `MetaTrader5` Python package (Windows only: `pip install MetaTrader5`)

## Safety

- **Paper/demo mode default** -- never trades live unless explicitly configured
- **Risk Guardian final veto** -- no agent, dashboard, or adapter can bypass it
- **LearningAI advisory only** -- all recommendations require human review
- **Idempotent execution** -- decision_id dedup prevents double orders
- **Full audit trail** -- every signal, assessment, decision, execution, and outcome persisted
- **MT5 optional** -- macOS/Linux development uses mock data + paper execution
- **Credentials in OS keyring** -- API keys, secrets, and access pins can be stored per platform profile instead of plaintext files

## Off-Chain Bot Scaffold

```text
src/trading_intelligence/offchain_bot/
  config.py                  Environment-only runtime settings
  models.py                  Quote, opportunity, risk, and execution dataclasses
  strategy.py                Rolling-window trade opportunity scanner
  risk.py                    Slippage protection and emergency kill switch
  bot.py                     Orchestrates market data, risk, and execution
  connectors/                CEX, Web3, and paper/demo adapters
infra/main.bicep             Azure Container Apps + ACR + Key Vault
.github/workflows/deploy.yml  OIDC-based CI/CD pipeline
Dockerfile                   python:3.11-slim runtime image
```

The off-chain bot reads all sensitive values from environment variables only. In Azure, inject them from Key Vault into Container Apps rather than baking them into the image or workflow logs.

### GitHub Actions / Azure deployment inputs

Configure these repository secrets and variables before enabling the deploy workflow:

- Secrets: `AZURE_CLIENT_ID`, `AZURE_TENANT_ID`, `AZURE_SUBSCRIPTION_ID`
- Variables: `ACR_NAME`, `AZURE_RESOURCE_GROUP`, `CONTAINER_APP_NAME`

For local macOS launches, run `scripts/install_desktop_launcher.sh` to build the `.app` bundle on your Desktop. The app launches the bot in the background and writes logs to `~/Library/Logs/Multi-Agent Trading Intelligence/launcher.log`.
