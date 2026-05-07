# Remote Routines

Remote routines are stateless runs against a cloned repository. Each run reads Markdown memory, uses configured environment variables, executes `atlas routine run <name> --mode paper`, writes reports, updates memory, optionally sends ClickUp notifications, and optionally commits/pushes changes.

Do not store keys in the repo. Configure keys in the remote runtime. Start with paper mode and keep `ALLOW_GIT_PUSH=false` until reviewed.

