from __future__ import annotations

import base64
import hashlib
import json
from pathlib import Path
from typing import Any, Protocol

from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import (
    Ed25519PrivateKey,
    Ed25519PublicKey,
)
from pydantic import BaseModel


def canonical_json(value: BaseModel | dict[str, Any]) -> bytes:
    payload = value.model_dump(mode="json") if isinstance(value, BaseModel) else value
    return json.dumps(
        payload,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    ).encode("utf-8")


def payload_hash(value: BaseModel | dict[str, Any]) -> str:
    return hashlib.sha256(canonical_json(value)).hexdigest()


class SignatureProvider(Protocol):
    @property
    def key_id(self) -> str: ...

    def sign(self, value: BaseModel | dict[str, Any]) -> str: ...

    def verify(self, value: BaseModel | dict[str, Any], signature: str) -> bool: ...


class Ed25519SignatureProvider:
    def __init__(
        self,
        key_id: str,
        *,
        private_key: Ed25519PrivateKey | None,
        public_key: Ed25519PublicKey,
    ) -> None:
        self._key_id = key_id
        self._private_key = private_key
        self._public_key = public_key

    @property
    def key_id(self) -> str:
        return self._key_id

    @classmethod
    def generate(cls, key_id: str) -> Ed25519SignatureProvider:
        private_key = Ed25519PrivateKey.generate()
        return cls(key_id, private_key=private_key, public_key=private_key.public_key())

    @classmethod
    def from_files(
        cls,
        key_id: str,
        *,
        private_key_path: str | Path | None,
        public_key_path: str | Path,
    ) -> Ed25519SignatureProvider:
        private_key = None
        if private_key_path is not None:
            loaded_private = serialization.load_pem_private_key(
                Path(private_key_path).read_bytes(),
                password=None,
            )
            if not isinstance(loaded_private, Ed25519PrivateKey):
                raise TypeError("Configured private key is not Ed25519")
            private_key = loaded_private
        loaded_public = serialization.load_pem_public_key(Path(public_key_path).read_bytes())
        if not isinstance(loaded_public, Ed25519PublicKey):
            raise TypeError("Configured public key is not Ed25519")
        return cls(key_id, private_key=private_key, public_key=loaded_public)

    def sign(self, value: BaseModel | dict[str, Any]) -> str:
        if self._private_key is None:
            raise RuntimeError("Private key is not available for signing")
        return base64.b64encode(self._private_key.sign(canonical_json(value))).decode("ascii")

    def verify(self, value: BaseModel | dict[str, Any], signature: str) -> bool:
        try:
            decoded = base64.b64decode(signature, validate=True)
            self._public_key.verify(decoded, canonical_json(value))
        except (InvalidSignature, ValueError):
            return False
        return True

    def write_private_key(self, path: str | Path) -> None:
        if self._private_key is None:
            raise RuntimeError("Private key is not available")
        Path(path).write_bytes(
            self._private_key.private_bytes(
                serialization.Encoding.PEM,
                serialization.PrivateFormat.PKCS8,
                serialization.NoEncryption(),
            )
        )

    def write_public_key(self, path: str | Path) -> None:
        Path(path).write_bytes(
            self._public_key.public_bytes(
                serialization.Encoding.PEM,
                serialization.PublicFormat.SubjectPublicKeyInfo,
            )
        )
