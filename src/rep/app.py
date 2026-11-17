import datetime
import secrets

from rep.catalog import SKILL_GROUP, format_amount, skill_progress
from rep.conditions import busy_reason
from rep.config import level_scale, protein_range_grams
from rep.lines import line_for
from rep.notifiers import Button, Card
from rep.progression import (KIND_BOSS, KIND_HARD, KIND_SKILL, RATING_EASY, RATING_FAILURE, RATING_STEADY,
                             apply_rating, cap_usage, choose_challenge, streak_from_counts, target_of)
from rep.routine import describe_sessions, session_allowances
from rep.scheduler import (ACTION_CHALLENGE, ACTION_NUDGE, ACTION_REMIND, ACTION_RETEST, ACTION_SCHEDULE_FIRST,
                           ACTION_SUMMARY, STAMP_RETEST, STAMP_SUMMARY, decide)
from rep.maxtest import apply_results
from rep.store import EVENT_SESSION, EVENT_SET, EVENT_SKIP, EVENT_TEST, EventLog, new_event

SECONDS_PER_MINUTE = 60
TOKEN_BYTES = 4
STAGE_ASK = "ask"
STAGE_RATE = "rate"
ANSWER_DONE = "done"
ANSWER_SKIP = "skip"
ANSWER_LATER = "later"
ANSWERS = (ANSWER_DONE, ANSWER_SKIP, ANSWER_LATER)
GLYPH_CHECK = 0xF012C
GLYPH_CLOSE = 0xF0156
GLYPH_CLOCK = 0xF0150
GLYPH_PAUSE = 0xF03E4
MEETING_PAUSE_MINUTES = 60
MAXIMUM_PAUSE_MINUTES = 24 * 60
PAUSE_MINUTES_RANGE = range(MAXIMUM_PAUSE_MINUTES + 1)
PAUSE_TIME_FORMAT = "%H:%M"
GLYPH_ARROW_UP = 0xF0737
GLYPH_FIRE = 0xF0238
GLYPH_TROPHY = 0xF0538
RATING_LABELS = {
    KIND_HARD: (("3+ left", RATING_EASY), ("1–2 left", RATING_STEADY), ("Failure", RATING_FAILURE)),
    KIND_SKILL: (("Easy", RATING_EASY), ("Okay", RATING_STEADY), ("Tough", RATING_FAILURE)),
    KIND_BOSS: (("Beat my best", RATING_EASY), ("Matched it", RATING_STEADY), ("Below", RATING_FAILURE)),
}
RATING_GLYPHS = (GLYPH_ARROW_UP, GLYPH_CHECK, GLYPH_FIRE)


