import asyncio
import sys
import logging

def main():
    logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
    
    if len(sys.argv) > 1 and sys.argv[1] != 'bot':
        # CLI mode
        from bot.cli import cli_main
        cli_main()
    else:
        # Bot mode
        from bot.telegram_bot import run_bot
        asyncio.run(run_bot())

if __name__ == '__main__':
    main()
