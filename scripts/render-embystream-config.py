#!/usr/bin/env python3
import os
import re
import secrets
import string
import sys
from pathlib import Path
from string import Template


if len(sys.argv) != 4:
    raise SystemExit("render-embystream-config.py ENV TEMPLATE OUTPUT")

env_path, template_path, output_path = map(Path, sys.argv[1:])
values = {}
for raw_line in env_path.read_text(encoding="utf-8").splitlines():
    line = raw_line.strip()
    if not line or line.startswith("#"):
        continue
    if "=" not in line:
        raise SystemExit(f"无效配置行：{raw_line}")
    key, value = line.split("=", 1)
    values[key.strip()] = value.strip()

required = [
    "EMBY_TOKEN",
    "GOOGLE_CLIENT_ID",
    "GOOGLE_CLIENT_SECRET",
    "GOOGLE_DRIVE_ID",
    "GOOGLE_ACCESS_TOKEN",
    "GOOGLE_REFRESH_TOKEN",
    "PUBLIC_BASE_URL",
]
missing = [key for key in required if not values.get(key)]
if missing:
    raise SystemExit(
        "请先填写 /root/docker-compose/embystream/.env.private："
        + ", ".join(missing)
    )

generated = []
alphabet = string.ascii_letters + string.digits
for key in ("EMBYSTREAM_ENCIPHER_KEY", "EMBYSTREAM_ENCIPHER_IV"):
    if not values.get(key):
        values[key] = "".join(secrets.choice(alphabet) for _ in range(16))
        generated.append(key)

if generated:
    with env_path.open("a", encoding="utf-8", newline="\n") as env_file:
        if env_path.stat().st_size:
            env_file.write("\n")
        for key in generated:
            env_file.write(f"{key}={values[key]}\n")
    os.chmod(env_path, 0o600)
    print("已在 .env.private 中生成 EmbyStream 本机加密密钥。")

for key, value in values.items():
    if "\n" in value or "\r" in value or '"' in value:
        raise SystemExit(f"{key} 包含不支持的字符")

rendered = Template(
    template_path.read_text(encoding="utf-8")
).substitute(values)
output_path.write_text(rendered, encoding="utf-8")
os.chmod(output_path, 0o600)
print(f"已生成 {output_path}")

