# Dashboard Security

The Atlas dashboard is implemented exclusively as a **static site generator**. 

## Static Generation
The command `atlas dashboard` collects local state and renders an `index.html` file in the `.atlas/dashboard` directory. 
There is **no built-in web server**, no active listening port, and no runtime API exposed by the dashboard.

## Security Invariants

### 1. Localhost Bind
Because there is no active web server bundled, Atlas does not bind to any network interface (neither `127.0.0.1` nor `0.0.0.0`). The user must rely on the `file://` protocol or provide their own web server to serve the generated static files. Any third-party web server used by the operator should be explicitly configured to bind to `localhost` unless public exposure is intended and secured.

### 2. Read-Only Surface
The generated dashboard provides a purely read-only view of the agent's state, logs, and configuration. It does not contain any form inputs or API endpoints capable of mutating state, submitting orders, or modifying configuration.

### 3. Secret Redaction
The dashboard generator actively redacts sensitive environment variables, provider credentials, and broker API keys before rendering the HTML. Test coverage (`test_dashboard_security.py`) enforces that fake secrets and live API keys do not leak into the generated output.
