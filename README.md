# i3wm-wscycle
i3wm addon for smart workspace cycling.

## Features
- **Cycle workspaces** on the same output (wraps around at the end)
    - `next` -> go to the next workspace
    - `prev` -> go to the previous workspace
- **Toggle outputs**: move the current workspace between different monitors/screens (and also wraps around them).
- **Workspace History (back-and-forth)**: switch to the last visited workspace on the current output.
    - `listen` -> start a daemon to track workspace history.
    - `back` -> switch to the previous workspace on the current output.

## Usage
```bash
./main.py [toggle|next|prev|listen|back]
```

## Example i3 config bindings
``` bash
# Start the daemon
exec --no-startup-id ~/scripts/main.py listen

# Cycle workspaces
bindsym $mod+bracketright exec --no-startup-id ~/scripts/main.py next
bindsym $mod+bracketleft  exec --no-startup-id ~/scripts/main.py prev

# Toggle outputs
bindsym $mod+o exec --no-startup-id ~/scripts/main.py toggle

# Back-and-forth on the current output
bindsym $mod+Tab exec --no-startup-id ~/scripts/main.py back
```

## Requirements

- Python
- python3-i3ipc

Install with:
```bash
pip install i3ipc
```
