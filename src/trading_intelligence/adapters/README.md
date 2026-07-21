# Adapters

Place external integrations here. Each adapter must implement an interface in `interfaces/ports.py`, never leak SDK types into `domain`, and have a simulator or fixture-backed test before use.

Suggested future modules: `mt5_execution.py`, `paper_execution.py`, `market_data.py`, `economic_calendar.py`, and `sqlite_repository.py`.
