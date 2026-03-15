# PersonalTrading - Claude Development Context

> **IMPORTANT: NEVER send orders into IB Gateway.** This project is for experimentation and research only. All orders must be entered manually by the user. Claude must never place, submit, or trigger any trade orders programmatically.

---

## Clarification

- When requirements are ambiguous or a task has multiple valid interpretations, use AskUserQuestion to clarify before proceeding.
- Before making major design decisions, confirm assumptions with AskUserQuestion.

---

## Documentation

| Topic | File |
|-------|------|
| Project overview, components, IB connection, backtesting specs | [docs/project.md](docs/project.md) |
| Strategy architecture, algorithms, composability | [docs/strategies.md](docs/strategies.md) |
| CLI reference (all 4 modes + examples) | [docs/cli.md](docs/cli.md) |
| Web dashboard usage & API | [docs/dashboard.md](docs/dashboard.md) |
| Session log, next actions, known bugs | [docs/session_log.md](docs/session_log.md) |
| Session history | `ai_iterations/` |
| Architecture decisions | `decisions/` |

---

## Code Standards

- Black formatting, line length 88
- Async/await throughout
- Type hints preferred
- pytest + pytest-asyncio for tests
- Logging: DEBUG/INFO/WARNING/ERROR levels
