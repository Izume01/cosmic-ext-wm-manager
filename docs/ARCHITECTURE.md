# Architecture

## Overview

`cosmic-wm` is a small orchestration layer on top of COSMIC's compositor tooling.

The project has four main responsibilities:

1. Load a profile or saved session from YAML.
2. Launch missing applications.
3. Match open windows to configured app entries.
4. Move matched windows onto the intended workspace or output.

The CLI is intentionally thin. Most behavior lives in a few focused modules.

## Main Modules

### `cosmic_wm_manager/cli/main.py`

Entry point for the `cosmic-wm` command.

It is responsible for:

- loading profiles and sessions
- building workspace routing metadata
- reusing already-open windows during restore
- invoking the retry engine after launch

### `cosmic_wm_manager/persistence/session.py`

Handles session capture.

It turns the current compositor state into a YAML file under:

- `~/.config/cosmic-wm-manager/sessions/`

The capture logic prefers stable `app_id` matches for singleton windows and only
stores titles when the same app appears multiple times and needs disambiguation.

### `cosmic_wm_manager/retry_engine/poll.py`

Coordinates launch-time matching and placement.

This module repeatedly polls the compositor for windows, finds the best match for
each configured app, and calls the backend to move the window into place.

### `cosmic_wm_manager/adapters/cosmic.py`

Concrete COSMIC backend.

This module wraps `cos-cli` and translates compositor JSON into internal models.
It also contains the workspace-stepping logic needed when COSMIC has not yet
materialized the next workspace in the current tail.

### `cosmic_wm_manager/window_manager/matcher.py`

Pure matching logic.

Supported match inputs:

- `class` / `app_id`
- `title`
- `process_name`

## Data Flow

Typical restore flow:

1. `restore <name>` loads a saved YAML session.
2. The CLI reads the currently open windows.
3. Matching windows are reused instead of relaunched.
4. Missing app entries are launched.
5. The retry engine waits for windows to appear.
6. The COSMIC backend moves each matched window to the requested destination.

## Design Notes

### Stable matching beats exact matching

Window titles are often volatile. Exact title-only restore logic produces stale
sessions and duplicate launches. The current code treats `app_id` as the stable
anchor and uses titles only when multiple windows of the same app must be
separated.

### The backend owns compositor quirks

COSMIC-specific behavior should stay in the backend layer, not leak into the CLI.
That includes `cos-cli` invocation details, output routing, and workspace growth.

### Sessions are editable

Saved sessions are plain YAML by design. Users should be able to edit commands,
remove duplicates, or relax overly specific matches without changing code.
