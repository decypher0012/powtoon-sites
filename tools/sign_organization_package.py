from __future__ import annotations

import argparse
import base64
import json
from pathlib import Path

from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import padding


def main() -> int:
    parser = argparse.ArgumentParser(description="Create a signed Work Launcher organization package")
    parser.add_argument("config", type=Path); parser.add_argument("private_key", type=Path); parser.add_argument("output", type=Path)
    parser.add_argument("--policy", type=Path, help="Optional enterprise policy JSON")
    args = parser.parse_args()
    config = json.loads(args.config.read_text(encoding="utf-8"))
    package = {"format": "work-launcher-organization-v1", "config": config}
    if args.policy: package["policy"] = json.loads(args.policy.read_text(encoding="utf-8"))
    payload = json.dumps(package, separators=(",", ":"), sort_keys=True).encode()
    key = serialization.load_pem_private_key(args.private_key.read_bytes(), password=None)
    signature = key.sign(payload, padding.PSS(mgf=padding.MGF1(hashes.SHA256()), salt_length=padding.PSS.MAX_LENGTH), hashes.SHA256())
    envelope = {"payload": base64.b64encode(payload).decode("ascii"), "signature": base64.b64encode(signature).decode("ascii")}
    args.output.write_text(json.dumps(envelope, indent=2) + "\n", encoding="utf-8")
    return 0


if __name__ == "__main__": raise SystemExit(main())
