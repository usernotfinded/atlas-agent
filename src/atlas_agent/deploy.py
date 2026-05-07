from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class GeneratedFile:
    path: Path
    created: bool


DOCKERFILE = """FROM python:3.12-slim

WORKDIR /app
COPY . /app
RUN python -m pip install --no-cache-dir -e . --no-build-isolation

CMD ["atlas", "agent", "run", "--continuous"]
"""


DOCKER_COMPOSE = """services:
  atlas-agent:
    build:
      context: ..
      dockerfile: deploy/Dockerfile
    command: ["atlas", "agent", "run", "--continuous"]
    env_file:
      - ../.env
    volumes:
      - ../memory:/app/memory
      - ../reports:/app/reports
      - ../pending_orders:/app/pending_orders
      - ../audit:/app/audit
    restart: unless-stopped
"""


SYSTEMD_SERVICE = """[Unit]
Description=Atlas Agent
After=network-online.target
Wants=network-online.target

[Service]
Type=simple
WorkingDirectory=/opt/atlas-agent
EnvironmentFile=-/etc/atlas-agent/atlas-agent.env
ExecStart=/usr/local/bin/atlas agent run --continuous
Restart=on-failure
RestartSec=30

[Install]
WantedBy=multi-user.target
"""


VPS_README = """# Atlas Agent VPS Deployment

Atlas Agent is designed for lightweight VPS deployments depending on provider,
workload, and model choices.

Typical flow:

1. Clone the repository on the VPS.
2. Install Python and create an isolated environment.
3. Store secrets in a local env file outside git.
4. Run `atlas validate`.
5. Use Docker Compose or the generated systemd service to run
   `atlas agent run --continuous`.
6. Use Telegram as an optional remote control plane with allowed user IDs.
"""


SERVERLESS_README = """# Atlas Agent Serverless Jobs

Use serverless jobs for scheduled research, simulation, learning, and reporting
cycles. Keep broker credentials in the provider secret store and keep live
execution behind the same approval and risk gates used by local runs.

Suggested jobs:

- market-session status check
- closed-market learning cycle
- pre-market research cycle
- report and memory sync
"""


GPU_CLUSTER_README = """# Atlas Agent GPU Cluster Deployment

GPU clusters are optional and only needed for local heavy models or custom
research pipelines. Broker execution remains adapter-based and still passes
through deterministic risk gates, approval policy, kill-switch checks, and audit
logging.

Keep model workers separate from broker credentials when possible.
"""


DEPLOYMENT_FILES = {
    "docker": {
        Path("deploy/Dockerfile"): DOCKERFILE,
        Path("deploy/docker-compose.yml"): DOCKER_COMPOSE,
    },
    "systemd": {
        Path("deploy/systemd/atlas-agent.service"): SYSTEMD_SERVICE,
    },
    "vps": {
        Path("deploy/vps/README.md"): VPS_README,
    },
    "serverless": {
        Path("deploy/serverless/README.md"): SERVERLESS_README,
    },
    "gpu-cluster": {
        Path("deploy/gpu-cluster/README.md"): GPU_CLUSTER_README,
    },
}


def ensure_deploy_files(kind: str, base_dir: Path | None = None) -> list[GeneratedFile]:
    base = base_dir or Path.cwd()
    if kind not in DEPLOYMENT_FILES:
        raise ValueError(f"unknown deploy target: {kind}")

    generated: list[GeneratedFile] = []
    for relative_path, content in DEPLOYMENT_FILES[kind].items():
        path = base / relative_path
        created = not path.exists()
        if created:
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(content, encoding="utf-8")
        generated.append(GeneratedFile(path=path, created=created))
    return generated
