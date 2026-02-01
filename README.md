# Polymarket Prediction Machine

An automated trading system for Polymarket crypto markets using ensemble signal analysis.

## Architecture

```
├── python/                    # Python ML/prediction engine
│   ├── signals/              # Signal generators
│   ├── polymarket/           # Polymarket API integration
│   ├── strategies/           # Trading strategies
│   └── engine.py             # Main prediction engine
├── api/                       # Node.js/TypeScript API
│   └── src/                  # API source code
├── config/                    # Configuration files
└── docker-compose.yml        # Container orchestration
```

## Features

- **Ensemble Predictions**: Combines multiple signals (technical, sentiment, market data)
- **Automated Trading**: 15-minute trading cycles with automatic execution
- **Crypto Focus**: Specialized for Polymarket crypto prediction markets
- **REST API**: External API for monitoring and control
- **Risk Management**: Position sizing and loss limits

## Quick Start

```bash
# Install Python dependencies
cd python && pip install -r requirements.txt

# Install Node.js dependencies
cd api && npm install

# Configure environment
cp .env.example .env
# Edit .env with your Polymarket credentials

# Run the system
docker-compose up
```

## Configuration

See `.env.example` for required environment variables.

## API Endpoints

- `GET /api/health` - System health check
- `GET /api/markets` - List tracked crypto markets
- `GET /api/predictions` - Current predictions
- `GET /api/positions` - Active positions
- `POST /api/trade/execute` - Manual trade execution
- `POST /api/engine/start` - Start trading engine
- `POST /api/engine/stop` - Stop trading engine

## License

MIT
