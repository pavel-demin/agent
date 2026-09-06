import re
import sys
import time
from pathlib import Path

from .core import Session, cli_main, is_interrupted, load_config, make_agent

OPEN_BOX_RE = re.compile(r"^\s*- \[ \]", re.MULTILINE)
STALL_LIMIT = 3
SESSIONS_DIR = Path("sessions")
SPEC_NOT_FOUND_MSG = "spec file not found: {path} - write the technical specification there first"


def open_count(todo_path):
    if not todo_path.is_file():
        return 0
    return len(OPEN_BOX_RE.findall(todo_path.read_text(encoding="utf-8")))


def transcript_paths(proj, task):
    return list(SESSIONS_DIR.glob(f"{proj}-{task}-*.json"))


def spec_path(proj, task):
    return Path(proj) / "tasks" / f"{task}-spec.md"


def latest_transcript(proj, task):
    candidates = transcript_paths(proj, task)
    return max(candidates, key=lambda p: p.name) if candidates else None


def is_interrupted_transcript(path):
    sess = Session.load(path)
    if not sess or not sess.messages:
        return False
    return is_interrupted(sess.messages)


def build_plan_file(cfg, proj, task):
    spec = spec_path(proj, task)
    if not spec.is_file():
        return None

    plan = spec.read_text(encoding="utf-8")
    rules = cfg["agent"]["plan_rules"]
    rules = rules.replace("<project_name>", proj).replace("<task_name>", task)

    plan_path = spec.parent / f"{task}-plan.md"
    plan_path.write_text(f"{plan}\n{rules}", encoding="utf-8")
    return plan_path


def build_prompt(cfg, proj, task, todo_path, first, max_tokens):
    verb = "start" if first else "continue"
    limit = int(0.8 * max_tokens)
    parts = [
        f"Please read '{todo_path}' and {verb} working on the tasks from this file.",
        f"Context budget is {max_tokens} tokens. You will be prompted to finish at 80% (about {limit} tokens). Plan accordingly.",
    ]
    rules = cfg["agent"]["work_rules"]
    rules = rules.replace("<project_name>", proj).replace("<task_name>", task)
    parts.append(rules.rstrip("\n"))
    return "\n\n".join(parts)


def run_session(cfg, sess_path, prompt, session=None):
    agent = make_agent(cfg, session=session or Session(), sess_path=sess_path)
    return agent.turn(prompt, sess_path)


def run(cfg_path, proj, task, stall_limit=STALL_LIMIT):
    cfg = load_config(cfg_path)
    tasks_dir = Path(proj) / "tasks"
    todo_path = tasks_dir / f"{task}-todo.md"

    if not build_plan_file(cfg, proj, task):
        print(SPEC_NOT_FOUND_MSG.format(path=spec_path(proj, task)))
        return 2

    sessions_dir = SESSIONS_DIR
    sessions_dir.mkdir(parents=True, exist_ok=True)

    max_tokens = cfg["agent"]["max_tokens"]
    prior_sessions = len(transcript_paths(proj, task))

    resumed_path = None
    latest = latest_transcript(proj, task)
    if latest and is_interrupted_transcript(latest):
        resumed_path = latest
        print(f"  [workflow] resuming an interrupted session ({resumed_path})")
    else:
        print("  [workflow] starting a new session")

    if resumed_path is None and todo_path.is_file() and open_count(todo_path) == 0:
        print("  [workflow] workflow complete")
        return

    prev_count = None
    stall_count = 0
    session_no = prior_sessions
    loaded = None

    while True:
        if resumed_path:
            loaded = Session.load(resumed_path)
            if not loaded:
                print(f"  [workflow] could not load {resumed_path} - starting a new session instead")
                resumed = False
                resumed_path = None
                continue
            resumed = True
            sess_path = resumed_path
            prompt = None
        else:
            session_no += 1
            sess_path = sessions_dir / f"{proj}-{task}-{time.strftime('%Y%m%d-%H%M%S')}.json"
            if not todo_path.is_file():
                prompt = f"Please read '{tasks_dir / f'{task}-plan.md'}' and start preparing a plan (task file) according to the specifications described in this file."
            else:
                first = prior_sessions <= 1 and session_no == 2
                prompt = build_prompt(cfg, proj, task, todo_path, first, max_tokens)
            resumed = False

        _, err = run_session(cfg, sess_path, prompt, session=loaded if resumed else None)
        resumed_path = None

        reason = "completed" if err is None else err
        cur_count = open_count(todo_path)

        print(f"  [workflow] session {session_no} ended: {reason} (open boxes: {cur_count})")

        if not todo_path.is_file():
            print(f"  [workflow] stopped: task file {todo_path} was not created by session 1")
            return
        if cur_count == 0:
            print("  [workflow] all boxes ticked - workflow complete")
            return
        if err:
            print("  [workflow] stopped: session ended with an error")
            return

        if cur_count == prev_count:
            stall_count += 1
        else:
            prev_count, stall_count = cur_count, 1
        if stall_count >= stall_limit:
            print(
                f"  [workflow] stopped: the number of open boxes remained the same during {stall_count} consecutive sessions."
            )
            return


def main(argv: list[str] | None = None):
    def _run(args):
        spec = spec_path(args[1], args[2])
        if not spec.is_file():
            print(SPEC_NOT_FOUND_MSG.format(path=spec))
            sys.exit(1)
        run(Path(args[0]), args[1], args[2])

    cli_main(
        "Usage: python -m agent.workflow <config.toml> <project_name> <task_name>",
        lambda args: len(args) == 3,
        _run,
        argv,
    )


if __name__ == "__main__":
    main()
