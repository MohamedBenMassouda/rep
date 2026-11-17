# CLAUDE.md

rep is a command-line calisthenics trainer for one person on a Linux desktop. A systemd user timer
runs `rep tick` every 3 minutes. The tick decides whether something is due and what: a challenge
(a hard set counted against weekly per-group caps, skill practice, or a weekly boss), a nudge
(protein, bedtime), the daily summary or a retest reminder. The user answers from a notification
card, and its buttons call `rep answer` / `rep rate` back with a challenge token. Moving parts:
an exercise pack (JSON), a TOML config, `state.json` + `events.jsonl` in `~/.local/state/rep`,
and pluggable notifiers (Quickshell flyout over IPC, desktop notifications via `notify-send`, terminal).
Optionally two Cloudflare Workers take over deciding: `front/` (JavaScript, `rep-api`) owns the cron
and the public routes, and `worker/` (Python, `rep`) holds the Durable Object that keeps state in a
Durable Object's SQLite, and the desktop syncs with it (see "Cloud sync").

One Python package, `src/rep`, stdlib only (Python 3.11+, `tomllib`), built with hatchling and
installed with `uv tool install` or `pipx`. Tests are in `tests/` (`unittest`). There is no
root-level tooling beyond `pyproject.toml`. `worker/` is the Python Worker (`pyproject.toml` for
pywrangler, `wrangler.jsonc`, `src/entry.py`); its build step rsyncs `src/rep` into `worker/src/rep`
(gitignored), so `src/rep` stays the only copy of the code. `front/` is about forty lines of
JavaScript with no package.json: it checks secrets and forwards to the Durable Object's RPC
methods, nothing else. Python Workers cost 5 to 20 ms of CPU per request just to start handling it,
over the free plan's 10 ms, which is the only reason the front is JavaScript.
`main` is the only long-lived branch. Nothing deploys: users install from git.

## Commands

From the repository root:

| Command                                                      | Does                                                          |
| ------------------------------------------------------------ | ------------------------------------------------------------- |
| `PYTHONPATH=src python3 -m unittest discover -s tests -t .`  | the gate. Run it before declaring work done                   |
| `PYTHONPATH=src python3 -m unittest tests.test_app`          | one suite while iterating                                     |
| `XDG_CONFIG_HOME=<scratch>/config XDG_STATE_HOME=<scratch>/state PYTHONPATH=src python3 -m rep …` | the whole tool against throwaway config and state (`init`, `test`, `now`, `answer`, `rate`, `stats --history`, `export`, `import`). Set `notifier = "terminal"` so cards print |
| `uv tool install --force .`                                  | install the working copy as `rep`                             |
| `rep now`                                                    | manual smoke rig. Shows a **real** card on your desktop and writes **real** state, never in CI |
| `cd worker && uv run pywrangler sync && npx wrangler dev -c ../front/wrangler.jsonc -c wrangler.jsonc --test-scheduled` | both Workers locally (secrets from `front/.dev.vars`); `curl "localhost:8787/cdn-cgi/handler/scheduled"` runs a tick |

CI (`.github/workflows/tests.yml`) runs the unittest suite on Python 3.11, 3.12, 3.13 and 3.14.
That job is the only check. Nothing lints or type-checks: hold the code style below yourself.

Branches are `<topic>/<short-slug>` when not working on `main`. There is no PR template. Commits
are small conventional commits (`feat(scheduler): …`, `fix(app): …`, `test: …`) with no AI
co-author or attribution.

## Code style: the contract

Non-negotiable, and they apply to every language in this repo. Treat a violation as a bug.

**1. No magic values.** Every literal, number or string, is a named constant whose name
explains it. No exceptions for "obvious" values. Retry limits, thresholds, page sizes and
timeouts are named fields on the type that owns them. Enum-like sets are real enums, never a
bare string compared inline.
Existing examples: `STEADY_ANSWERS_TO_ADVANCE`, `RATING_EASY`, `STRENGTH_TARGET_SHARE`,
`COMMAND_TIMEOUT_SECONDS`, `EVENT_SET`. Enum-like sets are module constants (`KIND_HARD`,
`ACTION_REMIND`, …); moving them to `enum.Enum` is welcome when you touch them.

