# PersonalTrading - Claude Development Context

> **IMPORTANT: NEVER send orders into IB Gateway.** This project is for experimentation and research only. All orders must be entered manually by the user. Claude must never place, submit, or trigger any trade orders programmatically.

> **IMPORTANT: No automated order execution — ever.** This project is purely for experimentation and research. The user will always enter orders manually via the IB Gateway UI. Claude must only generate rebalance reports and recommendations; it must never programmatically place, submit, modify, or cancel any trade orders.

---

## Quick Reference

| Topic | File |
|-------|------|
| **GSD planning workflow, commands, rules** | [docs/gsd-planning.md](docs/gsd-planning.md) |
| **MCP tools (ib-trading server)** | [docs/mcp-tools.md](docs/mcp-tools.md) |
| Project overview, components, IB connection, backtesting specs | [docs/project.md](docs/project.md) |
| Strategy architecture, algorithms, composability | [docs/strategies.md](docs/strategies.md) |
| CLI reference (all 4 modes + examples) | [docs/cli.md](docs/cli.md) |
| Web dashboard usage & API | [docs/dashboard.md](docs/dashboard.md) |
| Session log, next actions, known bugs | [docs/session_log.md](docs/session_log.md) |
| Full file/directory reference | [docs/project-structure.md](docs/project-structure.md) |
| Session history | `ai_iterations/` |
| Architecture decisions | `decisions/` |

---

## Clarification

- When requirements are ambiguous or a task has multiple valid interpretations, use AskUserQuestion to clarify before proceeding.
- Before making major design decisions, confirm assumptions with AskUserQuestion.

---

## Code Standards

- Black formatting, line length 88
- Async/await throughout
- Type hints preferred
- pytest + pytest-asyncio for tests
- Logging: DEBUG/INFO/WARNING/ERROR levels
- Ensure lint is clean
- Files should not exceed 600 lines unless absolutely necessary
