# Atlas Agent VPS Deployment

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
