#!/usr/bin/env python3
import sys
import os
import json
import i3ipc


import time


STATE_FILE = os.path.expanduser("~/.cache/i3wm-wscycle-state.json")
LOG_FILE = "/tmp/i3-wscycle.log"
HISTORY_LIMIT = 10
BACK_TIMEOUT = 1.0  # seconds within which repeated 'back' calls move deeper


def log(msg):
    # Prepend timestamp for better debugging
    ts = time.strftime("%Y-%m-%d %H:%M:%S")
    with open(LOG_FILE, "a") as f:
        f.write(f"[{ts}] {msg}\n")


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


# Parse workspace number (handles "3:web" -> 3)
def parse_name(name: str) -> int:
    try:
        return int(name.split(":", 1)[0])
    except (ValueError, IndexError):
        return 9999  # fallback for non-numeric names


# Get current (focused) workspace and all workspaces
def get_current_workspace(i3):
    workspaces = i3.get_workspaces()
    current = next((ws for ws in workspaces if ws.focused), None)
    if current is None:
        # If no focused workspace, maybe i3 is in a weird state.
        # Try to find any workspace.
        if workspaces:
            return workspaces[0], workspaces
        print("No workspaces found", file=sys.stderr)
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

    data = state.get(output, {})
    # Handle both old list format and new dict format
    if isinstance(data, list):
        history = data
    else:
        history = data.get("history", [])

    log(f"Back requested for output {output}. Current: {current.name}, History: {history}")

    if len(history) < 2:
        # If we only have one workspace in history, we can't toggle.
        # However, if the one we have isn't the current one, it's effectively the 'last'.
        if len(history) == 1 and history[0] != current.name:
            target_ws = history[0]
        else:
            log("Not enough history to toggle.")
            return
    else:
        # History is [last, current]
        # If history[-1] is current, we go to history[-2]
        if history[-1] == current.name:
            target_ws = history[-2]
        else:
            # Out of sync, history[-1] is likely the last one
            target_ws = history[-1]

    log(f"Toggling to workspace: '{target_ws}'")
    i3.command(f"workspace {target_ws}")


def listen():
    def update_state(i3, e):
        if e.change != "focus":
            return

        if not e.current:
            return

        workspaces = i3.get_workspaces()
        current_ws = next((ws for ws in workspaces if ws.name == e.current.name), None)
        
        if not current_ws:
            return

        state = load_state()
        output = current_ws.output
        name = current_ws.name

        data = state.get(output, {})
        if isinstance(data, list):
            history = data
        else:
            history = data.get("history", [])

        # Strict toggle logic:
        # We only care about the last workspace and the current one.
        if not history:
            history = [name]
        elif history[-1] != name:
            # New workspace focused. 
            # The old history[-1] becomes the 'last' (history[0])
            # The new 'name' becomes the 'current' (history[1])
            history = [history[-1], name]
            
            state[output] = {"history": history}
            log(f"Updated {output} pair: {history}")
            save_state(state)

    while True:
        try:
            log("Connecting to i3...")
            i3 = i3ipc.Connection()
            
            current, _ = get_current_workspace(i3)
            state = load_state()
            output = current.output
            
            # Initialize or update the current workspace in state
            data = state.get(output, {})
            if isinstance(data, list):
                history = data
            else:
                history = data.get("history", [])

            if not history:
                history = [current.name]
            elif history[-1] != current.name:
                history = [history[-1], current.name]
            
            state[output] = {"history": history}
            save_state(state)
            
            log(f"Daemon listening. Current output {current.output} at {current.name}")
            i3.on("workspace::focus", update_state)
            i3.main()
        except Exception as e:
            log(f"Daemon error: {e}")
            time.sleep(2)



def status():
    state = load_state()
    print(f"State file: {STATE_FILE}")
    print(f"Log file: {LOG_FILE}")
    print("History per output:")
    for output, data in state.items():
        if isinstance(data, list):
            history = data
            extra = ""
        else:
            history = data.get("history", [])
            back_idx = data.get("back_index", 0)
            extra = f" (back_index: {back_idx})"
        print(f"  {output}: {history}{extra}")


def main():
    if len(sys.argv) < 2:
        print("Usage: i3-wscycle.py [toggle|next|prev|listen|back|status]")
        sys.exit(1)

    cmd = sys.argv[1]

    if cmd == "listen":
        listen()
        return

    i3 = i3ipc.Connection()
    if cmd == "toggle":
        toggle_output(i3)
    elif cmd == "next":
        cycle_workspace(i3, +1)
    elif cmd == "prev":
        cycle_workspace(i3, -1)
    elif cmd == "back":
        back_on_output(i3)
    elif cmd == "status":
        status()
    else:
        print(f"Unknown command: {cmd}")
        sys.exit(1)



if __name__ == "__main__":
    main()
