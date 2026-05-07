FROM python:3.12-slim

WORKDIR /app
COPY . /app
RUN python -m pip install --no-cache-dir -e . --no-build-isolation

CMD ["atlas", "agent", "run", "--continuous"]
