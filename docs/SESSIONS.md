# Sessions And Matching

## Saved Sessions

`cosmic-wm save <name>` captures the current window set and writes a YAML file to:

- `~/.config/cosmic-wm-manager/sessions/<name>.yaml`

Each entry contains:

- the launch command
- the target workspace
- a match rule

Example:

```yaml
apps:
  - command: code
    workspace: 2
    match:
      class: code
```

## Why Some Entries Have Titles

If only one window exists for an app ID, the saved match usually keeps only:

- `class`

That keeps the session stable across title changes like:

- terminal current directory
- Discord channel or DM name
- browser tab title

If multiple windows share the same app ID, the session also stores `title` so the
restore flow can tell them apart.

Example:

```yaml
apps:
  - command: code
    workspace: 1
    match:
      class: code
      title: Welcome - Visual Studio Code

  - command: code
    workspace: 2
    match:
      class: code
      title: docs - Visual Studio Code
```

## Restore Semantics

`cosmic-wm restore <name>` is intended to be idempotent enough for normal reuse.

Current behavior:

- if a matching window is already open, restore reuses it
- if a configured entry is missing, restore launches it
- if two entries intentionally exist in the YAML, restore will try to satisfy both

This means duplicate windows usually come from one of two causes:

1. The session file really contains duplicate app entries.
2. The stored match rule is too specific and no longer matches the already-open window.

## Editing Sessions Manually

Manual editing is a supported workflow.

Common fixes:

- remove duplicate entries you no longer want
- relax a stale `title`
- change a command from a raw process path to a cleaner launcher command

## Debugging A Bad Restore

If restore does something unexpected, check these in order:

1. Inspect the saved session YAML.
2. Run `cosmic-wm status` to confirm the current `app_id` and title.
3. Compare the running window to the stored match rule.
4. Relax the title or remove it if the app is a singleton.
