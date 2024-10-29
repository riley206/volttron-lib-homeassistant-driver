import json

from unittest.mock import MagicMock
from platform_driver.agent import PlatformDriverAgent
from platform_driver.overrides import OverrideManager
from platform_driver.reservations import ReservationManager
from pathlib import Path
from volttron.utils import get_aware_utc_now
from volttrontesting.server_mock import TestServer

# To run these tests, create a helper toggle named volttrontest in your Home Assistant instance.
# This can be done by going to Settings > Devices & services > Helpers > Create Helper > Toggle

HOMEASSISTANT_URL = "" # Examples, http://0.0.0.0:8123, https://0.0.0.0:443
ACCESS_TOKEN = ""
SSL_CERT_PATH = "" # Optional for self signed cert. Make sure you give permissions. chmod 777
VERIFY_SSL = True

def return_config(pattern):
    if pattern == '_override_patterns':
        return b''

def test_instantiate():
    ts = TestServer()
    pda = ts.instantiate_agent(PlatformDriverAgent)

    driver_config = {
        "driver_config": {
            "url": HOMEASSISTANT_URL,
            "access_token": ACCESS_TOKEN,
            "verify_ssl": VERIFY_SSL,
            "ssl_cert_path": SSL_CERT_PATH
        },
        "driver_type": "home_assistant",
        "registry_config": [
            {
                "Entity ID": "input_boolean.volttrontest",
                "Entity Attribute": "state",
                "Volttron Point Name": "cool",
                "Units": "On / Off",
                "Units Details": "on/off",
                "Writable": True,
                "Starting Value": True,
                "Type": "boolean",
                "Notes": "input bool"
            }
        ],
        "timezone": "US/Pacific",
        "interval": 30,
    }
    driver_config_path = Path("/tmp/driver_config.config")
    with driver_config_path.open("w") as file:
        json.dump(driver_config, file)

    with open('/tmp/driver_config.config') as f:
        HAConfig = json.load(f)

    pda.vip.config.get = return_config
    pda.override_manager = OverrideManager(pda)
    now = get_aware_utc_now()
    pda.reservation_manager = ReservationManager(pda, pda.config.reservation_preempt_grace_time, now)
    pda._configure_new_equipment('devices/home_assistant', 'NEW', HAConfig, schedule_now=False)
    pda.vip = MagicMock()
    pda.vip.rpc.context = MagicMock()
    pda.vip.rpc.context.vip_message.peer = 'some.caller'

    pda.set_point('devices/home_assistant', 'cool', 0)
    result = pda.get_point('devices/home_assistant/cool')
    assert result == 'off'
    pda.set_point('devices/home_assistant', 'cool', 1)
    result = pda.get_point('devices/home_assistant/cool')
    assert result == 'on'