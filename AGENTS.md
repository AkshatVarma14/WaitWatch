# WaitWatch — Agent Guidelines

## Project Identity

**WaitWatch** is a real-time public transit tracking web application. It tracks public transport vehicles, displays routes and stops on an interactive map, and provides estimated arrival times (ETAs) using live vehicle positions and historical delay data.

## Purpose

- Track public transport vehicles in real time
- Display transit routes, stops, and schedules
- Provide accurate ETAs using GTFS-Realtime data and historical analysis
- Support multiple cities through configurable transit feeds

## Approved Technology Stack

| Layer | Technology |
|-------|------------|
| Frontend | React, TypeScript, Vite, Tailwind CSS, TanStack Query, Zustand |
| Backend | Python, FastAPI, Pydantic, SQLAlchemy, Alembic |
| Database | PostgreSQL, PostGIS |
| Frontend Testing | Vitest |
| Backend Testing | Pytest |
| CI/CD | GitHub Actions |

> **Do NOT introduce alternative frameworks, ORMs, or state management libraries without explicit approval.**

## Repository Structure

```
WaitWatch/
├── apps/web/          # React frontend
├── apps/api/          # FastAPI backend
├── docs/              # Documentation
├── infrastructure/    # Docker, deployment configs
├── scripts/           # Utility scripts
└── .github/workflows/ # CI/CD
```

## Coding Conventions

### TypeScript (Frontend)

- **Strict mode** enabled — no exceptions
- **No `any` type** — use proper types, generics, or `unknown` with narrowing
- **Functional components** only — no class components
- **Named exports** — avoid default exports
- **camelCase** for variables, functions, and file names
- **PascalCase** for components, types, and interfaces

### Python (Backend)

- **Type hints required** on all function signatures and return types
- **Async where appropriate** — use `async def` for I/O-bound operations
- **Pydantic** for all request/response validation
- **snake_case** for variables, functions, and file names
- **PascalCase** for classes

### General

- All files must have **meaningful content** — no empty placeholder files
- Keep imports organized and remove unused imports
- Write docstrings for public functions and classes
- Use consistent error handling patterns

## Testing Requirements

### Frontend (Vitest)

- Test critical business logic and utility functions
- Test key UI components with meaningful assertions
- Run tests: `cd apps/web && npm test`

### Backend (Pytest)

- Test **all** API endpoints
- Test data processing and transformation logic
- Test database operations with test fixtures
- Run tests: `cd apps/api && pytest`

### Before Committing

- All tests **must pass** before committing code
- Run the full test suite, not just new tests
- CI pipeline validates this — do not bypass it

## Git and GitHub Rules

### Commit Messages

Use **conventional commit** format:

- `feat:` — new feature or functionality
- `fix:` — bug fix
- `chore:` — maintenance, dependency updates, config changes
- `docs:` — documentation changes
- `test:` — adding or updating tests
- `refactor:` — code restructuring without behavior change

Examples:
```
feat: add GTFS route ingestion endpoint
fix: correct stop proximity query radius
docs: update API endpoint documentation
test: add vehicle position API tests
```

### Branch Strategy

- Push to **main** branch during initial development
- Use **feature branches** for larger changes in later stages
- CI must pass before merging any pull request

## Security Requirements

- **Never commit** credentials, API keys, secrets, or `.env` files
- Use `.env.example` as a configuration template (committed to repo)
- All database credentials must come from **environment variables only**
- Do not log sensitive information
- Do not hardcode connection strings

## Important Constraints

- **Do NOT make unnecessary architectural changes** — follow the approved stack above
- **Do NOT introduce new dependencies** without clear justification
- **Do NOT create empty placeholder files** — every file must serve a purpose
- **Do NOT skip tests** — all new functionality must be tested
- **Prioritize working functionality** over premature optimization
