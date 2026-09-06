# Upstream Sync Strategy

This fork diverges significantly from upstream (NousResearch/hermes-agent) with ~535 customization commits including:
- Business-OS (Waves 1-33)
- Rebranding (Hermes → Charterforge)
- Custom CLI/desktop/web architecture
- Extended test suite

## Current State

**Branch: `main`**
- Has upstream/main as parent via "ours" merge (commit `e4b9570fa3`)
- Preserves all Charterforge customizations
- Security backports applied: GHSA-7x36-8jrh-v4pw + multiplex dotenv isolation

## Future Sync Process

### Option A: Full Merge (Recommended for Major Syncs)

```bash
./scripts/sync-upstream.sh
# Resolve conflicts in sync-* branch
# Then merge to main
```

This leverages the existing "ours" merge base - git only sees NEW upstream commits since the last sync.

### Option B: Selective Cherry-Pick (For Specific Fixes)

```bash
./scripts/cherry-pick-upstream.sh <commit-hash> [<commit-hash>...]
```

Pre-identified high-value batches:

| Category | Commits |
|----------|---------|
| Agent streaming | `7b72fd1247 390c27c6db 562ee8ab76 3755dca7d6 c3e9defd18` |
| Session/state | `86b204081d ab281990b8 73f68362b3 61635e1b53 bcc2e65818 e9160625dc` |
| Performance | `c3b411dfb7 561b053f79 c96568f66c 2b55ded1ac` |
| Models/providers | `7e60d0c042 7f2aa70add d6bb94a1fb b462989a68 c2954c8934 0ee98eda52 4359af7705` |
| Gateway multiplex | `17f86ab36f eed481bd34 a6351a71e5 74b00d7a97 2ce6f5c538 ca42d7a034` |

### Option C: Rebase (Clean but High Effort)

```bash
git checkout -b rebase-new upstream/main
# Apply 535 customization commits as patches
# Then replace main
```

Only worth it for a major architectural alignment.

## Verification

After any sync:
```bash
scripts/run_tests.sh tests/security/test_gitspawn_config_injection.py
scripts/run_tests.sh tests/hermes_cli/test_config.py tests/hermes_cli/test_kanban_worktree_isolation.py
```

## Key Files That Typically Conflict

| File | Why |
|------|-----|
| `cli.py` | Business-OS commands + custom worktree logic |
| `hermes_cli/config.py` | Extended config schema |
| `hermes_cli/main.py` | Custom entry point |
| `hermes_cli/web_server.py` | Dashboard extensions |
| `apps/desktop/` | Complete rebrand + custom architecture |
| `web/src/` | Charterforge-branded dashboard |
| `hermes_constants.py` | Profile-aware paths |

## Security Backports Already Applied

| Commit | Description |
|--------|-------------|
| `02f00c71a7` | GHSA-7x36-8jrh-v4pw GitSpawn RCE fix + multiplex dotenv isolation |
| `359e907dc6` | Regression test suite (14 tests) |
| `c349a969dc` | Context references hardening fix |
