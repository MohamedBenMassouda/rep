# rep

Calisthenics challenges through the day. About once an hour `rep` shows you one set to do:
a hard set that builds muscle, or short practice for a skill like the handstand or the one-arm
pull-up. You answer from the notification, and your targets move with you.

- **Hard sets and skill practice.** Hard sets go close to failure and count against weekly caps
  per muscle group (push, pull, legs, core). Skill practice stays fresh and never counts.
- **Ladders instead of more weight.** Each movement climbs a ladder of harder variations:
  pull-ups go chest-to-bar → explosive → archer → typewriter; push-ups go clap → archer →
  pseudo-planche → one-arm. Reaching the top of a rung unlocks the next one.
- **Answers that steer progression.** Done / Skip / Later, then "how many reps were left?":
  3+ left raises the target, three steady sets in a row raise it, failure keeps it.
- **Your training days count.** Describe your split once (`push: chest, shoulders, triceps`…),
  log a day with `rep session push`, and that day's challenges skip those muscle groups, count
  towards the weekly caps and lean towards skill practice.
- **Max test.** A guided test places every ladder at the hardest movement you can do for real and
  sets targets from your numbers. A reminder comes every 6 weeks.
- **Weekly boss challenge**, protein check-in, bedtime reminder and a daily summary with streaks.
- **Waits when you're busy:** a call or recording using the mic, screen sharing, or any pause file
  you name (e.g. a focus timer or the lock screen).
- **Works on any Linux desktop:** standard notifications with buttons, a
  [Quickshell](https://quickshell.org) flyout when available, or the terminal.

## Install

```sh
uv tool install git+https://github.com/MohamedBenMassouda/rep   # or: pipx install …
rep init            # asks for your body weight, level, skills, hours; saved locally only
rep test            # 15-minute max test that sets your targets
rep install-timer   # systemd user timer: checks every 3 minutes whether something is due
```

Python 3.11+, no dependencies. Buttons on desktop notifications need `notify-send` (libnotify)
and a notification daemon that supports actions (dunst, mako, swaync, GNOME, KDE…).

## Commands

| Command | Does |
|---|---|
| `rep now` | a challenge right now |
| `rep session DAY` | log one of your training days today (`upper`, `legs`, `full` without a routine) |
| `rep routine [--names]` | your training days, their muscles and what they count as |
| `rep stats [--history]` | targets, ladders, weekly caps; `--history` adds progress charts and compares max tests |
| `rep test` / `rep test-window` | max test (in this terminal / in a new one) |
| `rep today` | today's numbers as JSON, for widgets |
| `rep summary` | show today's summary |
| `rep export [--format json\|csv] [--output FILE]` | export your history |
| `rep import FILE [--with-state]` | import a JSON export; events are merged, never duplicated |
| `rep pack export` | copy the exercise pack to your config folder to edit or extend |
| `rep install-timer` / `rep uninstall-timer` | the systemd user timer |
| `rep completion zsh\|bash\|fish` | print a shell completion script |

### Shell completion

```sh
# zsh: a folder on your fpath (add it before compinit in ~/.zshrc if it isn't)
mkdir -p ~/.local/share/zsh/site-functions
rep completion zsh > ~/.local/share/zsh/site-functions/_rep
# or, simpler but slower to start: eval "$(rep completion zsh)" after compinit

# bash
mkdir -p ~/.local/share/bash-completion/completions
rep completion bash > ~/.local/share/bash-completion/completions/rep

# fish
rep completion fish > ~/.config/fish/completions/rep.fish
```

Re-run it after updating rep so new commands show up.

## Your routine

`rep init` asks for your training days, one per line as `name: muscles`:

```
push: chest, shoulders, triceps
pull: back + biceps + rear delts
legs: legs and core
```

Muscles are joined with `,`, `+` or `and`; spelling is loose (`bicep`, `rear delts`). Each muscle
belongs to one or more groups of the pack (`chest` → push, `rear delts` → pull, `arms` → push
and pull, `legs` and `back` count double). A logged day counts `sets_per_muscle` (3) hard sets
per muscle against those groups' weekly caps and skips them for that day's challenges.
`rep routine` shows what each day counts as. The muscle list lives in the pack under `muscles`.

## Configuration

`~/.config/rep/config.toml` (written by `rep init`; edit freely):

| Section | Settings |
|---|---|
| `[profile]` | `body_weight_kg`, `level` (beginner / intermediate / advanced), `skills` |
| `[schedule]` | `start_hour`, `end_hour`, gap between challenges, `snooze_minutes`, `reminder_minutes` |
| `[training]` | `routine`, `sets_per_muscle`, `weekly_caps`, `session_allowances` (used when there is no routine), skill share on training / rest days, boss settings, `streak_minimum`, `retest_days`, `pack_file` |
| `[nudges]` | `protein`, `bedtime`, `summary` times (`HH:MM` or `off`) |
| `[display]` | `notifier` (auto / quickshell / desktop / terminal), `quickshell_kind`, `line_command` |
| `[conditions]` | `pause_files`, `check_microphone`, `check_screen_share` |

`line_command` lets another program supply the lines on the cards, e.g. a themed set of quips:
`line_command = "my-quips {kind}"` is called with `challenge`, `done`, `level_up`, `boss`,
`protein` or `bedtime`, and its output replaces the pack's line.

### Exercise packs

Exercises, ladders, skills, bosses, the max test and the lines live in a JSON pack
(`src/rep/data/default_pack.json`). `rep pack export` copies it to `~/.config/rep/packs/`; edit it
(add movements, a front-lever skill, your own lines) and point `pack_file` at it. Each exercise
has a `name`, `unit` (`reps`, `reps_per_side`, `seconds`, `tries`), `start`, `step`, `top` (where
its ladder moves on) and a form `cue`.

### Data

State lives in `~/.local/state/rep/`: `state.json` (targets, ladder positions, the pending
challenge) and `events.jsonl` (every set, skip, session and max test). Nothing leaves your computer.

## Development

```sh
PYTHONPATH=src python3 -m unittest discover -s tests -t .
```

See `CLAUDE.md` for the code style contract and the rules around state and re-runs.

## License

MIT
