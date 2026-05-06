# Contributing

Contributions must preserve safe defaults and auditability. New providers implement `AIProvider`. New brokers implement `Broker`. New execution paths require tests proving risk rejection prevents broker calls.

Do not commit secrets, broker credentials, generated approval files, or audit logs.

