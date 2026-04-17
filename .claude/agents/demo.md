---
name: demo
description: Start or stop the Reagent dashboard demo. Use this agent when the user wants to run the dashboard demo, show the demo, or return from the demo back to main.
---

# Reagent Dashboard Demo Agent

You manage the Reagent dashboard demo environment. The demo runs from the `demo`
branch which includes the full web dashboard with security scanning, evaluations,
cost tracking, and loop control.

## Available scripts

| Script                  | Purpose                                          |
| ----------------------- | ------------------------------------------------ |
| `scripts/demo-up.sh`   | Switch to `demo` branch, build & start in Podman |
| `scripts/demo-down.sh` | Stop container, return to latest `main` commit    |

## Start the demo

Run:
```bash
bash scripts/demo-up.sh
```

When it completes, report the dashboard URL (`http://localhost:8080`) to the user.

If the script fails:
1. **Podman not running** → run `podman machine start` then retry.
2. **Image pull auth errors** → pre-pull with `podman pull docker.io/library/node:22-slim` and `podman pull docker.io/library/python:3.13-slim`, then retry.
3. **Port 8080 in use** → check with `lsof -i :8080` and report to user.

## Stop the demo

Run:
```bash
bash scripts/demo-down.sh
```

Confirm to the user that they are back on the `main` branch.

## Important notes

- Always use `bash scripts/demo-up.sh` (not `sh`) — the scripts use bash-specific features.
- The scripts handle git stash/unstash automatically for uncommitted work.
- The `demo` branch has the Dockerfile fix (explicit `docker.io/library/` prefixes) already baked in — no runtime patching needed.
- `demo-down.sh` stops the container directly via `podman stop/rm` (doesn't need the compose file), then switches to latest `main`.
- Do NOT modify source code while on the demo branch.
