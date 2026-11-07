# Infrastructure as code pack

Applies to: Terraform (`.tf`, `.tfvars`, `.hcl`), Kubernetes YAML (`apiVersion:` + `kind:`), `Dockerfile`, `*.dockerfile`, `Containerfile` · Loaded by: code-review, security-review, implementer, verifier

Generic guidance only. Provider-specific services follow the repository's own modules and conventions. Never
apply, deploy or push to a live or shared environment while reviewing or verifying.

## Idioms to follow

- Terraform: pin the core version and every provider and module version; lock file committed.
- Terraform: remote state with locking; one state per environment or component, not one giant state.
- Terraform: typed variables with `description` and `validation`; `locals` for derived values; outputs that carry
  secrets marked `sensitive`.
- Terraform: `for_each` over `count` for collections (stable addresses); `moved` blocks when refactoring.
- Kubernetes: resource requests (and limits by repository policy) on every container.
- Kubernetes: readiness, liveness and, for slow starts, startup probes that check different things.
- Kubernetes: consistent labels; images by digest or immutable tag; config in ConfigMaps, secrets in Secret
  objects or an external secret mechanism.
- Dockerfile: minimal, pinned base image; multi-stage builds; dependency install before copying source for
  layer caching; `.dockerignore`.
- Dockerfile: `COPY` over `ADD` for local files; a non-root `USER`; exec-form `CMD`/`ENTRYPOINT`.

## Error-handling conventions

For infrastructure, "errors" are failed changes and bad rollouts.
- Read the plan before any apply; any `destroy` or forced replacement of stateful resources is called out.
- `lifecycle { prevent_destroy = true }` on stateful resources; `create_before_destroy` where downtime matters.
- Kubernetes rollouts: set `maxUnavailable`/`maxSurge`, a `PodDisruptionBudget`, and a graceful termination period.
- Shell-form `CMD` runs under `/bin/sh`, which does not forward signals; the app never sees `SIGTERM`.
- Misconfigured liveness probes cause restart loops under load; do not make them depend on downstream services.
- Rollback path stated: previous image tag, previous module version, or a reverse migration.

## Concurrency model and pitfalls

- Terraform state locking prevents concurrent applies; never disable it.
- Hidden ordering: use references to express dependencies; `depends_on` only for what references cannot show.
- More than one replica means the application must be stateless or use leader election.
- During a rolling update old and new versions run together; schemas and messages must be compatible both ways.
- An autoscaler and a fixed `replicas` field fight each other.
- `CronJob` needs a `concurrencyPolicy`; the default allows overlapping runs.

## Performance traps

- No resource requests: pods get packed onto busy nodes and are evicted first. Evidence: scheduler events.
- Tight CPU limits throttle latency-sensitive services. Evidence: throttling metrics.
- `COPY . .` before dependency install busts the layer cache on every change. Evidence: build time and cache hits.
- Large images from full base images and build tools left in the final stage. Evidence: image size and per-layer
  history from the container build tool.
- Large build context without `.dockerignore`.
- Huge Terraform states and many data-source lookups slow every plan. Evidence: plan duration.

## Security sinks and footguns

- `privileged: true`, `hostNetwork`, `hostPID`, `hostPath` mounts, added capabilities (CWE-250).
- Containers running as root; `allowPrivilegeEscalation` not set to `false`; writable root filesystem (CWE-250).
- Secrets in plain manifests, `.tfvars`, Dockerfile `ENV`/`ARG` (kept in image layers) (CWE-798, CWE-312).
- Terraform state holds secrets in plain text; it must be stored encrypted with tight access (CWE-312).
- Ingress or firewall rules open to `0.0.0.0/0` on admin or data ports (CWE-284).
- Wildcard RBAC verbs or resources; service account tokens mounted where not needed (CWE-269).
- Unpinned images (`:latest`), modules or providers from untrusted sources (CWE-829).
- `RUN curl ... | sh` without checksum verification (CWE-494).
- Storage and traffic without encryption at rest or in transit (CWE-311, CWE-319).
- Scanners when configured: `trivy`, `checkov`, `tfsec`, `kube-linter`.

## Testing conventions

- Terraform: `terraform fmt -check`, `terraform validate`, `tflint`, `terraform test` (1.6+); a `plan` against a
  disposable or mock setup only.
- Kubernetes: `kubeconform` (offline schema check), `kubectl apply --dry-run=client`, `helm lint` and
  `helm template` for charts, `kustomize build` for overlays.
- Dockerfile: `hadolint Dockerfile`, a local image build, and container structure tests where used.
- Policy-as-code tests (for example OPA/Conftest) if the repository has policies.

## Readability conventions

- `terraform fmt`; `yamllint` or Prettier for YAML; `hadolint` for Dockerfiles.
- Name resources by purpose, not by type; keep modules small with clear inputs and outputs.
- One Kubernetes object per document, separated by `---`, grouped by component.

## Things NOT to flag

- Attribute order and alignment — `terraform fmt` and the YAML formatter own them.
- `count = var.enabled ? 1 : 0` for a simple on/off resource; that is standard.
- Unpinned OS package versions in `apt-get install` unless the repository pins them; the base image digest is the
  reproducibility anchor.
- `:latest` or mutable tags in local-only development files.
- Long but flat YAML; repetition that the repository chose over templating.
