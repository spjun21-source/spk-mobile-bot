# SPK Mobile Bot

A Telegram-based trading and market analysis bot integrating the LS Securities (Xing) API, Korea Public Data Portal, and Google Gemini AI.

## Directory Structure
- `src/main.py`: The entry point for the background bot service.
- `src/clients/`: API client wrappers (Xing REST, Xing Realtime, Public Data, Gemini).
- `scripts/`: Windows batch scripts to start, stop, and check the bot's status locally.
- `requirements.txt`: Python dependencies.

## Setup Instructions

1. **Install Requirements**
   Ensure you have Python installed, then install the dependencies:
   ```bash
   pip install -r requirements.txt
   ```

2. **Configuration**
   The bot expects `xing_config.json` and `accounts.json` in the root or parent directories (these are currently excluded via `.gitignore` for security). The Telegram and Gemini API keys are currently configured within `src/main.py`.

## Running the Bot locally
Use the provided batch scripts in the `scripts/` folder:
- To start the bot in the background: Run `scripts\start_bot.bat`
- To stop the background process: Run `scripts\stop_bot.bat`
- To check if the bot is running: Run `scripts\status_bot.bat`
