# GPU Cluster

GPU clusters are optional. They are useful when Atlas Agent uses local heavy
models or custom research pipelines. The broker execution path should stay in
the main Atlas process and continue to use broker adapters, deterministic risk
gates, approval policy, kill-switch checks, and audit logs.

Recommended boundary:

- GPU workers handle model inference and research jobs.
- Atlas Agent handles memory, strategy validation, risk checks, order routing,
  approval policy, and broker execution.

Keep cluster workers stateless where possible. Pass only the minimum prompt,
market context, and task payload needed for inference, and keep provider keys,
broker keys, Telegram tokens, and account credentials out of worker logs.
