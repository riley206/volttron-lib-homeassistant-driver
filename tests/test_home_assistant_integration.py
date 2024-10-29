# -*- coding: utf-8 -*- {{{
# ===----------------------------------------------------------------------===
#
#                 Installable Component of Eclipse VOLTTRON
#
# ===----------------------------------------------------------------------===
#
# Copyright 2024 Battelle Memorial Institute
#
# Licensed under the Apache License, Version 2.0 (the "License"); you may not
# use this file except in compliance with the License. You may obtain a copy
# of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS, WITHOUT
# WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied. See the
# License for the specific language governing permissions and limitations
# under the License.
#
# ===----------------------------------------------------------------------===
# }}}
"""Integration tests for volttron-lib-home-assistant-driver"""
import json
import time
from pathlib import Path
from volttrontesting import PlatformWrapper
from volttrontesting.platformwrapper import InstallAgentOptions
from volttron.client.known_identities import CONTROL

# To run these tests, create a helper toggle named volttrontest in your Home Assistant instance.
# This can be done by going to Settings > Devices & services > Helpers > Create Helper > Toggle

HOMEASSISTANT_URL = "" # Examples, http://0.0.0.0:8123, https://0.0.0.0:443
ACCESS_TOKEN = ""
SSL_CERT_PATH = "" # Optional for self signed cert. Make sure you give permissions. chmod 777
VERIFY_SSL = True

def test_startup_instance(volttron_instance: PlatformWrapper):
    assert volttron_instance.is_running()

    # For now, we install things locally.
    agent_pth = "/home/riley/DRIVERWORK/11rc1/volttron-platform-driver"
    library_path = Path("/home/riley/DRIVERWORK/11rc1/volttron-lib-homeassistant-driver").resolve()

    vi = volttron_instance

    # Install the home assistant library using install_library.
    vi.install_library(library_path)
    time.sleep(1)

    # Install and start the platform driver agent using install_agent
    auuid = vi.install_agent(agent_dir=agent_pth,
                             install_options=InstallAgentOptions(start=True, vip_identity="platform.driver"))
    assert auuid is not None
    time.sleep(2)

    # Create registry configuration and store it as a tmp file.
    config_path = Path("/tmp/registry_config.json")
    registry_obj = [{
        "Entity ID": "input_boolean.volttrontest",
        "Entity Attribute": "state",
        "Volttron Point Name": "cool",
        "Units": "On / Off",
        "Units Details": "on/off",
        "Writable": True,
        "Starting Value": True,
        "Type": "boolean",
        "Notes": "input bool"
    }]
    with config_path.open("w") as file:
        json.dump(registry_obj, file)

    # Store the registry file using run_command.
    vi.run_command(
        ["vctl", "config", "store", "platform.driver", "homeassistant_test.json", str(config_path), "--json"]
    )

    # Store driver-specific configuration
    driver_config = {
        "driver_config": {
            "url": HOMEASSISTANT_URL,
            "access_token": ACCESS_TOKEN,
            "verify_ssl": VERIFY_SSL,
            "ssl_cert_path": SSL_CERT_PATH
        },
        "driver_type": "home_assistant",
        "registry_config": "config://homeassistant_test.json",
        "timezone": "US/Pacific",
        "interval": 30,
    }
    driver_config_path = Path("/tmp/driver_config.config")
    with driver_config_path.open("w") as file:
        json.dump(driver_config, file)

    # Store the driver config using run_command
    vi.run_command(
        ["vctl", "config", "store", "platform.driver", "devices/home_assistant", str(driver_config_path), "--json"]
    )

    # Verify that both configurations are stored using run_command
    list_configs = vi.run_command(["vctl", "config", "list", "platform.driver"])
    print("Final platform.driver config store contents:")
    print(list_configs)

    # Create a build agent to make rpc calls
    ba = vi.build_agent(identity="world")
    agent_identity = ba.vip.rpc.call(CONTROL, 'agent_vip_identity', auuid).get(timeout=10)
    print(f"Agent identity obtained: {agent_identity}")


    # Use RPC to turn on the switch, then get_point to make sure it was turned on.
    ba.vip.rpc.call("platform.driver", "set_point", "devices/home_assistant", "cool", 1).get(timeout=20)
    result = ba.vip.rpc.call("platform.driver", "get_point", "home_assistant", "cool").get(timeout=20)
    assert result == "on"

    # Use RPC to turn it off, then get_point to make sure its turned off.
    ba.vip.rpc.call("platform.driver", "set_point", "devices/home_assistant", "cool", 0).get(timeout=20)
    result = ba.vip.rpc.call("platform.driver", "get_point", "home_assistant", "cool").get(timeout=20)
    assert result == "off"
