import json
import os
import sys
import time
from dataclasses import asdict, dataclass, field
from typing import Any

import requests
import tomllib
from rich.console import Console
from rich.markdown import Markdown
from rich.theme import Theme

from .tools import execute, tools

LIGHT_THEME = Theme(
    {
        "markdown.code": "#000000 on #cccccc",
        "markdown.item.bullet": "bold #222222",
        "markdown.item.number": "bold #222222",
    }
)


@dataclass
class Session:
    id: str = field(default_factory=lambda: time.strftime("%Y%m%d-%H%M%S"))
    messages: list[dict[str, Any]] = field(default_factory=list)

    @classmethod
    def load(cls, path):
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            if not isinstance(data, dict):
                return None
            session = cls()
            session.id = data.get("id", session.id)
            session.messages = data.get("messages", [])
            return session
        except (OSError, json.JSONDecodeError, UnicodeDecodeError):
            return None

    def dump(self, path):
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(asdict(self), indent=2))


def last_role(messages):
    if not isinstance(messages, list) or not messages or not isinstance(messages[-1], dict):
        return None
    return messages[-1].get("role")


def is_interrupted(messages):
    return last_role(messages) in ("user", "tool")


class APIError(Exception):
    """The API returned an error object (or an HTTP-level failure)."""


class Model:
    def __init__(self, cfg, key, tools):
        self.cfg = cfg
        self.key = key
        self.tools = tools
        self.http = requests.Session()

    def call(self, messages, with_tools):
        headers = {"Authorization": f"Bearer {self.key}"} if self.key else None
        payload = {
            "model": self.cfg["model"],
            "messages": messages,
            "tools": self.tools if with_tools else [],
        }

        resp = self.http.post(self.cfg["url"], headers=headers, json=payload)
        resp.raise_for_status()
        data = resp.json()
        if "error" in data:
            raise APIError(f"API error: {data['error']}")
        return data


class Agent:
    def __init__(self, cfg, console, model, execute, session=None, session_path=None):
        self.cfg = cfg
        self.console = console
        self.model = model
        self.execute = execute
        self.system_prompt = self.cfg["prompt"].rstrip()
        self.session_path = session_path
        self.reset(session)

    def sync_session(self, path):
        self.session.messages = self.messages
        self.session.dump(path)

    def archive(self, path):
        archive_dir = path.parent
        archive_dir.mkdir(parents=True, exist_ok=True)
        archive_path = archive_dir / f"{self.session.id}.json"
        self.session.dump(archive_path)
        path.unlink(missing_ok=True)

    def reset(self, session=None):
        self.session = session or Session()
        self.messages = self.session.messages if isinstance(self.session.messages, list) else []
        self.prompt_tokens = 0

    def note(self, text):
        self.messages.append({"role": "user", "content": text})

    def turn(self, user_input, path):
        content, err = self.chat(user_input)
        self.sync_session(path)
        return content, err

    def build_req(self, step):
        pct = round(100 * self.prompt_tokens / self.cfg["max_tokens"])
        if self.prompt_tokens >= 0.8 * self.cfg["max_tokens"]:
            self.note(f"[SYSTEM: Context size is {pct}%. Limit reached. Finish in the fewest possible steps.]")
        elif step > 0 and step % 10 == 0 and self.prompt_tokens > 0:
            self.note(f"[SYSTEM: Context size is {pct}%.]")

        req = [{"role": "system", "content": self.system_prompt}] + self.messages

        return req

    def show(self, label, text):
        if text and text.strip():
            print(f"  [{label}]")
            self.console.print(Markdown(text, code_theme="default"))
            return True
        return False

    def chat(self, user_input=None):
        if user_input is not None:
            self.note(user_input)

        step = 0
        while True:
            if self.session_path:
                self.sync_session(self.session_path)

            req = self.build_req(step)

            resp = self.model.call(req, True)

            if not resp.get("choices"):
                error_info = resp.get("error", str(resp))
                print(f"  [API error response: {error_info}]")
                return "", f"API error: {error_info}"

            msg = resp["choices"][0]["message"]
            content = msg.get("content", "")
            tool_calls = msg.get("tool_calls", [])
            usage = resp.get("usage", {})
            self.prompt_tokens = usage.get("prompt_tokens", 0)
            hit_tokens = usage.get("prompt_cache_hit_tokens", 0)
            miss_tokens = usage.get("prompt_cache_miss_tokens", 0)

            print(f"  [size: {self.prompt_tokens} hit: {hit_tokens} miss: {miss_tokens} max: {self.cfg['max_tokens']}]")

            assistant_msg = {"role": msg["role"], "content": content}
            for key in ("reasoning", "reasoning_content"):
                if self.show(key, msg.get(key, "")):
                    assistant_msg[key] = msg[key]
            self.show("content", content)

            if tool_calls:
                assistant_msg["tool_calls"] = tool_calls
            self.messages.append(assistant_msg)

            if not tool_calls:
                return content, None

            print("  [tool calls]")
            for tc in tool_calls:
                self.messages.append(self.execute(self, tc))

            step += 1


def load_config(path):
    return tomllib.loads(path.read_text(encoding="utf-8"))


def make_agent(cfg, key=None, session=None, sess_path=None):
    if key is None:
        key = os.getenv("LLM_API_KEY")
    console = Console(theme=LIGHT_THEME)
    model = Model(cfg["api"], key, tools)
    return Agent(cfg["agent"], console, model, execute, session, sess_path)


def cli_main(usage, valid_args, run_fn, argv=None):
    args = list(sys.argv[1:]) if argv is None else list(argv)
    if not valid_args(args):
        sys.exit(usage)
    try:
        run_fn(args)
    except Exception as e:  # noqa: BLE001
        print(f"Fatal error: {type(e).__name__}: {e}")
        sys.exit(1)
