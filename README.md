# rep

Calisthenics challenges through the day. About once an hour `rep` shows you one set to do:
a hard set that builds muscle, or short practice for a skill like the handstand or the one-arm
pull-up. You answer from the notification, and your targets move with you.

- **Hard sets and skill practice.** Hard sets go close to failure and count against weekly caps
  per muscle group (push, pull, legs, core). Skill practice stays fresh and never counts.
- **Ladders instead of more weight.** Each movement climbs a ladder of harder variations:
  pull-ups go chest-to-bar → explosive → archer → typewriter; push-ups go clap → archer →
  pseudo-planche → one-arm. Reaching the top of a rung unlocks the next one.
- **Answers that steer progression.** Done / Skip / Later, then "how many reps were left?",
  with the reps you actually did if they differ from the target. The next target starts from what
  you did: easy raises it, three steady sets in a row raise it, failure keeps it.
- **Your training days count.** Describe your split once (`push: chest, shoulders, triceps`…),
  log a day with `rep session push`, and that day's challenges skip those muscle groups, count
  towards the weekly caps and lean towards skill practice.
- **Max test.** A guided test places every ladder at the hardest movement you can do for real and
  sets targets from your numbers. A reminder comes every 6 weeks.
- **Weekly boss challenge**, protein check-in, bedtime reminder and a daily summary with streaks.
- **Waits when you're busy:** a call or recording using the mic, screen sharing, or any pause file
  you name (e.g. a focus timer or the lock screen). In a meeting, tap **Meeting** on a card or run
  `rep pause [minutes]`: nothing is sent until it's over, then the card comes back.
- **Works on any Linux desktop:** standard notifications with buttons, a
  [Quickshell](https://quickshell.org) flyout when available, or the terminal.
- **On your phone too (optional):** free Cloudflare Workers run the schedule and send every
  card to Telegram, whether your desktop is on, off or locked, while your desktop keeps showing them.

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
| `rep pause [MINUTES]` | nothing for 60 minutes (or MINUTES, up to a day); `rep pause 0` resumes |
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
| `rep sync-upload` | copy this computer's history, targets and ladders to the cloud (once, see below) |

### Shell completion

Each file below asks the installed `rep` for its script the first time you complete `rep` in a
shell, so completions follow updates on their own.

```sh
# zsh: a folder on your fpath (add it before compinit in ~/.zshrc if it isn't)
mkdir -p ~/.local/share/zsh/site-functions
printf '#compdef rep\neval "$(rep completion zsh)"\n' > ~/.local/share/zsh/site-functions/_rep

# bash
mkdir -p ~/.local/share/bash-completion/completions
echo 'eval "$(rep completion bash)"' > ~/.local/share/bash-completion/completions/rep

# fish
echo 'rep completion fish | source' > ~/.config/fish/completions/rep.fish
```

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
| `[sync]` | `url` and `token` of your cloud Worker; empty keeps everything on this computer |

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
challenge) and `events.jsonl` (every set, skip, session and max test). Nothing leaves your computer
unless you set up the cloud below.

## Phone and cloud (optional)

Two Cloudflare Workers (free plan) become the one place that decides when a card is due and keeps
your history. They send each card to a Telegram bot, so cards reach your phone with your desktop
off. Your desktop's `rep tick` keeps running: it sends your config, shows the same cards in your
flyout, and forwards your answers. The desktop's busy checks (mic, screen share, pause files) only
apply without the cloud: with it, a locked or busy desktop never holds your phone back, and you
pause by hand with **Meeting**, `/pause` or `rep pause`. Answer
wherever you are: the other side catches up within one tick.

In Telegram, tap the buttons as usual. While a set waits for its rating, send the reps you did as a
number before tapping how it felt. The bot also takes `/now` (a challenge right away), `/session`
(log a training day from buttons, or `/session chest-day`), `/today`, `/stats`, `/routine`,
`/summary`, `/test` (the max test, one question at a time; `/skip` and `/cancel` work during it),
`/pause` (nothing for 60 minutes, `/pause 90` for longer, `/pause 0` to resume) and `/help`. Export and import stay on the desktop.

You need [uv](https://docs.astral.sh/uv/), Node.js, `rsync` and a free Cloudflare account.

1. In Telegram, talk to [@BotFather](https://t.me/BotFather), send `/newbot` and keep the token.
2. Make two random secrets, one for your desktop and one for Telegram: `openssl rand -hex 32` twice.
3. Deploy the two Workers (the Python one holding your data first) and give them the secrets:

   ```sh
   cd worker
   uv sync
   uv run pywrangler login
   uv run pywrangler deploy
   uv run pywrangler secret put TELEGRAM_TOKEN
   cd ../front
   npx wrangler deploy
   npx wrangler secret put DESKTOP_TOKEN
   npx wrangler secret put TELEGRAM_WEBHOOK_SECRET
   npx wrangler secret put TELEGRAM_CHAT_ID
   ```

   The second `deploy` prints the address, `https://rep-api.<your-subdomain>.workers.dev`.
4. Point the bot at it:

   ```sh
   curl https://api.telegram.org/bot<TELEGRAM_TOKEN>/setWebhook \
     -d url=https://rep-api.<your-subdomain>.workers.dev/telegram -d secret_token=<TELEGRAM_WEBHOOK_SECRET>
   ```

5. Send your bot any message. It answers with your chat id; store it on both Workers and only that
   chat is listened to from then on: `uv run pywrangler secret put TELEGRAM_CHAT_ID` in `worker/`
   and `npx wrangler secret put TELEGRAM_CHAT_ID` in `front/`. To show the commands in Telegram's
   menu:

   ```sh
   curl https://api.telegram.org/bot<TELEGRAM_TOKEN>/setMyCommands -H 'Content-Type: application/json' -d '{"commands": [
     {"command": "now", "description": "a challenge right now"},
     {"command": "session", "description": "log a training day"},
     {"command": "today", "description": "today's sets, streak and skills"},
     {"command": "stats", "description": "targets, ladders and the week's caps"},
     {"command": "routine", "description": "your training days"},
     {"command": "summary", "description": "today's summary"},
     {"command": "test", "description": "the max test, one question at a time"},
     {"command": "pause", "description": "no challenges for an hour (or /pause 90)"},
     {"command": "help", "description": "what the bot can do"}]}'
   ```
6. On your desktop, add to `~/.config/rep/config.toml`:

   ```toml
   [sync]
   url = "https://rep-api.<your-subdomain>.workers.dev"
   token = "<DESKTOP_TOKEN>"
   ```

   then run `rep tick` once and `rep sync-upload` once to copy your history, targets and ladders.

The Worker ticks every 3 minutes and reads only the last week of sets plus your max tests, so it
stays inside the free plan's CPU budget as your history grows. Cloudflare's dashboard shows the CPU
time of each run under Workers → rep → Metrics.

## Development

```sh
PYTHONPATH=src python3 -m unittest discover -s tests -t .
```

See `CLAUDE.md` for the code style contract and the rules around state and re-runs.

## License

MIT
