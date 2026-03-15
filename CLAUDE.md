# PersonalTrading - Claude Development Context

> **IMPORTANT**: If a user prompt is ambiguous or lacks sufficient detail, ask clarifying questions before proceeding. Do not make assumptions about intent on tasks involving trading logic, backtesting parameters, or strategy changes.

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