**2. No comments.** Names carry the meaning. If a block needs a comment, it needs a better
name or its own function. This covers doc-comment blocks and banner separators
(`// ===== SECTION =====`) too: a file that needs section headers needs splitting.
No source file carries comments or docstrings today. Do not add more, and do not cite an
existing comment as precedent. Where a
comment records a real constraint (a vendor quirk, or a production incident the obvious change
would bring back), move it into this file or into `README.md` and delete it from the
source. Never leave commented-out code. Git remembers it.

**3. Self-explanatory names.** No abbreviations: `DrainNextPage`, not `DrainNext`. When two
kinds of id are in scope, disambiguate them (`parentId` vs `childId`, `jobRunId` vs
`dataRunId`). Loop variables get real names. Vendor and domain acronyms that are a proper
name stay (JSON, TOML, CSV, IPC, XDG).
Python conventions: `snake_case` for functions and variables, `UPPER_SNAKE` for module
constants, `PascalCase` for classes and dataclasses, one module per concern under `src/rep/`.

**4. Blank line before and after control-flow keywords:** `if`, `else`, `for`, `foreach`,
`while`, `return`, `throw`, `switch`, `try`. A block owns its braces, so **never** put a blank
line directly after an opening brace or a `case` label, and **never** put one directly before
a closing brace.

In Python the line ending in `:` is the opening brace, and the end of the indented block is the
closing brace. `src/rep/progression.py`:

```python
def streak_days(events, today, minimum):
    counts = completed_per_day(events)
    checked_day = today

    if counts.get(checked_day.isoformat(), 0) < minimum:
        checked_day -= datetime.timedelta(days=1)

    streak = 0

    while counts.get(checked_day.isoformat(), 0) >= minimum:
        streak += 1
        checked_day -= datetime.timedelta(days=1)

    return streak
```

Nothing enforces rule 4 mechanically. Follow it by hand, everywhere in the repo.

**5. DRY.** Shared behaviour goes in `src/rep`: pure helpers in `progression.py`,
`scheduler.py` and `catalog.py`, and anything touching the outside world (files, subprocesses,
the desktop) in `store.py`, `conditions.py`, `timer.py` and `notifiers/`, with each notifier
exposing `show(card)`. Desktop-specific code stays in `src/rep/notifiers/<backend>.py`. Check
`progression.py` and `catalog.py` before writing a helper.

## Scheduling and progression contract

- **`scheduler.decide()`** is pure: given `now`, state, config, pack, events, the busy reason
  and a random source, it returns a `Decision` and changes nothing. Order: nudges (protein,
  bedtime), summary, then outside active hours nothing, retest reminder, first-run scheduling,
  "not due or busy", remind the pending card after `reminder_minutes`, else a new challenge.
- **`progression`** is pure too: `apply_rating()` (3+ left raises the target, three steady sets
  in a row raise it, failure resets the run, reaching `top` moves the ladder), `cap_usage()`,
  `choose_challenge()`, `streak_days()`.
- **`app.App`** is the only place that reads and writes state, appends events and shows cards.
  The CLI (`cli.py`) only parses arguments and calls `App`.
- New behaviour goes in a pure function first, tested directly, and is wired through `App` after.
- New exercises and skills go in the pack JSON, not in code. A pack is validated on load
  (`catalog.validate_references`). Keep that passing.

### Durable state and re-runs

**Every step is a resume.** Each `rep` invocation is a new process: it loads `state.json` and
`events.jsonl`, acts, and writes back. The timer re-triggers `tick` every 3 minutes, and
notification buttons can fire twice or hours late. Every handler must be idempotent and safe to
re-run after a kill at any step boundary. Anything that must survive the step is persisted
before you return.

**Every write to persisted state is an upsert.** A handler killed after its write but before
its state transition runs again from the top:

- Use indexer or set semantics (`map[key] = value`), not `Add`, which throws or duplicates on
  a re-run. When the first value must win on purpose, say so with `TryAdd`. Never wrap `Add`
  in a `ContainsKey` guard.
