# cosmic-vm-manager

Wayland-native session restore and workspace automation for COSMIC Desktop.


## What It Does

`cosmic-wm` helps you:

- Launch a repeatable workspace setup from YAML profiles
- Save the current desktop session as a snapshot
- Restore saved sessions onto the right workspaces
- Route windows across outputs and workspace groups in COSMIC
- Reuse already-open matching windows during restore instead of blindly relaunching everything

It is built for COSMIC Desktop on Wayland and uses `cos-cli` to talk to the compositor.

## Current Behavior

- `start <profile>` launches apps from a profile and places matching windows
- `save <name>` captures open windows into a YAML session file
- `restore <name>` replays that session and skips relaunching windows that already match
- When only one window exists for an app ID, saved sessions prefer stable `app_id` matching over volatile titles
- When multiple windows share the same app ID, titles are kept to disambiguate them

## Installation

Prerequisites:

- Pop!_OS / COSMIC Desktop on Wayland
- Python 3.11+
- Rust toolchain for building `cos-cli`

Install:

```bash
git clone git@github.com:Izume01/cosmic-wm-manager.git cosmic-session-manager
cd cosmic-session-manager
./install.sh
```

That script:

- builds or reuses `cos-cli`
- creates `.venv`
- installs the package in editable mode
- writes `~/.local/bin/cosmic-wm`

Make sure `~/.local/bin` is on your `PATH`.

## Usage

Start a profile:

```bash
cosmic-wm start dev
```

Save the current session:

```bash
cosmic-wm save coding
```

Restore a saved session:

```bash
cosmic-wm restore coding
```

Show current windows and workspaces:

```bash
cosmic-wm status
```

Enable restore on login:

```bash
cosmic-wm autostart --enable
```

Rebuild the helper after COSMIC changes:

```bash
cosmic-wm update
```

## Profile Format

Profiles live in `~/.config/cosmic-wm-manager/profiles/`.

Example:

```yaml
name: work
description: Daily development setup

monitors:
  - output: eDP-1
    primary: true
    workspace_count: 4

apps:
  - command: "kitty --title backend"
    workspace: 1
    match:
      class: kitty
      title: backend

  - command: code
    workspace: 2
    match:
      class: code

  - command: flatpak run com.discordapp.Discord
    workspace: 3
    match:
      class: discord
```

## Session Files

Saved sessions live in `~/.config/cosmic-wm-manager/sessions/`.

They are normal YAML files, so you can edit them manually. This is useful when:

- you want fewer duplicate windows restored
- a command needs to change
- a title-based match became too specific

If a session contains two `code` entries, restore will still open two VS Code windows by design.

## Matching Rules

Supported match fields:

- `class`: COSMIC app ID / window class
- `title`: regex or case-insensitive substring
- `process_name`: process-level fallback matching

Matching is intentionally conservative:

- exact configured windows are matched first
- some title drift can fall back to `app_id`-only matching
- existing matching windows are reused during restore

## Troubleshooting

`Workspace not found`

- usually means COSMIC has not materialized the next workspace yet
- the current implementation steps through workspace growth instead of jumping past the current tail

Duplicate windows after restore

- check the session YAML first
- repeated `restore` runs should now reuse matching windows instead of reopening them
- if duplicates still happen, the saved match rule is probably too specific or the app title changed

Launcher still shows closed apps

- `cosmic-wm` does not maintain its own launcher history
- if closed apps still appear in COSMIC's launcher or app switcher, that is likely compositor or desktop-shell state rather than this tool's session list

## Development

Additional docs:

- [Architecture](docs/ARCHITECTURE.md)
- [Sessions and matching](docs/SESSIONS.md)

Run tests with the project virtualenv:

```bash
.venv/bin/python -m unittest tests/test_window_routing.py
```

Key modules:

- `cosmic_wm_manager/cli/main.py`
- `cosmic_wm_manager/persistence/session.py`
- `cosmic_wm_manager/retry_engine/poll.py`
- `cosmic_wm_manager/adapters/cosmic.py`

## License

This project is licensed under the MIT License. See the [LICENSE](LICENSE) file for the full text.
