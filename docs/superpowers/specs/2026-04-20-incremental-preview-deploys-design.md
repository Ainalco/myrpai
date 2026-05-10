# Incremental Preview Deploys

## Problem

Today, every push to a PR triggers `preview-deploy.yml` which destroys the existing preview VM, clones a fresh one from the Proxmox template, reinstalls Docker + Tailscale, and redeploys the app. Each cycle takes several minutes and discards all runtime state (DB data, cached builds, logs). For a PR that gets 10 commits, that's 10 full VM rebuilds.

## Goal

Reuse the preview VM across commits on the same PR. On new commits, SSH into the existing VM and do `git fetch && git reset --hard && docker compose up -d --build`. Only create a fresh VM when one doesn't already exist (first deploy, or after PR close/reopen).

## Non-Goals

- No change to `destroy-preview` job — PR close still destroys the VM
- No manual "force rebuild" trigger — close+reopen the PR to get a clean VM
- No changes to `docker-compose.preview.yml`, seed scripts, or migrations
- No caching of Docker layers beyond what the VM's local Docker already does

## Architecture

### VM lifecycle

```
opened/synchronize/reopened
   │
   ▼
Check Proxmox for VM with ID 70000+PR_NUM
   │
   ├── VM does not exist ──►  full provisioning path (today's flow)
   │                             ├─ Clone VM from template
   │                             ├─ Start VM, wait for boot + SSH
   │                             ├─ Provision Docker + Tailscale
   │                             ├─ Write fresh .env (with fresh SECRET_KEY)
   │                             ├─ git clone repo into ~/app on VM
   │                             └─ docker compose up -d --build
   │
   └── VM exists ──────────►  incremental path (new)
                                 ├─ SSH in, git fetch + reset --hard <PR_HEAD_SHA>
                                 └─ docker compose up -d --build --remove-orphans
                                    (.env left untouched)

closed
   │
   └── destroy-preview job (unchanged)
```

### Workflow structure

Single `deploy-preview` job. The branching is done with `if:` conditions on individual steps, gated by a `VM_EXISTS` env var set early in the job.

| Step | Run when |
|---|---|
| Set variables | always |
| Setup SSH key | always |
| Check VM existence (sets `VM_EXISTS`) | always |
| Clone VM from template | `VM_EXISTS == 'false'` |
| Start VM | `VM_EXISTS == 'false'` |
| Get VM IP | always |
| Wait for SSH | `VM_EXISTS == 'false'` |
| Provision Docker + Tailscale | `VM_EXISTS == 'false'` |
| Get Tailscale IP (via SSH `tailscale ip -4`) | always |
| **Fresh deploy** (write .env, git clone, compose up) | `VM_EXISTS == 'false'` |
| **Incremental deploy** (fetch + reset + compose up) | `VM_EXISTS == 'true'` |
| Comment on PR | always |
| Cleanup SSH key | always (`if: always()`) |

The existing "Destroy existing VM if re-deploying" step is removed entirely.

### VM existence probe

```bash
STATUS=$(curl -sk -w "%{http_code}" -o /dev/null \
  -H "Authorization: PVEAPIToken=${{ secrets.PROXMOX_API_TOKEN }}" \
  "${PVE_API}/nodes/${PROXMOX_NODE}/qemu/${VM_ID}/status/current")

if [ "$STATUS" = "200" ]; then
  echo "VM_EXISTS=true" >> $GITHUB_ENV
else
  echo "VM_EXISTS=false" >> $GITHUB_ENV
fi
```

### Fresh deploy path

Replaces today's "Deploy app to VM" step. Key change: instead of `rsync` from the runner, clone the repo directly on the VM.

