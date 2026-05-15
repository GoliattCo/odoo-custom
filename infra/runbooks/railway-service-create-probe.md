# Railway `serviceCreate` GraphQL probe (Phase 3 prework, 2026-05-15)

Verifies assumption-1 from the Phase 3 design block: Railway's GraphQL `serviceCreate` mutation supports creating Dockerfile-source services for our per-tenant exclusive-tier postgres + odoo deployables.

## TL;DR — assumption HOLDS, with a 2-step pattern

`serviceCreate` does NOT accept a Dockerfile path inline. The shape that works is:

```
serviceCreate(input: { projectId, name, source: { repo: "<owner>/<repo>" }, variables: { … } })
  → returns Service with id
serviceInstanceUpdate(serviceId, environmentId, input: {
  dockerfilePath: "infra/postgres/Dockerfile",
  builder: RAILPACK,
  railwayConfigFile: "infra/railway/postgres-exclusive/railway.toml",
  restartPolicyType: ON_FAILURE,
  restartPolicyMaxRetries: 5,
  watchPatterns: ["infra/postgres/**"],
})
```

Pattern verified earlier in this project: that's exactly what made the pgbouncer service build correctly when Railpack's autodetect was choosing the wrong Dockerfile (commit `0dbec542` deployment, 2026-05-15).

## Full schema introspection

### `serviceCreate` input

`ServiceCreateInput`:
- `projectId: String!` — required
- `name: String` — service display name
- `environmentId: String` — when set to a forked env, service lives only there; otherwise lands in all non-forked envs
- `source: ServiceSourceInput` — what to deploy. `ServiceSourceInput` has ONLY:
  - `image: String` — Docker image reference (registry-hosted)
  - `repo: String` — `owner/repo` GitHub reference
  - **No `dockerfile` / `dockerfilePath` field.** Confirms the 2-step pattern is mandatory.
- `variables: EnvironmentVariables` — scalar JSON map `{ KEY: "value", ... }`. Set env atomically at create-time.
- `templateId` + `templateServiceId` — template-based path (alternative to source).
- `registryCredentials: RegistryCredentialsInput` — for private registries.
- `icon`, `branch` — cosmetic / git-branch.

### `serviceInstanceUpdate` input

`ServiceInstanceUpdateInput` (post-create configuration):
- `buildCommand: String`
- `builder: Builder` — enum: `HEROKU | NIXPACKS | PAKETO | RAILPACK`. **No `DOCKERFILE` value.** Workaround we already use: set `builder: RAILPACK` + a `railwayConfigFile` toml that contains `[build] dockerfilePath = "..."` — the toml overrides Railpack's autodetect.
- `dockerfilePath: String` — alone, this is IGNORED by Railpack autodetect (we hit this with pgbouncer). Must be combined with `railwayConfigFile`.
- `railwayConfigFile: String` — path to a toml; this is the load-bearing config knob.
- `rootDirectory: String`
- `region: String` — placement region.
- `numReplicas: Int`
- `restartPolicyType: RestartPolicyType` — enum (likely `ALWAYS | ON_FAILURE | NEVER`).
- `restartPolicyMaxRetries: Int`
- `healthcheckPath: String`, `healthcheckTimeout: Int`
- `cronSchedule: String` — for cron-flavored services (not relevant here)
- `drainingSeconds: Int`, `overlapSeconds: Int` — rolling-restart knobs
- `ipv6EgressEnabled: Boolean`
- `multiRegionConfig: JSON`, `nixpacksPlan: JSON` — JSON blobs for advanced config
- `preDeployCommand: [...]` — list type
- `registryCredentials: RegistryCredentialsInput`
- `sleepApplication: Boolean`
- `source: ServiceSourceInput` — can re-set image/repo
- `startCommand: String`
- `watchPatterns: [...]` — list of glob patterns that trigger rebuilds

### Other useful mutations seen in passing

- `serviceConnect(id, input: ServiceConnectInput!)` — connect an existing service to a source/repo after-the-fact
- `variableUpsert(input: VariableUpsertInput!)` — set a single env var atomically; we already use this routinely

## Recommended pattern for Phase 3.0

### Decision: `source.repo` + static toml per service type, NOT `source.image`

Two viable paths for Dockerfile-based deployments via `serviceCreate`:

