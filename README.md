A minimal LLM agent harness written in Python that communicates with an OpenAI-compatible chat completion API. It provides an interactive chat interface and a multi-session workflow driver.

## Project structure

- [chat.py](https://github.com/pavel-demin/agent/tree/main/chat.py) - interactive chat with automatic session saving after each turn.
- [workflow.py](https://github.com/pavel-demin/agent/tree/main/workflow.py) - workflow script that drives a task across as many LLM sessions as needed.
- [tasks](https://github.com/pavel-demin/agent/tree/main/tasks) - example task specification files.
- [config.toml](https://github.com/pavel-demin/agent/tree/main/config.toml) - configuration file.
- [core.py](https://github.com/pavel-demin/agent/tree/main/core.py) - agent loop and OpenAI-compatible API client.
- [tools.py](https://github.com/pavel-demin/agent/tree/main/tools.py) - built-in tools.

## Requirements

- Python 3.11 or newer.
- `python3 -m pip install requests rich`.
- Optionally `rlwrap` for line editing and prompt history.

## Chat mode

Starts an interactive chat:
```
rlwrap python3 -m agent.chat <config.toml> <session.json> [prompt]
```

Passing a prompt as the third argument runs a single turn and exits.

Example:
```
rlwrap python3 -m agent.chat agent/config.toml sessions/test.json
```

Commands:

- `/quit` - exit.
- `/new` - archive the current session and start a new one.
- `/resume` - continue an interrupted turn.

## Workflow mode

Drives a complex task across multiple LLM sessions until completion:
```
python3 -m agent.workflow <config.toml> <project_name> <task_name>
```

The driver manages the task through the following lifecycle:
1. Specification: Reads a specification file (`<project_name>/tasks/<task_name>-spec.md`).
2. Planning: Creates a detailed task file (`<project_name>/tasks/<task_name>-todo.md`) containing a list of executable steps with checkboxes.
3. Execution: The driver automatically starts and resumes LLM agent sessions until all check boxes in the task file are checked.

Each session transcript is archived for review in `sessions/<project_name>-<task_name>-<timestamp>.json`.

Example, using the existing specification file `agent/tasks/tests-spec.md`:
```bash
python3 -m agent.workflow agent/config.toml agent tests
```
