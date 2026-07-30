#!/usr/bin/env python3
"""Register a Home Assistant device node with platform.driver from config store.

This is a convenience helper for environments where platform.driver does not
rebuild equipment nodes automatically on restart.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from typing import Any

from volttron.client.commands.connection import ControlConnection


def _default_address(volttron_home: str) -> str:
    return f"ipc://@{volttron_home}/run/vip.socket"


def _load_registry_payload(conn: ControlConnection, registry_key: str) -> Any:
    payload = conn.server.vip.rpc.call(
        "platform.config_store",
        "get_config",
        "platform.driver",
        registry_key,
        False,
    ).get(timeout=20)

    if isinstance(payload, str):
        return json.loads(payload)
    return payload


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Register Home Assistant node and verify point reads."
    )
    parser.add_argument(
        "--volttron-home",
        default=os.environ.get("VOLTTRON_HOME", ""),
        help="Path to VOLTTRON_HOME (default: env VOLTTRON_HOME)",
    )
    parser.add_argument(
        "--address",
        default="",
        help="VIP address (default: ipc://@<VOLTTRON_HOME>/run/vip.socket)",
    )
    parser.add_argument(
        "--device-config",
        default="devices/home/bedroom",
        help="platform.driver device config key",
    )
    parser.add_argument(
        "--registry-config",
        default="",
        help="platform.driver registry config key (auto-detected from device config if omitted)",
    )
    args = parser.parse_args()

    if not args.volttron_home:
        print("error: VOLTTRON_HOME is required (set env or pass --volttron-home)", file=sys.stderr)
        return 2

    address = args.address or _default_address(args.volttron_home)
    os.environ["VOLTTRON_HOME"] = args.volttron_home

    conn = ControlConnection(address=address)
    try:
        cfg = conn.server.vip.rpc.call(
            "platform.config_store",
            "get_config",
            "platform.driver",
            args.device_config,
            False,
        ).get(timeout=20)

        registry_key = args.registry_config
        if not registry_key:
            reg_ref = cfg.get("registry_config", "")
            if isinstance(reg_ref, str) and reg_ref.startswith("config://"):
                registry_key = reg_ref[len("config://") :]
            else:
                print(
                    "error: could not infer registry key; pass --registry-config",
                    file=sys.stderr,
                )
                return 2

        registry_payload = _load_registry_payload(conn, registry_key)
        cfg["registry_config"] = registry_payload

        add_ok = conn.server.vip.rpc.call(
            "platform.driver", "add_node", args.device_config, cfg, True
        ).get(timeout=40)
        print(f"add_node: {add_ok}")

        scrape = conn.server.vip.rpc.call(
            "platform.driver", "scrape_all", args.device_config
        ).get(timeout=40)
        print(f"scrape_all: {scrape}")

        first_point = None
        if isinstance(registry_payload, list) and registry_payload:
            first_point = registry_payload[0].get("Volttron Point Name")

        if first_point:
            point_value = conn.server.vip.rpc.call(
                "platform.driver", "get_point", args.device_config, first_point
            ).get(timeout=40)
            print(f"get_point({first_point}): {point_value}")

        return 0
    except Exception as exc:
        print(f"error: {exc!r}", file=sys.stderr)
        return 1
    finally:
        conn.kill()


if __name__ == "__main__":
    raise SystemExit(main())
