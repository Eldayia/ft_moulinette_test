# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

Three documents are imported below and are part of these instructions (all in French):

- `docs/agent-guide.md` — the maintained guide to the existing code: module map, invariants, validation record. Keep it up to date when behaviour, layout or validation results change.
- `AGENT.md` — the user's current mission: a remote execution backend on Google Cloud Run sandboxes (VPS on OVH, untrusted C never executed there).
- `docs/cloudrun.md` — what has actually been verified in Google's docs, deviations from the mission, the integration plan and its progress. Update it as phases land.

`cli/README.md` is the user-facing guide for the CLI; `web/README.md` covers the local web part.

@docs/agent-guide.md

@AGENT.md

@docs/cloudrun.md

## Quick reference

The repo has two parts:

- `cli/` — ft-moulinette, a local grader for the 42 **Libft 1.3** and **Printf 1.1** subjects: a stdlib-only Python 3.10+ engine (no third-party runtime deps) that compiles the student's C code into temporary harnesses, runs functional/symbol/prototype/Makefile/Norminette/Valgrind checks, and reports text or JSON. Linux + GNU toolchain only (`-Wl,--wrap=malloc` is used for allocation-failure injection). Editor integrations live in `cli/integrations/`.
- `web/` — local web UI (`ft_moulinette_web`): stdlib `http.server` + vanilla HTML/CSS/JS, no build step, no deps. It runs the CLI as a subprocess with `--json --progress` (one run at a time, cancellable; live progress parsed from the stderr event lines) and never reimplements checks. Finished runs persist to `$XDG_STATE_HOME/ft-moulinette-web/history.json` (`--history`/`--no-history`; tests must never touch the default path). Run `./bin/ft-moulinette-web` (http://127.0.0.1:8042/); tests: `python3 -m unittest discover -s tests -v` from `web/`. Keep its HTTP guards (loopback bind, Host allow-list, Origin/Sec-Fetch-Site checks, JSON-only POST, CSP, `textContent`-only DOM): the engine executes student Makefiles unsandboxed.

### Commands (run from `cli/`)

```sh
python3 -m ft_moulinette /path/to/libft [--verbose|--json] [--project libft|printf]
bin/ft-moulinette /path/to/project                             # works from any cwd

python3 -m unittest discover -s tests -v                       # full suite (~70 s, compiles C)
python3 -m unittest discover -s tests -p 'test_printf.py' -v   # one test file
python3 -m unittest discover -s tests -k test_static_global -v # one test by name pattern
node --check integrations/vscode/extension.js
sh -n install.sh package.sh
```

Always run tests via `discover -s tests` from `cli/`: test modules import `references` from `tests/`, and `ft_moulinette` must be importable from the cwd. There is no linter configured. `cli/` scripts resolve paths relative to themselves, and `package.sh`'s archive has the contents of `cli/` at its root, so `cli/README.md` must work both in the repo and in an extracted archive.

### Runners (run from `runners/`)

`python3 -m unittest discover -s tests -v` — 65 tests, stdlib only (google-auth is mocked). `ft_moulinette_runners` holds the `ExecutionBackend` contract, protocol v1, archive validation and the Local/Mock/CloudRun backends; see `runners/README.md`. Invariants: never fall back from cloudrun to local; production accepts only isolated backends; reports are untrusted (validated, outcome recomputed by `protocol.classify`); never retry a request whose state is unknown; never log ID tokens.

### runner-api (run from `workers/cloudrun/`)

`.venv/bin/python -m unittest discover -s tests -v` after `python3 -m venv .venv && .venv/bin/pip install -r requirements-dev.txt`. FastAPI service deployed on Cloud Run; it only orchestrates `sandbox do` with documented flags (never `--allow-egress`/`--write`/writable mounts) and must fail closed. `tests/fake_sandbox.py` is a non-isolating test double, refused in production.

### Dispatcher, images, deploy

- `workers/dispatcher/` (VPS worker: Redis quotas via Lua, RQ 3 enqueue with `unique=True`, task): `.venv/bin/python -m unittest discover -s tests -v` (starts a pinned Redis container).
- Images: `deploy/gcp/build.sh` (no `--push` = local only; uses the classic builder when buildx is missing). Never add C tools to the runner or worker images.
- `deploy/gcp/*.sh` are never run against Google without the user's explicit go-ahead (billable resources); `render.py` tests: `python3 -m unittest discover -s deploy/gcp/tests`. `shellcheck -x -P SCRIPTDIR deploy/gcp/*.sh` must stay clean.
- Adversarial tests (`FTM_ADVERSARIAL_TESTS=docker`, smoke probes) need explicit authorization; never on the production VPS.

### CLI architecture in one pass

- `__main__.main()` → `engine.run()` → `engine.detect_project()` picks Printf (via `ft_printf.h` / `libftprintf.a` markers) or defaults to Libft; Printf is delegated to `printf.run_printf()`.
- Every external command goes through `engine.execute()` (argument lists, own process session, kill group on timeout → code 124, output capped at 64 KiB). Check modules receive `execute` and an `add` result callback as parameters rather than importing them — follow that pattern.
- Libft test data lives in `cases.py` (`FUNCTIONS`, `CASES`, C `PRELUDE`, malloc-failure scenarios) and must stay consistent with `prototypes.PROTOTYPES`; `runner.test_function()` builds and runs one harness per function. Printf's twelve groups and its `snprintf`-comparison harness live in `printf_cases.py`.
- Harnesses run twice: against independently compiled objects, then against the real archive built by the Makefile (result checks prefixed `archive:`).
- `run()`/`run_printf()` take an optional `progress` callback invoked from `add()` for every result; `--progress` streams them to stderr as JSON lines. The stream must equal `results`, in order.
- `diagnostics.locations()` remaps temp-dir paths back to the student's original files; `explain.py` turns raw failures into French pedagogical messages; `report.py` renders text output.
- The JSON shape (`schema_version`, `module`, `summary`, `results[]` with `file/line/column/check/status/message`) is consumed by the VSCode and Neovim integrations and by `web/ft_moulinette_web/static/app.js` — don't change it without updating them.

User-facing messages, diagnostics, and docs are written in French; keep that convention.