- Check for existing children before fanning out, unless the creation call is itself
  idempotent.
- Never append to a list stored in persisted state (read, append, write). Derive the list from
  a count, or use a set.
- Never persist a running total accumulated across steps. Store absolute values.
  Reference implementation: `cap_usage()`, `streak_days()` and `maxtest.test_history()` derive
  everything from `events.jsonl`. `targets` and `rungs` hold absolute values. `events.jsonl` is
  the one append-only store: every event has a unique `id`, and `backup.import_backup()` merges
  by `id`, so a re-import adds nothing.

### Runtime-only contracts

- **Challenge tokens.** A card's buttons carry `pending["token"]`. `answer` and `rate` act
  only when the token and `pending["stage"]` (`ask` / `rate`) match, and otherwise return
  "ignored". Never act on an answer without that check.
- **Exercise identifiers are data.** They are stored in `targets`, `steady_answers`, `rungs`,
  `best`, `pending` and every event. Renaming one in a pack orphans its history; migrate the
  state and events in the same change.
- **The button argv is an interface.** Notifiers run `rep answer <token> done|skip|later`,
  `rep rate <token> 3|1|0 [reps done]`, `rep test-window` and `rep dismiss`. The desktop notifier re-enters
  through the hidden `rep await-notification <json>`.
- **`rep today` output is read by widgets.** The keys are `done`, `streak`, `trained`,
  `sessions` (day name → muscles text) and `skills`. The `rep` script enters through
  `rep.launcher`: with sync on, `rep today` prints the `today.json` that every sync writes, after
  importing only `rep.config` and `rep.paths`. Keep the launcher's imports that small.
- **Session names are data too.** They come from `[training] routine` (else
  `session_allowances`), are stored in `session` events, and `rep routine --names` feeds shell
  completion for `rep session`. `App` replaces `session_allowances` with the routine's on load
  (`routine.session_allowances()`), so everything downstream reads one table.
- **Line kinds** passed to `line_command` and looked up in packs: `challenge`, `done`,
  `level_up`, `boss`, `protein`, `bedtime`.