class App:
    def __init__(self, store, config, pack, notifier, chooser, clock=datetime.datetime.now, busy_check=None):
        self.store, self.config, self.pack = store, config, pack
        self.notifier, self.chooser, self.clock = notifier, chooser, clock
        self.busy_check = busy_check or (lambda: busy_reason(config["conditions"]))
        self.state = store.load_state()
        self.events = EventLog(store.load_events)
        self.scale = level_scale(config)
        config["training"]["session_allowances"] = session_allowances(config["training"], pack)

    def save(self):
        self.store.save_state(self.state)

    def record(self, event_type, **fields):
        event = self.store.append_event(new_event(event_type, now=self.clock(), **fields))
        self.events.append(event)

        return event

    def streak(self, today):
        return streak_from_counts(self.store.completed_counts(), today, self.config["training"]["streak_minimum"])

    def amount(self, exercise_identifier):
        exercise = self.pack.exercises[exercise_identifier]

        return format_amount(exercise, target_of(self.state, self.pack, exercise_identifier, self.scale))

    def line(self, kind):
        return line_for(kind, self.pack, self.config["display"], self.chooser)

    def next_gap_seconds(self):
        schedule = self.config["schedule"]
        minutes = self.chooser.randint(schedule["minimum_gap_minutes"], schedule["maximum_gap_minutes"])

        return minutes * SECONDS_PER_MINUTE

    def stamp(self, name):
        self.state["stamps"][name] = self.clock().date().isoformat()

    def tick(self):
        now = self.clock()
        reason = self.busy_check()
        decision = decide(now, self.state, self.config, self.pack, self.events, reason, self.chooser)

        if decision is None:
            return reason or "nothing due"

        if decision.action == ACTION_NUDGE:
            self.stamp(decision.detail)
            self.save()
            self.show_nudge(decision.detail)
        elif decision.action == ACTION_SUMMARY:
            self.stamp(STAMP_SUMMARY)
            self.save()
            self.notifier.show(Card(*self.summary_lines()))
        elif decision.action == ACTION_RETEST:
            self.stamp(STAMP_RETEST)
            self.save()
            self.show_retest()
        elif decision.action == ACTION_SCHEDULE_FIRST:
            first_minutes = self.chooser.randint(*self.config["schedule"]["first_challenge_minutes"])
            self.state["next_due"] = now.timestamp() + first_minutes * SECONDS_PER_MINUTE
            self.save()
        elif decision.action == ACTION_REMIND:
            self.show_pending()
        elif decision.action == ACTION_CHALLENGE:
            self.start_challenge(decision.detail)

        return decision.action

    def now(self):
        if self.state.get("pending"):
            self.show_pending()

            return "shown again"

        challenge = choose_challenge(self.state, self.pack, self.config["training"], self.config["profile"]["skills"],
                                     self.events, self.clock(), self.chooser)

        if challenge is None:
            return "Nothing to offer: every weekly cap is full and no skills are chosen."

        self.start_challenge(challenge)

        return "shown"

    def start_challenge(self, challenge):
        self.state["pending"] = {
            "token": secrets.token_hex(TOKEN_BYTES),
            "kind": challenge.kind,
            "group": challenge.group,
            "ladder": challenge.ladder_identifier,
            "exercise": challenge.exercise_identifier,
            "stage": STAGE_ASK,
            "shown_at": 0,
        }
        self.show_pending()

    def show_pending(self):
        pending = self.state["pending"]
        pending["shown_at"] = self.clock().timestamp()
        self.save()

        if pending["stage"] == STAGE_RATE:
            self.show_rating(pending)

            return

        exercise = self.pack.exercises[pending["exercise"]]

        if pending["kind"] == KIND_BOSS:
            best = self.state["best"].get(pending["exercise"])
            title = f"Boss: {exercise.name}" + (f" · beat {best}" if best else "")
            line = self.line("boss")
        elif pending["kind"] == KIND_SKILL:
            skill = self.pack.skills[pending["ladder"]]
            title = f"Skill · {exercise.name}: {self.amount(exercise.identifier)}"
            line = f"{skill_progress(self.pack, skill, exercise.identifier)}. Stay fresh, stop well before failure."
        else:
            title = f"{exercise.name}: {self.amount(exercise.identifier)}"
            line = self.line("challenge")

        buttons = (Button("Done", GLYPH_CHECK, ("answer", pending["token"], ANSWER_DONE)),
                   Button("Skip", GLYPH_CLOSE, ("answer", pending["token"], ANSWER_SKIP)),
                   Button("Later", GLYPH_CLOCK, ("answer", pending["token"], ANSWER_LATER)),
                   Button("Meeting", GLYPH_PAUSE, ("pause", str(MEETING_PAUSE_MINUTES))))
        self.notifier.show(Card(title, " · ".join(part for part in (line, exercise.cue) if part), True, buttons))

    def show_rating(self, pending):
        exercise = self.pack.exercises[pending["exercise"]]
        buttons = tuple(Button(label, glyph, ("rate", pending["token"], str(rating)))
                        for (label, rating), glyph in zip(RATING_LABELS[pending["kind"]], RATING_GLYPHS))
        target = target_of(self.state, self.pack, exercise.identifier, self.scale)
        self.notifier.show(Card("How many reps were left?", f"{exercise.name} · {self.amount(exercise.identifier)}",
                                True, buttons, done_prompt=target))

    def matching_pending(self, token, stage):
        pending = self.state.get("pending")

        if not pending or pending["token"] != token or pending["stage"] != stage:
            return None

        return pending

    def answer(self, token, answer):
        pending = self.matching_pending(token, STAGE_ASK)

        if pending is None or answer not in ANSWERS:
            return "ignored: that challenge was already answered"

        now = self.clock().timestamp()

        if answer == ANSWER_DONE:
            pending["stage"] = STAGE_RATE
            self.show_pending()
        elif answer == ANSWER_LATER:
            pending["shown_at"] = 0
            self.state["next_due"] = now + self.config["schedule"]["snooze_minutes"] * SECONDS_PER_MINUTE
            self.save()
        else:
            self.record(EVENT_SKIP, kind=pending["kind"], group=pending["group"], ladder=pending["ladder"],
                        exercise=pending["exercise"], amount=self.amount(pending["exercise"]))
            self.state["pending"] = None
            self.state["next_due"] = now + self.next_gap_seconds()
            self.save()

        return answer

    def pause(self, minutes):
        if minutes not in PAUSE_MINUTES_RANGE:
            return f"ignored: pause for at most {MAXIMUM_PAUSE_MINUTES} minutes"

        resume_at = self.clock() + datetime.timedelta(minutes=minutes)
        self.state["paused_until"] = resume_at.timestamp()
        self.save()

        return f"Paused until {resume_at.strftime(PAUSE_TIME_FORMAT)}."

    def rate(self, token, rating, done=None):
        pending = self.matching_pending(token, STAGE_RATE)

        if pending is None:
            return "ignored: that challenge was already rated"

        exercise_identifier = pending["exercise"]
        done = pending.get("typed") if done is None else done
        target_before = target_of(self.state, self.pack, exercise_identifier, self.scale)
        unlocked = apply_rating(self.state, self.pack, exercise_identifier, rating, self.scale, done)
        amount = target_before if done is None else done

        if pending["kind"] == KIND_BOSS and rating >= RATING_EASY:
            self.state["best"][exercise_identifier] = amount

        if pending["kind"] != KIND_SKILL:
            self.state["last_group"] = pending["group"]

        self.state["pending"] = None
        self.state["next_due"] = self.clock().timestamp() + self.next_gap_seconds()
        self.save()
        self.record(EVENT_SET, kind=pending["kind"], group=pending["group"], ladder=pending["ladder"],
                    exercise=exercise_identifier, amount=amount, rating=rating)
        self.show_result(exercise_identifier, unlocked)

        return "rated"

    def show_result(self, exercise_identifier, unlocked):
        today = self.clock().date()
        done_today = sum(1 for event in self.events if event["type"] == EVENT_SET and event["day"] == today.isoformat())
        streak = self.streak(today)
        body = f"{done_today} today · streak {streak} d · next time {self.amount(exercise_identifier)}"

        if unlocked:
            title = f"{self.line('level_up')} Next: {self.pack.exercises[unlocked].name} ({self.amount(unlocked)})"
        else:
            title = self.line("done") or "Nice set."

        self.notifier.show(Card(title.strip(), body))

    def log_session(self, session):
        allowances = self.config["training"]["session_allowances"]

        if session not in allowances:
            return f"unknown session {session!r}: use {', '.join(allowances)}"

        self.record(EVENT_SESSION, session=session)
        groups = ", ".join(allowances[session])
        self.notifier.show(Card(f"Logged: {session} session", f"Today's challenges skip {groups}."))

        return "logged"

    def show_nudge(self, kind):
        if kind == "protein":
            low, high = protein_range_grams(self.config)
            self.notifier.show(Card(self.line("protein") or "Protein check", f"Target today: about {low}-{high} g."))
        else:
            self.notifier.show(Card(self.line("bedtime") or "Bedtime soon", "Muscle grows while you sleep."))

    def show_retest(self):
        buttons = (Button("Run test", GLYPH_TROPHY, ("test-window",)), Button("Not today", GLYPH_CLOSE, ("dismiss",)))
        self.notifier.show(Card("Time for a max test", "About 15 minutes to set your targets from real numbers.",
                                True, buttons))

    def apply_test(self, results, skill_steps):
        apply_results(self.state, self.pack, results, skill_steps)
        self.state["last_test_day"] = self.clock().date().isoformat()
        self.save()
        self.record(EVENT_TEST, results=results, skill_steps=skill_steps)

        return "Targets set."

    def today(self):
        today = self.clock().date().isoformat()
        sessions = [event["session"] for event in self.events if event["type"] == EVENT_SESSION and event["day"] == today]

        return {
            "done": sum(1 for event in self.events if event["type"] == EVENT_SET and event["day"] == today),
            "streak": self.streak(self.clock().date()),
            "trained": sessions,
            "sessions": describe_sessions(self.config["training"], self.config["training"]["session_allowances"]),
            "skills": {self.pack.skills[skill].title: self.pack.exercises[self.current_skill_step(skill)].name
                       for skill in self.config["profile"]["skills"] if skill in self.pack.skills},
        }

    def current_skill_step(self, skill):
        ladder = self.pack.skills[skill]
        rung = min(self.state["rungs"].get(skill, 0), len(ladder.exercise_identifiers) - 1)

        return ladder.exercise_identifiers[rung]

    def summary_lines(self):
        today = self.clock().date()
        sets = [event for event in self.events if event["type"] == EVENT_SET and event["day"] == today.isoformat()]
        usage = cap_usage(self.events, self.pack.groups, self.config["training"]["session_allowances"], today)
        caps = self.config["training"]["weekly_caps"]
        week = ", ".join(f"{group} {usage[group]}/{caps.get(group, 0)}" for group in self.pack.groups)

        if not sets:
            return "No challenges today", f"Week: {week}"

        per_group = {}

        for event in sets:
            label = "skills" if event["group"] == SKILL_GROUP else event["group"]
            per_group[label] = per_group.get(label, 0) + 1

        streak = self.streak(today)
        groups_text = ", ".join(f"{group} {count}" for group, count in per_group.items())

        return f"Today: {len(sets)} challenges · streak {streak} d", f"{groups_text} · week: {week}"
