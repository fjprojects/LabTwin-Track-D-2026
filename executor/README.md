# Optional isolated code worker

The legacy local runner remains available for trusted development/demo examples. It executes student code as the Django process's user and is unsuitable for public untrusted submissions. This worker integration routes **both original and new** lab tests to a separate execution host.

On a dedicated host with a current, hardened Docker Engine:

```bash
docker build -t labtwin-code-runtime executor/
export LABTWIN_RUNNER_SECRET='<a-long-random-secret>'
python executor/service.py
```

The service binds to localhost:8090 by default. Put it behind a private TLS reverse proxy if accessed across hosts. Restrict access to the application server. Do not put the Docker socket, application database, credentials or uploaded sources in job containers, and do not mount the socket into the Django app.

Set the corresponding backend variables:

```text
LABTWIN_RUNNER_URL=https://your-private-worker
LABTWIN_RUNNER_SECRET=<the-same-secret>
```

Each authenticated request runs one fresh container, compiles once, and evaluates up to 20 inputs. Expected outputs stay in Django and are compared there. Containers run as UID/GID 65534 with no network, a read-only root filesystem, dropped capabilities, no new privileges, one CPU, 256 MiB memory, 64-process limit, and a 64 MiB temporary filesystem. Subprocess CPU/file limits and timeouts bound individual runs. The service limits concurrent jobs to four and removes the named container even after a client/worker timeout. Runtime data is ephemeral.

This is a standard container isolation layer, not a guarantee against kernel/container-engine vulnerabilities. Maintain the host and isolate it from application data and the rest of your infrastructure. The included runtime is Linux-specific. Docker availability/container launch must be verified on the target host; API-contract tests do not claim to exercise a Docker engine when one is unavailable.

The API is `POST /execute` with a bearer worker secret and `{code, language, inputs}`. It returns `{executions:[{success,stdout,stderr}]}`. `/health` returns a service identifier. No student identity or answer key is sent. Do not expose this service as a public unauthenticated code endpoint. Worker failures retain the student's saved attempt without mastery credit.