- **Event types:** `set`, `skip`, `session`, `test`. Counting code filters on `type`.
- **`App` takes a store** (`FileStore`, `MemoryStore`, or the cloud's `SqlStore`) and a `busy_check`.
  `App.events` is a lazy `EventLog`: a tick with nothing due must not read the history. The last
  max-test day is kept in `state["last_test_day"]` for the same reason.

### Cloud sync

- With `[sync] url` set, the Worker is the only thing that decides. The desktop never runs
  `decide()`: `rep tick` posts its config, pack, timezone and busy reason to `/desktop/sync` and
  shows the cards the Worker produced since its cursor (skipping ones older than
  `CARD_FRESH_SECONDS`). Commands that change state are forwarded to `/desktop/command`. `today`
  reads the cached `today.json`, `routine` needs only the config, and `stats` and `export` run on a
  `MemoryStore` built from `/desktop/export`.
- `rep.cloud.Brain` is plain Python over an `execute(sql, *parameters)` function, tested on
  `sqlite3`. `worker/src/entry.py` only adapts it to the Durable Object, and `front/src/index.js`
  only routes. Keep logic out of both: it belongs in `src/rep`, where it is tested.
- **The cloud reads only the last `RECENT_HISTORY_DAYS` of events plus every `test` event.** The
  free plan allows 10 ms of CPU per run. Anything the cloud needs from older history goes through
  a store query (the streak uses `completed_counts()`, a `GROUP BY day`), never a full load.
- `SqlStore` caches settings in memory, skips writes of unchanged values, and the Durable Object
  keeps one store for its lifetime (it is the only writer). Every query in it uses an index or
  the primary key: check `EXPLAIN QUERY PLAN` when adding one. A desktop command carries its sync
  report, so it is one round trip.
- The desktop sends the 20 KB pack only when its digest changed; a cloud whose digest differs
  answers `needs_pack` before running anything, so the resend never runs a command twice.
  `today` is cached under a marker of the state, config, date and `MAX(rowid)` of events; never
  use `COUNT(*)` for such checks (Durable Objects bill rows read).
- `rep-api` holds the one secret, `DESKTOP_TOKEN`; the Python Worker has no public URL
  (`workers_dev: false`) and is reached only through the Durable Object binding. The desktop's
  `[sync]` section never leaves the desktop.

### Results, retries, errors

No retries. Subprocess calls (`qs`, `notify-send`, `pactl`, `pw-dump`, `systemctl`, the line
command) use `COMMAND_TIMEOUT_SECONDS`, and failures degrade quietly. A failed busy check counts
as "not busy". A lost card comes back through the reminder path because `pending` is persisted.
User mistakes (no config, a broken pack) exit with `EXIT_PROBLEM` and one readable line.

## Testing

`unittest` from the standard library, in `tests/` (`test_progression.py`, `test_scheduler.py`,
`test_app.py`, `test_maxtest.py`, `test_backup.py`, `test_cloud.py`, `test_sync.py`). Shared fixtures
are in `tests/helpers.py`, including `sqlite_execute()` for the cloud store.

- **No network, no secret store, no real vendor API from the test suite.** Fake HTTP at the
  transport layer (there is no HTTP here; tests turn the busy checks off in config and pass a
  recording notifier instead of touching the desktop) so production code needs no test hooks.
- Fixtures live in `tests/helpers.py`. Doubles and spies live in the test modules
  (`RecordingNotifier` in `tests/test_app.py`). Reuse them before writing new ones.
- Test display names are sentences about behaviour, not restatements of the method name:
  `def test_an_unanswered_card_is_not_sent_again_before_the_reminder_interval(self)`,
  with a matching `Method_DoesTheThing` name (in Python the method name is the sentence).
- New tests go under `tests/test_<module>.py`. There are no debt directories.
- Manual rigs that touch real secrets or APIs are not tests. Keep them out of CI and never
  let anything in CI depend on them.
- To test the workflow end to end, build a fresh `App` from the same `Paths` between steps
  (`test_the_state_survives_a_restart_between_the_two_answer_steps`): that is a kill/resume.
  Pin time with `clock=lambda: FIXED_NOW` and randomness with `seeded_random()`.

## Gotchas

- `busy_reason()` must ignore `.monitor` sources: audio visualisers record the speakers all the
  time. Call apps hold the mic only during calls, so challenges correctly wait.
- `choose_challenge()` reads the hour (boss after `boss_after_hour`) and today's sessions: pin
  the clock in tests or the boss branch fires depending on when they run.
- Desktop notification buttons need a daemon that supports actions and `notify-send --wait`.
  The click is awaited in a detached `rep await-notification` process; if the daemon drops the
  card, the reminder path shows it again.
- `rep_command()` prefers the installed `rep` on `PATH` and falls back to `python -m rep`. A
  card created by a working copy runs the installed one when clicked.
- `tomllib` only reads TOML: `config.to_toml()` writes the flat two-level layout `rep` uses.
  Nested tables beyond one level are written as inline tables.
- zsh users: an unquoted `$var` holding a command is not word-split. Use a shell function in scripts.
- CI only runs the tests: no lint, no type check, no style check.
- pywrangler bundles neither symlinks nor local path dependencies: the Worker's build step rsyncs
  `src/rep` instead. Use `rsync -a`, not `cp`: rewriting the files retriggers the dev watcher and
  rebuilds in a loop.
- In a Python Worker, `sql.exec(...).toArray()` already returns a Python list.
- Cloudflare answers Python's default `Python-urllib` user agent with error 1010 (403). Desktop
  sync requests send `USER_AGENT`; keep it on every request.

## Working style

- Verify a fix by breaking it: revert the change and confirm the test fails. A test that
  passes both ways proves nothing.
- Before you report a regression or a pre-existing bug, check `git show HEAD:<path>` to tell
  which one it is.
- Fix the root cause, not the caller that reported it. One fix in the shared helper is a
  smaller diff than a guard in every caller, and patching one caller leaves the others broken.
- When a shared change breaks tests, fix the tests to match the new truth. Do not weaken
  assertions to make them pass.
- Report what actually happened, including what was skipped and what still needs doing.
