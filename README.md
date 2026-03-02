# SPK Mobile Bot

A Telegram-based trading and market analysis bot integrating the LS Securities (Xing) API, Korea Public Data Portal, and Google Gemini AI.

## Directory Structure
- `src/main.py`: The entry point for the background bot service.
- `src/clients/`: API client wrappers (Xing REST, Xing Realtime, Public Data, Gemini).
- `skills/market-monitor/`: [v1.1.0] LS Securities real-time WebSocket adapter and Portfolio Simulation tools.
- `scripts/`: Windows batch and PowerShell scripts to manage the bot and tools.
- `requirements.txt`: Python dependencies.

## Setup Instructions

1. **Install Requirements**
   Ensure you have Python and Node.js installed.
   ```bash
   pip install -r requirements.txt
   cd skills/market-monitor && npm install
   ```

2. **Configuration (Remote Work SYNC)**
   - The `.gitignore` prevents sensitive `ls_config.json` and `xing_config.json` from being leaked.
   - For remote work, copy your `ls_config.json` manually into `skills/market-monitor/scripts/`.

## Running the Bot & Tools

### Main Bot
Use the provided scripts in the `scripts/` folder:
- `scripts\start_bot.bat`: Start the background service.

### Market Monitor v1.1.0 (LS WebSocket)
- `node skills/market-monitor/scripts/ls_websocket_adapter.js connect`: Start the real-time daemon.
- `node skills/market-monitor/scripts/portfolio_monitor.js`: View your real-time PnL.
- `node skills/market-monitor/scripts/mock_trade_executor.js`: Execute simulated trades.

