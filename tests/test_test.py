import os
import subprocess
import json
import time
from pathlib import Path
from volttrontesting import PlatformWrapper
from volttrontesting.platformwrapper import InstallAgentOptions
from unittest.mock import MagicMock
from volttron.client.known_identities import CONTROL

def test_startup_instance(volttron_instance: PlatformWrapper):
    assert volttron_instance.is_running()

    # Set up agent path and environment
    agent_pth = "/home/riley/DRIVERWORK/11rc1/volttron-platform-driver"
    library_path = Path("/home/riley/DRIVERWORK/11rc1/volttron-lib-homeassistant-driver").resolve()


    # Install the library
    vi = volttron_instance
    vi.install_library(library_path)
    time.sleep(1)
    print("@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@LOG", vi._log_path)

    env = vi._platform_environment
    print(f"@@@@@@@@@Using VOLTTRON_HOME from PlatformWrapper: {env['VOLTTRON_HOME']}")
    print(f"@@@@@@@@@Using PATH from PlatformWrapper: {env['VIRTUAL_ENV']}")

    # Install and start the platform driver agent
    auuid = vi.install_agent(agent_dir=agent_pth,
                             install_options=InstallAgentOptions(start=True, vip_identity="platform.driver"))
    assert auuid is not None
    time.sleep(2)

    # Create registry configuration and store it
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

    vi.run_command(
        ["vctl", "config", "store", "platform.driver", "homeassistant_test.json", str(config_path), "--json"]
    )

    # Verify the configuration is listed in platform.driver
    list_configs = vi.run_command(["vctl", "config", "list", "platform.driver"])
    print("Current platform.driver config store contents:")
    print(list_configs.stdout)

    # Store driver-specific configuration
    driver_config = {
        "driver_config": {
            "url": "",
            "access_token": "",
            "verify_ssl": True,
            "ssl_cert_path": ""
        },
        "driver_type": "home_assistant",
        "registry_config": "config://homeassistant_test.json",
        "timezone": "US/Pacific",
        "interval": 30,
    }
    driver_config_path = Path("/tmp/driver_config.config")
    with driver_config_path.open("w") as file:
        json.dump(driver_config, file)

    vi.run_command(
        ["vctl", "config", "store", "platform.driver", "devices/home_assistant", str(driver_config_path), "--json"]
    )

    # Verify that both configurations are stored
    list_configs = vi.run_command(["vctl", "config", "list", "platform.driver"])
    print("Final platform.driver config store contents:")
    print(list_configs.stdout)

    # Create a listener agent to verify if configurations are accessible
    listening = vi.build_agent(identity="world")
    agent_identity = listening.vip.rpc.call(CONTROL, 'agent_vip_identity', auuid).get(timeout=10)
    print(f"Agent identity obtained: {agent_identity}")
    time.sleep(20) # GIVE IT TIME LOL

    # Fetch data points to confirm the platform driver reads config correctly
    result = listening.vip.rpc.call("platform.driver", "get_point", "home_assistant", "cool").get(timeout=10)
    print("RPC call result:", result)
    assert result is not None, "Failed to retrieve data points from platform driver."

    print("Test completed successfully.")
