# Deployment Guidance

Every project should be easy to build, configure, and deploy from day one. **Don't let deployment become an afterthought** — bake it into the project structure as you build.

---

## Core Principles

1. **Deployability is a feature.** If the code works locally but can't be deployed easily, it's not done.
2. **Automate everything repeatable.** Builds, tests, linting, and deployments should be runnable with a single command.
3. **Externalize configuration.** Never hardcode environment-specific values (URLs, credentials, ports, feature flags). Use environment variables, config files, or secret managers.
4. **Make the default path work.** A new developer should be able to clone the repo and get running with minimal setup. Document any prerequisites.
5. **Fail fast and visibly.** Validate required config at startup, not at the point of first use deep in the application.

---

## When to Raise Deployment Concerns

- **New dependency added** → Does it require system-level packages, native binaries, or specific runtime versions? Note the impact on build/deploy.
- **New environment variable or config** → Suggest adding it to `.env.example`, `docker-compose.yml`, and/or documentation.
- **New feature with external dependency** → Consider how it behaves when the dependency is unavailable (graceful degradation, health checks).
- **Project initialization** → Suggest including a `Dockerfile`, `docker-compose.yml`, or equivalent from the start.
- **Database schema changes** → Suggest a migration strategy (migration files, seed scripts).
- **Multi-service architecture** → Suggest service discovery, health endpoints, and local development orchestration.

---

## Environment Configuration

### The Twelve-Factor App Approach

- Store config in environment variables, not in code.
- Provide a `.env.example` (or equivalent) checked into source control with placeholder values and comments.
- Never commit `.env`, secrets, or credentials to version control.
- Validate all required environment variables at application startup.

### Language-Specific Config Patterns

| Language | Common Pattern |
|---|---|
| Python | `python-dotenv` + `os.environ`, Pydantic `BaseSettings` |
| Node.js | `dotenv` + `process.env`, or framework config (e.g., Next.js built-in) |
| Java/Spring | `application.yml` + `@Value` / `@ConfigurationProperties` |
| .NET | `appsettings.json` + `IConfiguration` |
| Go | `os.Getenv()`, `envconfig`, or `viper` |

---

## Containerization

When a project doesn't have containerization and would benefit from it, suggest it:

- **Dockerfile** — Use multi-stage builds to keep images small. Pin base image versions. Don't run as root.
- **docker-compose.yml** — For local development with databases, caches, or other services.
- **.dockerignore** — Exclude `node_modules/`, `.git/`, build artifacts, `.env`.

### Dockerfile Principles

1. Use official, specific base images (e.g., `python:3.12-slim`, not `python:latest`).
2. Copy dependency manifests first, install, then copy source — this maximizes layer caching.
3. Use a non-root user for the runtime stage.
4. Expose only the ports the application needs.
5. Use `HEALTHCHECK` where appropriate.

---

## CI/CD Pipeline

Every project should have automated checks that run on every push or pull request. If none exists, suggest one.

### Minimum Viable Pipeline

1. **Install dependencies**
2. **Lint / format check**
3. **Run tests**
4. **Build** (if applicable)

### Suggested Platforms

| Platform | Config File | Common For |
|---|---|---|
| GitHub Actions | `.github/workflows/*.yml` | GitHub-hosted repos |
| GitLab CI | `.gitlab-ci.yml` | GitLab-hosted repos |
| Azure DevOps | `azure-pipelines.yml` | Azure / enterprise |
| Jenkins | `Jenkinsfile` | Self-hosted enterprise |

### What to Automate Beyond Tests

- **Dependency vulnerability scanning** (Dependabot, Snyk, `npm audit`, `pip-audit`)
- **Container image scanning** (Trivy, Grype)
- **Deployment to staging** on merge to main
- **Release tagging** and changelog generation

---

## Build Scripts

- Define a clear `build` command in the project's package manager (`npm run build`, `python -m build`, `./gradlew build`, `dotnet publish`, `go build`).
- If the build requires specific steps, document them in a `Makefile`, `justfile`, or equivalent task runner.
- Ensure the build is reproducible — pin dependency versions with a lockfile (`package-lock.json`, `poetry.lock`, `go.sum`, etc.).

---

## Health and Readiness

For services (web apps, APIs, workers), suggest:

- **Health endpoint** (`/health` or `/healthz`) — returns 200 when the service is alive.
- **Readiness endpoint** (`/ready`) — returns 200 when the service can accept traffic (database connected, caches warm, etc.).
- **Graceful shutdown** — handle SIGTERM, finish in-flight requests, close connections, then exit.

---

## Secrets Management

- **Never commit secrets.** Use `.gitignore` for `.env`, credentials files, and key material.
- For production: use platform-native secret managers (AWS Secrets Manager, Azure Key Vault, GCP Secret Manager, HashiCorp Vault).
- For local development: use `.env` files or a local secrets manager.
- Rotate secrets on a schedule and on suspected compromise.

---

## Checklist

When you produce or modify code, verify:

- [ ] The project can be built with a single command
- [ ] Environment-specific config is externalized (not hardcoded)
- [ ] `.env.example` or equivalent documents required configuration
- [ ] No secrets are committed to version control
- [ ] A CI pipeline exists (or is suggested) that runs lint + tests + build
- [ ] Dependency versions are pinned via lockfile
- [ ] If applicable, a Dockerfile or container config exists and follows best practices
- [ ] README documents how to build, run, and deploy the project

