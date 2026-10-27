"""Offline enforcement for the hub (FR5/NFR4).

Call :func:`enforce_offline` before importing whisperx, faster_whisper, transformers,
huggingface_hub or pyannote:

* Hugging Face Hub and transformers are put in offline mode (cache only, no requests);
* library telemetry is switched off - pyannote.audio 4.x sends OpenTelemetry spans to
  ``https://otel.pyannote.ai`` by default (``telemetry/config.yaml: metrics_enabled: true``);
* a socket guard refuses every non-loopback connection, and every name lookup of a
  non-loopback host (no DNS query leaves the machine), from this process and counts the
  attempts, so a library that tries to reach the network fails loudly instead of silently
  downloading or reporting.

Subprocesses (ffmpeg for decoding, adb for the clock offset) are separate processes and are
not affected.
"""

from __future__ import annotations

import ipaddress
import os
import socket
import threading

OFFLINE_ENV = {
    "HF_HUB_OFFLINE": "1",
    "TRANSFORMERS_OFFLINE": "1",
    "HF_DATASETS_OFFLINE": "1",
    "HF_HUB_DISABLE_TELEMETRY": "1",
    "HF_HUB_DISABLE_IMPLICIT_TOKEN": "1",
    "DO_NOT_TRACK": "1",
    "PYANNOTE_METRICS_ENABLED": "false",
    "OTEL_SDK_DISABLED": "true",
}


class OfflineViolation(ConnectionRefusedError):
    """A non-loopback connection was attempted while offline mode is enforced."""


_lock = threading.Lock()
_blocked: list[str] = []
_installed = False
_original_connect = socket.socket.connect
_original_connect_ex = socket.socket.connect_ex
_original_getaddrinfo = socket.getaddrinfo


def _is_loopback(address) -> bool:
    if not isinstance(address, tuple) or not address:
        return True  # AF_UNIX paths and the like are local
    host = address[0]
    if host in ("localhost", ""):
        return True
    try:
        return ipaddress.ip_address(host.split("%")[0]).is_loopback
    except ValueError:
        return False  # a host name: refuse, it would need DNS and leave the machine


def _check(address) -> None:
    if _is_loopback(address):
        return
    with _lock:
        _blocked.append(repr(address))
    raise OfflineViolation(f"offline mode: connection to {address!r} refused")


def _guarded_connect(self, address):
    _check(address)
    return _original_connect(self, address)


def _guarded_connect_ex(self, address):
    _check(address)
    return _original_connect_ex(self, address)


def _guarded_getaddrinfo(host, *args, **kwargs):
    # Name lookups of non-loopback hosts would send DNS queries off the machine.
    if host is not None:
        name = host.decode() if isinstance(host, bytes) else str(host)
        _check((name, 0))
    return _original_getaddrinfo(host, *args, **kwargs)


def enforce_offline() -> dict:
    """Sets the offline environment and installs the socket guard (idempotent).

    Returns the environment values in force, for recording in outputs.
    """
    global _installed
    for key, value in OFFLINE_ENV.items():
        os.environ[key] = value
    with _lock:
        if not _installed:
            socket.socket.connect = _guarded_connect
            socket.socket.connect_ex = _guarded_connect_ex
            socket.getaddrinfo = _guarded_getaddrinfo
            _installed = True
    return {key: os.environ[key] for key in OFFLINE_ENV}


def blocked_attempts() -> list[str]:
    """Addresses of the connections refused so far."""
    with _lock:
        return list(_blocked)


def _uninstall_for_tests() -> None:
    global _installed
    with _lock:
        socket.socket.connect = _original_connect
        socket.socket.connect_ex = _original_connect_ex
        socket.getaddrinfo = _original_getaddrinfo
        _installed = False
        _blocked.clear()