```bash
# Write .env (unchanged from today, including fresh SECRET_KEY)
printf '%s\n' '${{ secrets.PREVIEW_ENV_FILE }}' > /tmp/preview.env
# ... printf overrides for DOMAIN_NAME, URLs, etc. ...
printf 'SECRET_KEY=%s\n' "$(openssl rand -hex 32)" >> /tmp/preview.env
sed -i 's/^[[:space:]]*//' /tmp/preview.env && sed -i 's/\r$//' /tmp/preview.env
scp -i ~/.ssh/preview_key /tmp/preview.env ubuntu@${VM_IP}:~/app.env.tmp
rm -f /tmp/preview.env

# Clone repo on VM using GH_PAT; checkout the exact PR HEAD commit
ssh -i ~/.ssh/preview_key ubuntu@${VM_IP} <<SSHEOF
  set -e
  git clone https://x-access-token:${{ secrets.GH_PAT }}@github.com/${{ github.repository }}.git ~/app
  cd ~/app
  git config credential.helper store
  echo "https://x-access-token:${{ secrets.GH_PAT }}@github.com" > ~/.git-credentials
  chmod 600 ~/.git-credentials
  git checkout ${{ github.event.pull_request.head.sha }}
  mv ~/app.env.tmp ~/app/.env
  docker compose --env-file .env -f docker/docker-compose.preview.yml up -d --build
  sleep 30
  docker compose --env-file .env -f docker/docker-compose.preview.yml ps
SSHEOF
```

The `actions/checkout@v4` step on the runner is no longer needed. `${{ github.repository }}` and `${{ github.event.pull_request.head.sha }}` give us everything we need.

### Incremental deploy path

```bash
ssh -i ~/.ssh/preview_key ubuntu@${VM_IP} <<SSHEOF
  set -e
  cd ~/app
  git fetch --all --prune
  git reset --hard ${{ github.event.pull_request.head.sha }}
  docker compose --env-file .env -f docker/docker-compose.preview.yml up -d --build --remove-orphans
  sleep 30
  docker compose --env-file .env -f docker/docker-compose.preview.yml ps
SSHEOF
```

Notes:
- `git fetch --all --prune` also drops stale remote-tracking branches, so force-pushed PR branches don't leave orphans
- `git reset --hard <sha>` guarantees we land exactly on the PR's HEAD, matching `actions/checkout` behavior
- `.env` is not touched — `SECRET_KEY` stays stable, existing JWTs survive
- `--remove-orphans` cleans up containers for services that were deleted from the compose file
- `--build` rebuilds images whose dockerfile/context changed; untouched services are left alone

### Secret propagation tradeoff

Because incremental deploys don't rewrite `.env`, updates to the `PREVIEW_ENV_FILE` GitHub secret (e.g., API key rotation) do NOT propagate to existing preview VMs. To pick up a rotated secret on a running preview, close + reopen the PR. This is a deliberate tradeoff chosen for session stability; documented here so the future-you doesn't chase a ghost.

## Failure modes

- **VM exists but is in a bad state** (container wedged, disk full, etc.): `docker compose up -d --build` may fail. Resolution: close + reopen the PR to get a clean VM. No automated self-heal in this spec.
- **`.env` missing on incremental path**: would happen only if someone manually deleted it on the VM. `docker compose --env-file .env` fails loudly; same resolution — close + reopen the PR.
- **`git reset --hard` over uncommitted VM-side edits**: if someone SSH'd in and hand-edited files in `~/app`, the incremental path discards their edits. This is intended behavior — the VM is a deployment target, not a workspace.
- **GH_PAT expired**: fresh-deploy `git clone` fails; existing VMs keep working (credentials were stored on first clone). Rotate the secret and trigger a close+reopen.
- **PR head on a fork**: `git fetch` on the origin remote won't see fork commits. This workflow already requires same-repo PRs (the Proxmox runner wouldn't be exposed to forks anyway), so out of scope.

## Testing

Manual verification on a throwaway PR:

1. **Fresh deploy**: open a new PR on a feature branch, confirm VM is created, app is reachable at the Tailscale IP, and the PR comment appears
2. **Incremental deploy**: push a second commit to the same PR, watch the workflow run — verify it SSHs in, runs `git fetch + reset`, and `docker compose up -d --build` rebuilds only changed services. The app should stay reachable throughout (brief container restarts are fine); seed users should still be able to log in (SECRET_KEY preserved, DB volume preserved)
3. **Compose file change**: push a commit that modifies `docker-compose.preview.yml` (add an env var to backend), confirm the backend container is recreated
4. **PR close**: close the PR, confirm `destroy-preview` still runs and tears down the VM
5. **PR reopen**: reopen the closed PR, confirm it falls into the fresh-deploy path (VM doesn't exist → clone template)

No automated tests — the workflow is GitHub-Actions-driven and runs only in the live Proxmox environment.

## Files touched

- `.github/workflows/preview-deploy.yml` — restructured with conditional steps, new incremental path, `actions/checkout@v4` removed
