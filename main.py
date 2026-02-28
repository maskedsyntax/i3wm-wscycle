#!/usr/bin/env python3
import sys
import os
import json
import i3ipc


STATE_FILE = os.path.expanduser("~/.cache/i3wm-wscycle-state.json")
LOG_FILE = "/tmp/i3-wscycle.log"


def log(msg):
    with open(LOG_FILE, "a") as f:
        f.write(f"{msg}\n")


def load_state():
    if not os.path.exists(STATE_FILE):
        return {}
    try:
        with open(STATE_FILE, "r") as f:
            return json.load(f)
    except Exception as e:
        log(f"Error loading state: {e}")
        return {}


def save_state(state):
    try:
        os.makedirs(os.path.dirname(STATE_FILE), exist_ok=True)
        with open(STATE_FILE, "w") as f:
            json.dump(state, f)
    except Exception as e:
        log(f"Error saving state: {e}")
        print(f"Failed to save state: {e}", file=sys.stderr)


# Parse workspace number (handles "3:web" → 3)
def parse_name(name: str) -> int:
    try:
        return int(name.split(":", 1)[0])
    except ValueError:
        return 9999  # fallback for non-numeric names


# Get current (focused) workspace and all workspaces
def get_current_workspace(i3):
    workspaces = i3.get_workspaces()
    current = next((ws for ws in workspaces if ws.focused), None)
    if current is None:
        print("No focused workspace found", file=sys.stderr)
        sys.exit(1)
    return current, workspaces


# Cycle workspace on the same output
def cycle_workspace(i3, direction: int):
    current, workspaces = get_current_workspace(i3)

    # filter same output
    same_output = [ws for ws in workspaces if ws.output == current.output]

    # sort numerically by workspace number
    same_output.sort(key=lambda ws: parse_name(ws.name))

    # find index of current
    idx = next((i for i, ws in enumerate(same_output) if ws.name == current.name), 0)

    # wrap around
    new_idx = (idx + direction) % len(same_output)
    next_ws = same_output[new_idx]

    i3.command(f"workspace {next_ws.name}")


def get_outputs(i3):
    tree = i3.get_tree()
    outputs = [
        n.name for n in tree.nodes if n.type == "output" and not n.name.startswith("__")
    ]
    return sorted(outputs)


def toggle_output(i3):
    current, _ = get_current_workspace(i3)
    outputs = get_outputs(i3)

    if len(outputs) < 2:
        print("Not enough outputs detected")
        sys.exit(1)

    try:
        idx = outputs.index(current.output)
    except ValueError:
        print(f"Current output {current.output} not in detected outputs {outputs}")
        sys.exit(1)

    # Move to next output, wrap around
    target = outputs[(idx + 1) % len(outputs)]

    i3.command(f"move workspace to output {target}")
    i3.command(f"workspace {current.name}")


def back_on_output(i3):
    state = load_state()
    current, _ = get_current_workspace(i3)
    output = current.output

    history = state.get(output, [])
    log(f"Back requested for output {output}. Current: {current.name}, History: {history}")

    if len(history) >= 2:
        # history[-1] should be the current workspace
        # history[-2] is the last one
        prev_ws = history[-2]
        
        # If history[-1] is NOT the current workspace, it might be out of sync
        if history[-1] != current.name:
            log(f"History out of sync! history[-1]({history[-1]}) != current({current.name})")
            # We still try to switch to history[-1] as it's likely the "actual" previous one 
            # if we just arrived at 'current' but the daemon hasn't updated yet.
            prev_ws = history[-1]

        log(f"Switching to workspace: '{prev_ws}'")
        responses = i3.command(f"workspace {prev_ws}")
        for r in responses:
            if not r.success:
                log(f"Command failed: {r.error}")
            else:
                log("Command sent successfully")
    else:
        log("History length < 2, not enough data to switch")


def listen(i3):
    def update_state(i3, e):
        # We listen to all workspace events and check if the change is 'focus'
        if e.change != "focus":
            return

        if not e.current:
            return

        # e.current is a Con object which doesn't have .output directly.
        # We find the corresponding WorkspaceReply to get the output name.
        workspaces = i3.get_workspaces()
        current_ws = next((ws for ws in workspaces if ws.name == e.current.name), None)
        
        if not current_ws:
            return

        state = load_state()
        output = current_ws.output
        name = current_ws.name

        history = state.get(output, [])
        # Only add if it's different from the last tracked workspace on this output
        if not history or history[-1] != name:
            history.append(name)
            # Keep only the last 2 workspaces to allow simple back-and-forth
            state[output] = history[-2:]
            log(f"Updated {output}: {state[output]}")
            save_state(state)

    # Initialize state with the currently focused workspace on its output
    current, _ = get_current_workspace(i3)
    state = load_state()
    state[current.output] = [current.name]
    save_state(state)
    log(f"Daemon started. Current output {current.output} at {current.name}")

    i3.on("workspace::focus", update_state)
    i3.main()


def status():
    state = load_state()
    print(f"State file: {STATE_FILE}")
    print(f"Log file: {LOG_FILE}")
    print("History per output:")
    for output, history in state.items():
        print(f"  {output}: {history}")


def main():
    if len(sys.argv) < 2:
        print("Usage: i3-wscycle.py [toggle|next|prev|listen|back|status]")
        sys.exit(1)

    i3 = i3ipc.Connection()
    cmd = sys.argv[1]

    if cmd == "toggle":
        toggle_output(i3)
    elif cmd == "next":
        cycle_workspace(i3, +1)
    elif cmd == "prev":
        cycle_workspace(i3, -1)
    elif cmd == "listen":
        listen(i3)
    elif cmd == "back":
        back_on_output(i3)
    elif cmd == "status":
        status()
    else:
        print(f"Unknown command: {cmd}")
        sys.exit(1)


if __name__ == "__main__":
    main()
