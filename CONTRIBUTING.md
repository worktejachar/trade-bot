# Contributing to GX TradeIntel

Thank you for your interest in contributing! Here's how you can help.

## How to Contribute

1. **Fork** the repository
2. **Create a branch** for your feature: `git checkout -b feature/my-feature`
3. **Make changes** and test them
4. **Submit a Pull Request** with a clear description

## Areas We Need Help

### High Priority
- **Multi-index support** — Add BankNifty and FinNifty trading
- **Web dashboard** — React or Streamlit dashboard for monitoring
- **Regime detection** — Improve classification accuracy

### Medium Priority
- **Options Greeks** — Real-time Delta, Theta, Vega tracking
- **Spread strategies** — Bull call spreads, iron condors
- **Better slippage model** — Real bid-ask spread simulation

### Low Priority
- **PostgreSQL migration** — Move from CSV to proper database
- **API rate limiting** — Smart request throttling
- **Docker deployment** — Containerized setup

## Code Style

- Use `# -*- coding: utf-8 -*-` at the top of all files
- Add docstrings to all functions
- Keep functions under 50 lines
- Use type hints where possible
- Run `python3 -m py_compile your_file.py` before submitting

## Testing

Before submitting a PR:
```bash
# Compile check all files
python3 -c "import py_compile, os; [py_compile.compile(f, doraise=True) for f in os.popen('find . -name \"*.py\"').read().split()]"

# Run backtest
python3 backtest.py
```

## Disclaimer

All contributors acknowledge that this software is for educational purposes. No financial advice is provided or implied.
