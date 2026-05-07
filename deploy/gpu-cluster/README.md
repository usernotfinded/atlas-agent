# Atlas Agent GPU Cluster Deployment

GPU clusters are optional and only needed for local heavy models or custom
research pipelines. Broker execution remains adapter-based and still passes
through deterministic risk gates, approval policy, kill-switch checks, and audit
logging.

Keep model workers separate from broker credentials when possible.
