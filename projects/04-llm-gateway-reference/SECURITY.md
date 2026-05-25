# Security

## Secret management

This gateway never stores secrets in version control:

- The OpenAI API key lives in `.env` (gitignored — see `.env.example` for the
  template).
- Application code wraps the key in `pydantic.SecretStr` and only calls
  `.get_secret_value()` at the single point of use — provider construction
  in [`app/providers/registry.py`](app/providers/registry.py). The key is
  redacted from `repr()` / `str()` / log dumps everywhere else.
- No key, header, or auth material ever lands in the verification artefacts
  under `docs/verification/` — those record only the gateway's public
  response envelope plus the test inputs.

## Pre-commit gates

The hooks in [`.pre-commit-config.yaml`](.pre-commit-config.yaml) enforce
the secret-management posture above:

| Hook | Purpose |
|---|---|
| `detect-secrets` | Block accidental commits of API keys, tokens, and high-entropy strings. Baseline in `.secrets.baseline`. |
| `check-added-large-files` | Block files over 500 KB. |
| `ruff` / `ruff-format` | Lint + format Python. |
| Standard hygiene hooks | Trailing whitespace, EOF newlines, YAML / TOML syntax, merge-conflict markers. |

First-time setup after cloning:

```bash
pip install -r requirements-dev.txt
pre-commit install               # wire the hook into .git/hooks
pre-commit run --all-files       # one-off check across the tree
```

## Triaging a `detect-secrets` finding

When `pre-commit` blocks a commit with a `detect-secrets` failure, the hook
prints the file path and the secret type. The two correct responses:

### False positive

Examples: a high-entropy test fixture string, an example token in
documentation, a Base64-encoded fixture payload.

```bash
detect-secrets audit .secrets.baseline
# Interactive triage — mark the finding as "not a secret".
git add .secrets.baseline
git commit -m "chore: triage detect-secrets baseline"
```

After the audit, the baseline records the finding as known and pre-commit
will allow the original file through.

### True positive

A **real key was about to be committed.** Treat the key as compromised even
if the commit never landed — assume it touched disk and shell history.
Rotate immediately:

1. **Revoke** the key in the provider dashboard. For OpenAI:
   Settings → API Keys → Revoke.
2. **Generate a fresh** project-scoped key with the same `$10` hard cap and
   "Restricted" permission level. Paste it into `.env`.
3. **Unstage and scrub** the file:
   ```bash
   git restore --staged <file>
   # then edit <file> to remove the literal secret
   ```
4. If the key had been pushed in earlier history, follow GitHub's guide on
   [removing sensitive data from a repository](https://docs.github.com/en/authentication/keeping-your-account-and-data-secure/removing-sensitive-data-from-a-repository).
   For a private project repo, `git push --force-with-lease` after a
   filter-repo rewrite. For a public repo, **assume the key is harvested**
   even after rewrite — rotation is the only defence that matters.

## Live OpenAI verification

The opt-in `tests/live/` suite exercises the real OpenAI endpoint. See the
[Live tests (opt-in)](README.md#live-tests-opt-in) section of the README and
the committed artefacts under `docs/verification/`. The suite skips cleanly
if `OPENAI_API_KEY` is absent, so it never breaks CI.

## Reporting

This is a personal portfolio project. For security concerns, contact the
maintainer via the email on the GitHub profile.
