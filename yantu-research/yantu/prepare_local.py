"""Prepare a private, local Plane configuration from the bundled v1.4.2 template.

Run from any directory with: python3 yantu/prepare_local.py
"""

from pathlib import Path
import os
import re
import secrets


root = Path(__file__).resolve().parent.parent
template = root / "plane.env.example"
destination = root / "plane.env"

if destination.exists():
    raise SystemExit(f"{destination} already exists. Keep your settings; no file was changed.")

if not template.is_file():
    raise SystemExit(f"Missing {template}; extract the full local bundle first.")

postgres_password = secrets.token_hex(32)
rabbitmq_password = secrets.token_hex(32)
values = {
    "APP_RELEASE": "v1.4.2",
    "APP_DOMAIN": "plane.lab.test",
    "SITE_ADDRESS": "http://plane.lab.test",
    "WEB_URL": "http://plane.lab.test",
    "CORS_ALLOWED_ORIGINS": "http://plane.lab.test",
    "CERT_EMAIL": "",
    "POSTGRES_PASSWORD": postgres_password,
    "DATABASE_URL": f"postgresql://plane:{postgres_password}@plane-db/plane",
    "SECRET_KEY": secrets.token_hex(32),
    "LIVE_SERVER_SECRET_KEY": secrets.token_hex(32),
    "RABBITMQ_PASSWORD": rabbitmq_password,
    "AMQP_URL": f"amqp://plane:{rabbitmq_password}@plane-mq:5672/plane",
    "AWS_SECRET_ACCESS_KEY": secrets.token_hex(32),
    "YANTU_SITE_ADDRESS": "http://research.lab.test",
    "INTERNAL_BIND_IP": "127.0.0.1",
    "YANTU_DATABASE_URL": f"postgresql+psycopg://plane:{postgres_password}@plane-db:5432/plane",
    "PLANE_API_KEY": "",
    "PLANE_ALLOWED_PROJECTS": "",
    "AI_BASE_URL": "http://ollama:11434",
    "AI_MODEL": "qwen2.5:3b",
}

seen = set()
lines = []
for line in template.read_text(encoding="utf-8").splitlines():
    match = re.match(r"^([A-Z][A-Z0-9_]*)=", line)
    if match and match.group(1) in values:
        key = match.group(1)
        if key in seen:
            raise SystemExit(f"Duplicate key in template: {key}")
        lines.append(f"{key}={values[key]}")
        seen.add(key)
    else:
        lines.append(line)

lines += [f"{key}={value}" for key, value in values.items() if key not in seen]
fd = os.open(destination, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
with os.fdopen(fd, "w", encoding="utf-8") as output:
    output.write("\n".join(lines) + "\n")

print("Created plane.env with random secrets for local testing.")
print("Do not publish plane.env or send it in a screenshot.")
