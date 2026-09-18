# Toolchain Reference

Commands per stack for the Phase 1 baseline and the Phase 2 sweeps. Run what exists; never invent a command and report its output. `scripts/recon.py` prints which of these are actually available in the repo.

> **Read-only caveat.** Several commands below write into the tree: dependency installs create `node_modules/`, `vendor/`, `.venv/`; builds create `dist/`, `target/`, `__pycache__/`; test runs can touch a dev database or the network. Run them in a disposable copy (`git worktree add /tmp/review-copy HEAD`), or ask once for permission covering all of them. Linters, type checkers, static analysis and manifest-reading audits are safe in place. `integrity.py check` is what settles the question afterwards.

Rule of thumb for every stack: **the type checker and the linter find in seconds what a manual read finds in an hour** - run them before reading code, and treat their output as leads to verify rather than findings to report. A linter warning becomes a finding only once you can say what breaks.

## JavaScript / TypeScript

```bash
npm ci || npm install            # or pnpm i --frozen-lockfile / yarn --immutable
npm run build
npm test -- --run                # vitest; jest: npx jest --ci
npx tsc --noEmit                 # type errors are the single highest-yield scan in TS
npx eslint . --max-warnings=0
npm audit --audit-level=high     # or: pnpm audit / yarn npm audit
npx depcheck                     # unused + missing deps
```
Traps: `any` and `as` casts hiding real type errors (`rg -n ' as any| as unknown as '`); `strict: false` in tsconfig, which silently disables null checking across the project - check this first, it changes what every other finding means; `@ts-ignore`/`@ts-expect-error` comments; `--passWithNoTests` masking an empty suite; ESLint config that disables `no-floating-promises`.

## Python

```bash
pip install -r requirements.txt   # or: poetry install / uv sync
pytest -q
pytest --cov --cov-report=term-missing
mypy .                            # or: pyright
ruff check .                      # or: flake8 / pylint
bandit -r . -ll                   # security-focused static analysis
pip-audit                         # or: safety check
```
Traps: `except Exception` everywhere; mutable default arguments; `assert` used for validation (stripped under `-O`); circular imports masked by local imports; `__eq__` without `__hash__`; `datetime.now()` without tz; f-strings in SQL.

## Go

```bash
go build ./...
go vet ./...
go test ./... -race -count=1      # -race is the highest-value flag in this stack
go test ./... -cover
staticcheck ./...
govulncheck ./...
```
Traps: ignored errors (`_ =`); loop-variable capture in goroutines (pre-1.22); `defer` inside a loop; nil map writes; slice aliasing after `append`; context not propagated or never cancelled.

## Java / Kotlin

```bash
./mvnw -q verify        # or: ./gradlew build
./mvnw test             # or: ./gradlew test
./mvnw spotbugs:check   # or: gradle spotbugs / errorprone
./mvnw dependency-check:check   # OWASP dependency check
```
Traps: `catch (Exception e) {}`; `equals` without `hashCode`; mutable static state; `SimpleDateFormat` shared across threads; `@Transactional` on a private or self-invoked method (silently does nothing); Lazy loading outside a session.

## PHP

```bash
composer install
./vendor/bin/phpunit
./vendor/bin/phpstan analyse --level=8
./vendor/bin/psalm
composer audit
```
Traps: `==` vs `===` (type juggling); unserialize on user input; `$_REQUEST`; raw `DB::raw` / string-built queries in Laravel; mass assignment without `$fillable`.

## Ruby

```bash
bundle install
bundle exec rspec        # or: rake test
bundle exec rubocop
bundle exec brakeman -A  # Rails security scanner
bundle exec bundler-audit check --update
```
Traps: `rescue nil`; `rescue Exception`; mass assignment; `find_by_sql` with interpolation; N+1 from missing `includes` (run with `bullet` enabled).

## Rust

```bash
cargo build --all-targets
cargo test
cargo clippy -- -D warnings
cargo audit
```
Traps: `unwrap()`/`expect()` on paths that can legitimately fail; `unsafe` blocks; panics in library code; blocking calls inside async.

## C# / .NET

```bash
dotnet restore && dotnet build -warnaserror
dotnet test
dotnet list package --vulnerable --include-transitive
```
Traps: `async void`; `.Result`/`.Wait()` deadlocks; `catch (Exception) {}`; `IDisposable` not disposed; EF Core lazy loading in loops.

## Cross-stack, language-agnostic

```bash
# secret scanning (history, not just working tree)
gitleaks detect --no-git=false || trufflehog filesystem .
# multi-language static analysis with a good rule set
semgrep --config=auto --severity=ERROR --severity=WARNING
# container / IaC
trivy fs . ; hadolint Dockerfile ; checkov -d .
# churn-based hotspots when git is available
git log --since=1.year --name-only --pretty=format: | sort | uniq -c | sort -rn | head -40
```

Semgrep with `--config=auto` is the best single cross-language starting point: fast, low setup, and its rules encode many of the patterns in `detection-playbook.md`. Treat its output as leads. Budget for its false-positive rate by verifying each hit against the code before it enters the ledger as `Confirmed` - an unverified scanner dump pasted into a report is exactly the noise that makes teams stop reading reports.

## Property-based testing, per stack

Pass BL leans on these, because example-based tests are chosen by the same person holding the same wrong assumption as the bug. Install the one matching the stack before starting Pass BL - writing three properties for the money path is usually a better hour than reading another module.

| Stack | Library | Install |
|---|---|---|
| Python | Hypothesis | `pip install hypothesis` |
| JS / TS | fast-check | `npm i -D fast-check` |
| Java / Kotlin | jqwik | Maven/Gradle test dependency |
| Go | `testing/quick`, gopter, rapid | `go get pgregory.net/rapid` |
| Rust | proptest, quickcheck | `cargo add --dev proptest` |
| Ruby | rantly, propcheck | `gem install propcheck` |
| PHP | Eris | `composer require --dev giorgiosironi/eris` |
| C# | FsCheck | `dotnet add package FsCheck.Xunit` |

Start with the properties that the OOPSLA 2025 study found most effective: assert what must *raise* on invalid input (113x more likely to catch a mutation than an average test), what must be *included* in a result, and what *type or shape* the output must have. Most catches come from the first generated input, so a property that is quick to state is usually worth stating.

## When tooling cannot run

If dependencies will not install, services are unavailable, or the platform is unsupported: record the exact failure in the ledger, proceed with static analysis and reading, and label every finding `Suspected` unless a code trace confirms it. Say so in the report. A static-only sweep with honest labels is a real deliverable; a sweep that implies it executed the code when it did not is a fabrication.
