# Phase 1 — Split Flask Server into Modules

## Goal
Break `scripts/serve_results.py` (1365 lines) into a `scripts/server/` package with separate files for app creation, data loading, page routes, and API routes.

## TODOs
- [x] Create `scripts/server/` package with `__init__.py`
- [x] Extract data loading functions into `scripts/server/data.py`
- [x] Extract API endpoints into `scripts/server/api.py`
- [x] Extract page routes + HTML templates into `scripts/server/routes.py`
- [x] Create `scripts/server/app.py` as the Flask app factory
- [x] Update `scripts/serve_results.py` to be a thin entry point that imports from the package
- [x] Verify the server still starts and all routes work

## Notes
