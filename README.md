# Discord Prediction Market Bot

A small Discord bot that runs binary (YES/NO) prediction markets inside a server. Members create accounts, trade virtual shares on automated-market-maker pricing (LMSR), and admins resolve markets to pay out winners.

## Features

- Binary prediction markets, priced by a logarithmic market scoring rule (LMSR)
- Each winning share pays a fixed 100 credits; markets start at 50 credits / share
- Configurable per-server: currency name, starting balance, market liquidity, auto-inflation
- Accounts linked to Discord identity (no re-auth per trade)
- Net-worth leaderboard with win-rate tracking
- Odds-over-time graph per market (`/odds`) and daily net-worth graph per user (`/portfolio`)
- Peer-to-peer transfers (`/transfer`)
- Optional transaction tax on trades
- 10-minute trade cooldown per user
- All admin actions gated by Discord's administrator permission

## Stack

Python 3.11+, [discord.py](https://github.com/Rapptz/discord.py) 2.x, SQLite via `aiosqlite`.

## Commands

| Command | Who | Description |
| --- | --- | --- |
| `/setup` | admin | Initialize the bot on this server |
| `/create` | anyone | Create an account |
| `/markets` | anyone | List open markets |
| `/odds` | anyone | Odds-over-time graph for a market |
| `/trade` | anyone | Buy YES or NO shares |
| `/transfer` | anyone | Send currency to another user |
| `/portfolio` | anyone | Balance, positions, stats, net-worth graph |
| `/leaderboard` | anyone | Top 10 by net worth |
| `/info`, `/commands` | anyone | Bot / command info |
| `/settings ...` | admin | Currency, balance, inflation, market lifecycle, grants |

## Project layout

```
main.py               bot entry point
config.py             constants and env loading
db.py                 SQLite schema and connection helpers
market.py             LMSR math
networth.py           net-worth valuation helper
charts.py             matplotlib chart rendering
inflation.py          background task for periodic credit grants
snapshots.py          background task for daily net-worth snapshots
permissions.py        admin/owner permission checks
cog_setup.py          /setup
cog_accounts.py       /create
cog_markets.py        /markets, /portfolio
cog_trade.py          /trade
cog_settings.py       /settings group (admin)
cog_info.py           /info, /commands, /leaderboard
```

## License

MIT
