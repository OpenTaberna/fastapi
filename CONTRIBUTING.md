# Contributing

Thanks for helping out. Read the [Code of Conduct](CODE_OF_CONDUCT.md) first — swearing
about code is fine, swearing at people is not.

## How a change gets in

`main` is protected. Only the maintainers, @PhilippTheServer and @maltonoloco, can push
to it directly. Everyone else goes through a pull request:

1. **Open an issue** describing the behaviour you expect once it is solved. Small fixes
   too — it is where the discussion lives.
2. **Branch** from `main` (or fork, if you have no write access).
3. **Commit and push** your branch.
4. **Open a pull request** against `main` and link the issue with `Closes #N` in the
   body.
5. **CI must pass.** These checks are required before the PR can be merged:
   - `Run Tests with Services`
   - `Code Quality Checks`
   - `Security Scan`
   - `Test Docker Build`
6. **A maintainer must approve.** Every file is owned by @PhilippTheServer and
   @maltonoloco (see [.github/CODEOWNERS](.github/CODEOWNERS)); one of them has to
   review and approve. New commits after an approval need a fresh approval.
7. **Squash merge.** The PR lands as a single commit on `main`; delete the branch
   afterwards.

## Before you open the PR

Run the same checks locally so CI has no surprises (integration tests also need the API
running — see Dev Setup in the [README](README.md)):

```sh
uv sync --extra test --extra dev
uv run ruff check src/ tests/
uv run ruff format --check src/ tests/
docker compose -f docker-compose.dev.yml up -d \
  opentaberna-db opentaberna-redis opentaberna-keycloak opentaberna-minio
uv run pytest tests/ -m "not integration and not slow"
```

Update the docs in the same PR as the change, not afterwards, and add a test that would
fail if your fix regressed.
