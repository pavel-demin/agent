from pathlib import Path

from .core import Session, cli_main, is_interrupted, last_role, load_config, make_agent


def chat_and_sync(agent, user_input, sess_path):
    print("  [thinking...]")
    _, err = agent.turn(user_input, sess_path)
    if err:
        print(f"  Error: {err}")


def resume(agent):
    role = last_role(agent.messages)
    if role == "tool":
        return None, True
    if role == "user":
        return agent.messages.pop()["content"], True
    print("  [nothing to resume]")
    return None, False


def run(cfg_path, sess_path, prompt=None):
    cfg = load_config(cfg_path)

    sess = Session.load(sess_path)
    agent = make_agent(cfg, session=sess, sess_path=sess_path)
    if sess:
        print(f"Resuming session {sess.id}...")

    if prompt is not None:
        try:
            chat_and_sync(agent, prompt, sess_path)
        except KeyboardInterrupt:
            print("  [interrupted]")
        except Exception as e:  # noqa: BLE001
            print(f"  Error: {e}")
        return

    if is_interrupted(agent.messages):
        print("  [previous turn interrupted - type /resume to continue]")

    try:
        while True:
            try:
                line = input("> ").strip()
            except EOFError:
                break
            except Exception as e:  # noqa: BLE001
                print(f"  [error] input: {type(e).__name__}: {e}")
                continue

            try:
                if not line:
                    continue
                if line == "/quit":
                    break
                if line == "/new":
                    agent.archive(sess_path)
                    agent.reset()
                    print("  [new session]")
                    continue
                if line == "/resume":
                    content, resumed = resume(agent)
                    if resumed:
                        chat_and_sync(agent, content, sess_path)
                    continue

                chat_and_sync(agent, line, sess_path)
            except Exception as e:  # noqa: BLE001
                print(f"  Error: {e}")
                continue
    except KeyboardInterrupt:
        pass


def main(argv=None):
    def _run(args):
        prompt = args[2] if len(args) == 3 else None
        run(Path(args[0]), Path(args[1]), prompt)

    cli_main(
        "Usage: python -m agent.chat <config.toml> <session.json> [prompt]",
        lambda args: len(args) in (2, 3),
        _run,
        argv,
    )


if __name__ == "__main__":
    main()
