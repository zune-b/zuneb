"""Main entry point for the Polymarket Prediction Machine."""

import asyncio
import argparse
import sys
import structlog
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# Configure logging
structlog.configure(
    processors=[
        structlog.stdlib.filter_by_level,
        structlog.stdlib.add_logger_name,
        structlog.stdlib.add_log_level,
        structlog.processors.TimeStamper(fmt="iso"),
        structlog.processors.StackInfoRenderer(),
        structlog.processors.format_exc_info,
        structlog.processors.UnicodeDecoder(),
        structlog.dev.ConsoleRenderer(colors=True),
    ],
    wrapper_class=structlog.stdlib.BoundLogger,
    context_class=dict,
    logger_factory=structlog.stdlib.LoggerFactory(),
    cache_logger_on_first_use=True,
)

logger = structlog.get_logger()


async def main():
    """Main entry point."""
    parser = argparse.ArgumentParser(
        description="Polymarket Prediction Machine",
    )

    parser.add_argument(
        "--dry-run",
        action="store_true",
        default=True,
        help="Run in dry-run mode (no real trades)",
    )

    parser.add_argument(
        "--live",
        action="store_true",
        help="Run in live mode (real trades - use with caution!)",
    )

    parser.add_argument(
        "--interval",
        type=int,
        default=15,
        help="Trading interval in minutes (default: 15)",
    )

    parser.add_argument(
        "--single-cycle",
        action="store_true",
        help="Run a single cycle and exit",
    )

    args = parser.parse_args()

    # Determine if dry run
    dry_run = not args.live

    logger.info(
        "Starting Polymarket Prediction Machine",
        mode="DRY RUN" if dry_run else "LIVE",
        interval=args.interval,
    )

    if not dry_run:
        logger.warning("=" * 60)
        logger.warning("LIVE TRADING MODE - Real money will be used!")
        logger.warning("=" * 60)

        # Confirmation prompt
        confirm = input("Type 'CONFIRM' to proceed with live trading: ")
        if confirm != "CONFIRM":
            logger.info("Live trading cancelled")
            return

    # Import here to avoid loading everything for --help
    from src.engine import create_engine

    engine = create_engine(
        dry_run=dry_run,
        trade_interval_minutes=args.interval,
    )

    try:
        if args.single_cycle:
            result = await engine.run_single_cycle()
            logger.info("Single cycle completed", **result)
        else:
            await engine.run_forever()

    except KeyboardInterrupt:
        logger.info("Received shutdown signal")
        await engine.stop()

    except Exception as e:
        logger.error("Engine failed", error=str(e))
        await engine.stop()
        raise


if __name__ == "__main__":
    asyncio.run(main())
