FROM python:3.11-slim

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app

# Keep the runtime image small: install only what is needed to run the bot.
RUN useradd --create-home --shell /usr/sbin/nologin appuser

COPY pyproject.toml README.md /app/
COPY src /app/src

RUN pip install --upgrade pip \
    && pip install .

USER appuser

# The bot reads secrets from environment variables and/or cloud secret injection.
CMD ["python", "-m", "trading_intelligence.offchain_bot.cli"]
