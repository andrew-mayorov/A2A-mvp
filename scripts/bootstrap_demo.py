from __future__ import annotations

import json
import os
import secrets
from pathlib import Path

from sber_a2a.config import RuntimeConfig
from sber_a2a.shared.security.signatures import Ed25519SignatureProvider


def main() -> None:
    runtime = RuntimeConfig.load(os.environ["RUNTIME_CONFIG_FILE"])
    output = Path(os.environ["BOOTSTRAP_OUTPUT_DIR"])
    output.mkdir(mode=0o700, parents=True, exist_ok=True)
    password_file = output / "database_password"
    if not password_file.exists():
        password_file.write_text(secrets.token_urlsafe(32), encoding="utf-8")
        password_file.chmod(0o644)

    agents = [runtime.profile.buyer_agent_id, *(item.agent_id for item in runtime.suppliers)]
    index: dict[str, dict[str, str]] = {}
    for agent_id in agents:
        safe_name = __import__("hashlib").sha256(agent_id.encode()).hexdigest()[:24]
        private_path = output / f"{safe_name}.private.pem"
        public_path = output / f"{safe_name}.public.pem"
        if not private_path.exists() or not public_path.exists():
            provider = Ed25519SignatureProvider.generate(f"{agent_id}:v1")
            provider.write_private_key(private_path)
            provider.write_public_key(public_path)
            try:
                private_path.chmod(0o640)
                os.chown(private_path, 0, 10001)
            except OSError:
                # Rootless user namespaces can deny chown. Preserve owner-only
                # access instead of broadening permissions for a local run.
                private_path.chmod(0o600)
            public_path.chmod(0o644)
        index[agent_id] = {
            "key_id": f"{agent_id}:v1",
            "private_key": str(private_path),
            "public_key": str(public_path),
        }
    index_path = output / "key_index.json"
    index_path.write_text(
        json.dumps(index, ensure_ascii=False, sort_keys=True, indent=2),
        encoding="utf-8",
    )
    index_path.chmod(0o644)


if __name__ == "__main__":
    main()