| Path | Pros | Cons |
|---|---|---|
| `source.repo` + static toml + `serviceInstanceUpdate` | No CI changes; same path the pgbouncer service uses today; per-tenant config emerges from env vars not toml files | Repo cloned per service (extra build time on each create) |
| Pre-build images, push to GHCR, `source.image` | One pull per deploy (faster); cleaner separation of build vs deploy; matches cloud-native standard | Needs CI changes (GHCR push + tag on main), Railway registry credentials, image-tag rollout discipline |

Pick `source.repo` + static toml for Phase 3.0. Revisit `source.image` if build times become a bottleneck (likely at ~30+ exclusive tenants).

### Static toml files needed

```
infra/railway/postgres-exclusive/railway.toml
  [build]
  dockerfilePath = "infra/postgres/Dockerfile"
  [deploy]
  restartPolicyType = "ON_FAILURE"
  restartPolicyMaxRetries = 5

infra/railway/odoo-exclusive/railway.toml
  [build]
  dockerfilePath = "Dockerfile"
  [deploy]
  restartPolicyType = "ON_FAILURE"
  restartPolicyMaxRetries = 5
  healthcheckPath = "/saas/health"
```

ALL exclusive postgres services point at the first toml; ALL exclusive odoo services point at the second. Per-tenant config (db_name, secrets, region) flows through `variables` at `serviceCreate` time.

### Pseudo-code for `RailwayProvider.deployOdooInstance(spec)`

```ts
async deployOdooInstance(spec: OdooInstanceSpec): Promise<DeploymentId> {
  // For the EXCLUSIVE tier, spec.tier === 'exclusive' and the workflow is
  // creating a NEW service. spec carries: slug, dbName, region, image (unused
  // for repo-source), cpu/memory (Railway doesn't expose these via GraphQL,
  // baseline service plan governs sizing — flag below), envSecrets.
  const serviceName = `odoo-${spec.slug}`;
  const create = await this.graphql<{ serviceCreate: { id: string } }>(
    `mutation Create($i: ServiceCreateInput!) {
       serviceCreate(input: $i) { id name }
     }`,
    { i: {
        projectId: this.projectId,
        name: serviceName,
        source: { repo: this.repoFullName },         // "<owner>/Odoo"
        variables: spec.envSecrets,                   // EnvironmentVariables scalar
        environmentId: this.environmentId,            // pin to production env
    }},
  );
  const serviceId = create.serviceCreate.id;

  await this.graphql(
    `mutation Update($s: String!, $e: String, $i: ServiceInstanceUpdateInput!) {
       serviceInstanceUpdate(serviceId: $s, environmentId: $e, input: $i)
     }`,
    { s: serviceId, e: this.environmentId, i: {
        builder: 'RAILPACK',
        railwayConfigFile: 'infra/railway/odoo-exclusive/railway.toml',
        dockerfilePath: 'Dockerfile',
        healthcheckPath: '/saas/health',
        restartPolicyType: 'ON_FAILURE',
        restartPolicyMaxRetries: 5,
        region: spec.region,                          // 'us-east4-eqdc4a' etc
        // CPU/memory NOT settable here — see flag below
    }},
  );

  return serviceId;
}
```

### Things this probe did NOT verify (flagged for the implementation pass)

1. **CPU + memory limits** are not in `ServiceInstanceUpdateInput`. Railway's GraphQL appears to gate this through the service-plan side, not per-service config. Need to confirm whether per-service CPU/RAM caps are configurable via GraphQL at all, or whether sizing is tied to the project's billing plan. Fly has explicit `guest.cpus + memory_mb` in `machines.create`; Railway parity here might require a different approach. Possibly we accept "Railway exclusive = same machine size as shared" and use Fly when a tenant needs custom sizing.

2. **Postgres volume attachment.** Railway services can attach a persistent volume via the dashboard, but the GraphQL `volumeCreate` / `volumeAttach` mutations weren't probed here. Per-tenant exclusive Postgres needs persistent storage — confirm before the Phase 3.0 implementation chunk.

3. **`serviceCreate` race with first deploy.** Railway typically starts an initial build immediately after `serviceCreate`, BEFORE `serviceInstanceUpdate` lands. This may produce a failed-build deployment on the wrong Dockerfile. Test: create a throwaway service, observe deployment timeline, confirm whether we need to `serviceInstanceUpdate` followed by an explicit redeploy mutation to land the right build.
