# Pegasus Galaxy Autonomous Bot Dockerfile
# Lightweight Python 3.12/3.13 image for Linux VPS deployment
FROM python:3.12-slim

WORKDIR /app

# Install dependencies
RUN pip install --no-cache-dir httpx rich

# Copy bot files
COPY peg_client.py peg_bot.py bot_strategy.py bot_config.json ./
COPY .env ./

# Run the autonomous bot loop
CMD ["python", "peg_bot.py"]
