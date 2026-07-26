# Off-Chain Bot Structure

```text
src/trading_intelligence/offchain_bot/
  __init__.py                Public package exports
  cli.py                     Environment-driven CLI entry point
  config.py                  Environment-only settings and secret fields
  models.py                  Framework-free domain dataclasses
  strategy.py                Opportunity scanner with rolling-window logic
  risk.py                    Final trade gate, slippage checks, kill switch
  bot.py                     Orchestration loop for market data + execution
  connectors/
    __init__.py              Connector exports
    base.py                  Protocols for market/execution clients
    ccxt_connector.py        CEX market data and live execution adapter
    web3_connector.py        Web3 oracle market data adapter
    paper_connector.py       Paper/demo execution simulator
```

## Security posture

- Secret values are never hardcoded.
- The bot reads environment variables only.
- Production secret injection should come from Azure Key Vault, Container Apps secrets, or the CI/CD environment.
- Paper/demo mode stays simulated even when the same connectors are used in development.
- Live CEX execution is allowed only when the bot is explicitly started in live mode.
- The Web3 backend is read-only by default; it should be used for monitoring or oracle-driven opportunity detection unless a dedicated DEX execution adapter is added.
