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
#     https://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS, WITHOUT
# WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied. See the
# License for the specific language governing permissions and limitations
# under the License.
#
# ===----------------------------------------------------------------------===
# }}}

import logging
import requests

from pydantic import AnyHttpUrl, computed_field, Field, FilePath
from typing import Iterable, Any

from volttron.driver.base.config import PointConfig, RemoteConfig
from volttron.driver.base.interfaces import BaseInterface, BaseRegister, BasicRevert

_log = logging.getLogger(__name__)
type_mapping = {"string": str, "int": int, "integer": int, "float": float, "bool": bool, "boolean": bool}


class HAPointConfig(PointConfig):
    entity_id: str = Field(alias='Entity ID')
    entity_attribute: str = Field(default='state', alias='Entity Point')
    point_name: str = Field(alias='Volttron Point Name')
    starting_value: Any = Field(alias='Starting Value')
    type: str = Field(alias='Type')

class HARemoteConfig(RemoteConfig):
    url: AnyHttpUrl
    access_token: str
    verify_ssl: bool = True
    ssl_cert_path: FilePath | None = None

    @computed_field
    @property
    def verify_option(self) -> str | bool:
        return self.ssl_cert_path if self.ssl_cert_path else self.verify_ssl


class HomeAssistantRegister(BaseRegister):

    def __init__(self,
                 read_only,
                 point_name,
                 units,
                 reg_type,
                 entity_id,
                 entity_attribute):
        super(HomeAssistantRegister, self).__init__("byte", read_only, point_name, units, description='')
        self.reg_type = reg_type
        self.entity_id = entity_id
        self.value = None
        self.entity_attribute = entity_attribute


class HomeAssistantInterface(BasicRevert, BaseInterface):

    REGISTER_CONFIG_CLASS = HAPointConfig
    INTERFACE_CONFIG_CLASS = HARemoteConfig

    def __init__(self, config: RemoteConfig, core, vip, *args, **kwargs):
        BasicRevert.__init__(self, **kwargs)
        BaseInterface.__init__(self, config, core, vip, *args, **kwargs)

        if not self.config.verify_ssl:
            import urllib3
            _log.debug("SSL verification is disabled; suppressing warnings.")
            urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

    def create_register(self, register_definition: HAPointConfig) -> BaseRegister:
        """Create a register instance from the provided PointConfig.

        :param register_definition: PointConfig from which to create a Register instance.
        """
        register = HomeAssistantRegister(
            read_only=register_definition.writable is not True,
            point_name=register_definition.point_name,
            units=register_definition.units,
            reg_type=register_definition.type,
            entity_id=register_definition.entity_id,
            entity_attribute=register_definition.entity_attribute
        )
        if register_definition.starting_value is not None:
            self.set_default(register_definition.point_name, register_definition.starting_value)
        return register

    def get_point(self, topic, **kwargs):
        register: HomeAssistantRegister = self.get_register_by_name(topic)

        entity_data = self.get_entity_data(register.entity_id)
        if register.point_name == "state":
            result = entity_data.get("state", None)
            return result
        else:
            value = entity_data.get("attributes", {}).get(f"{register.point_name}", 0)
            return value

    def _set_point(self, topic, value):
        register: HomeAssistantRegister = self.get_register_by_name(topic)
        if register.read_only:
            raise IOError("Trying to write to a point configured read only: " + topic)
        register.value = register.reg_type(value)    # setting the value
        entity_attribute = register.entity_attribute
        # Changing lights values in home assistant based off of register value.
        if "light." in register.entity_id:
            if entity_attribute == "state":
                if isinstance(register.value, int) and register.value in [0, 1]:
                    if register.value == 1:
                        self.turn_on_lights(register.entity_id)
                    elif register.value == 0:
                        self.turn_off_lights(register.entity_id)
                else:
                    error_msg = f"State value for {register.entity_id} should be an integer value of 1 or 0"
                    _log.info(error_msg)
                    raise ValueError(error_msg)

            elif entity_attribute == "brightness":
                if isinstance(register.value,
                              int) and 0 <= register.value <= 255:    # Make sure its int and within range
                    self.change_brightness(register.entity_id, register.value)
                else:
                    error_msg = "Brightness value should be an integer between 0 and 255"
                    _log.error(error_msg)
                    raise ValueError(error_msg)
            else:
                error_msg = f"Unexpected point_name {topic} for register {register.entity_id}"
                _log.error(error_msg)
                raise ValueError(error_msg)

        elif "input_boolean." in register.entity_id:
            if entity_attribute == "state":
                if isinstance(register.value, int) and register.value in [0, 1]:
                    if register.value == 1:
                        self.set_input_boolean(register.entity_id, "on")
                    elif register.value == 0:
                        self.set_input_boolean(register.entity_id, "off")
                else:
                    error_msg = f"State value for {register.entity_id} should be an integer value of 1 or 0"
                    _log.info(error_msg)
                    raise ValueError(error_msg)
            else:
                _log.info(f"Currently, input_booleans only support state")

        # Changing thermostat values.
        elif "climate." in register.entity_id:
            if entity_attribute == "state":
                if isinstance(register.value, int) and register.value in [0, 2, 3, 4]:
                    if register.value == 0:
                        self.change_thermostat_mode(entity_id=register.entity_id, mode="off")
                    elif register.value == 2:
                        self.change_thermostat_mode(entity_id=register.entity_id, mode="heat")
                    elif register.value == 3:
                        self.change_thermostat_mode(entity_id=register.entity_id, mode="cool")
                    elif register.value == 4:
                        self.change_thermostat_mode(entity_id=register.entity_id, mode="auto")
                else:
                    error_msg = f"Climate state should be an integer value of 0, 2, 3, or 4"
                    _log.error(error_msg)
                    raise ValueError(error_msg)
            elif entity_attribute == "temperature":
                self.set_thermostat_temperature(register)

            else:
                error_msg = f"Currently set_point is supported only for thermostats state and temperature {register.entity_id}"
                _log.error(error_msg)
                raise ValueError(error_msg)
        else:
            error_msg = f"Unsupported entity_id: {register.entity_id}. " \
                        f"Currently set_point is supported only for thermostats and lights"
            _log.error(error_msg)
            raise ValueError(error_msg)
        return register.value

    def get_entity_data(self, entity_id):
        headers = {
            "Authorization": f"Bearer {self.config.access_token}",
            "Content-Type": "application/json",
        }
        # the /states grabs current state AND attributes of a specific entity
        url = f"{self.config.url}/api/states/{entity_id}"
        response = requests.get(url, headers=headers, verify=self.config.verify_option)
        if response.status_code == 200:
            return response.json()    # return the json attributes from entity
        else:
            error_msg = f"Request failed with status code {response.status_code}, Point name: {entity_id}, " \
                        f"response: {response.text}"
            _log.error(error_msg)
            raise Exception(error_msg)

    def _get_multiple_points(self, topics: Iterable[str], **kwargs) -> (dict, dict):
        result = {}
        errors = {}
        for topic in topics:
            register: HomeAssistantRegister = self.get_register_by_name(topic)
            entity_id = register.entity_id
            entity_attribute = register.entity_attribute
            try:
                entity_data = self.get_entity_data(entity_id)    # Using Entity ID to get data
                if "climate." in entity_id:    # handling thermostats.
                    if entity_attribute == "state":
                        state = entity_data.get("state", None)
                        # Giving thermostat states an equivalent number.
                        if state == "off":
                            register.value = 0
                            result[register.point_name] = 0
                        elif state == "heat":
                            register.value = 2
                            result[register.point_name] = 2
                        elif state == "cool":
                            register.value = 3
                            result[register.point_name] = 3
                        elif state == "auto":
                            register.value = 4
                            result[register.point_name] = 4
                        else:
                            error_msg = f"State {state} from {entity_id} is not yet supported"
                            _log.error(error_msg)
                            ValueError(error_msg)
                    # Assigning attributes
                    else:
                        attribute = entity_data.get("attributes", {}).get(f"{entity_attribute}", 0)
                        register.value = attribute
                        result[register.point_name] = attribute
                # handling light states
                elif "light." in entity_id or "input_boolean." in entity_id:  # Checks for lights or input booleans
                    if entity_attribute == "state":
                        state = entity_data.get("state", None)
                        _log.debug(f"Fetched light state for {entity_id}: {state}")  # Log the fetched state
                        # Converting light states to numbers.
                        if state == "on":
                            register.value = 1
                            result[register.point_name] = 1
                            _log.debug(f"Set light state to 1 (on) for {entity_id}")
                        elif state == "off":
                            register.value = 0
                            result[register.point_name] = 0
                            _log.debug(f"Set light state to 0 (off) for {entity_id}")
                        else:
                            _log.error(f"Unknown state {state} for {entity_id}")
                    else:
                        attribute = entity_data.get("attributes", {}).get(f"{entity_attribute}", 0)
                        register.value = attribute
                        result[register.point_name] = attribute
                else:    # handling all devices that are not thermostats or light states
                    if entity_attribute == "state":

                        state = entity_data.get("state", None)
                        register.value = state
                        result[register.point_name] = state
                    # Assigning attributes
                    else:
                        attribute = entity_data.get("attributes", {}).get(f"{entity_attribute}", 0)
                        register.value = attribute
                        result[register.point_name] = attribute
            except Exception as e:
                _log.error(f"An unexpected error occurred for entity_id: {entity_id}: {e}, using {self.config.verify_option}")

        return result, errors

    def turn_off_lights(self, entity_id):
        url = f"{self.config.url}/api/services/light/turn_off"
        headers = {
            "Authorization": f"Bearer {self.config.access_token}",
            "Content-Type": "application/json",
        }
        payload = {
            "entity_id": entity_id,
        }
        self._post_method(url, headers, payload, f"turn off {entity_id}")

    def turn_on_lights(self, entity_id):
        url = f"{self.config.url}/api/services/light/turn_on"
        headers = {
            "Authorization": f"Bearer {self.config.access_token}",
            "Content-Type": "application/json",
        }

        payload = {"entity_id": f"{entity_id}"}
        self._post_method(url, headers, payload, f"turn on {entity_id}")

    def change_thermostat_mode(self, entity_id, mode):
        # Check if entity_id startswith climate.
        if not entity_id.startswith("climate."):
            _log.error(f"{entity_id} is not a valid thermostat entity ID.")
            return
        # Build header
        url = f"{self.config.url}/api/services/climate/set_hvac_mode"
        headers = {
            "Authorization": f"Bearer {self.config.access_token}",
            "content-type": "application/json",
        }
        # Build data
        data = {
            "entity_id": entity_id,
            "hvac_mode": mode,
        }
        # Post data
        self._post_method(url, headers, data, f"change mode of {entity_id} to {mode}")

    def set_thermostat_temperature(self, register: HomeAssistantRegister):
        # Check if the provided entity_id starts with "climate."
        if not register.entity_id.startswith("climate."):
            _log.error(f"{register.entity_id} is not a valid thermostat entity ID.")
            return

        url = f"{self.config.url}/api/services/climate/set_temperature"
        headers = {
            "Authorization": f"Bearer {self.config.access_token}",
            "content-type": "application/json",
        }

        if register.units == "C":
            converted_temp = round((register.value - 32) * 5 / 9, 1)
            _log.info(f"Converted temperature {converted_temp}")
            data = {
                "entity_id": register.entity_id,
                "temperature": converted_temp,
            }
        else:
            data = {
                "entity_id": register.entity_id,
                "temperature": register.value,
            }
        self._post_method(url, headers, data, f"set temperature of {register.entity_id} to {register.value}")

    def change_brightness(self, entity_id, value):
        url = f"{self.config.url}/api/services/light/turn_on"
        headers = {
            "Authorization": f"Bearer {self.config.access_token}",
            "Content-Type": "application/json",
        }
        # ranges from 0 - 255
        payload = {
            "entity_id": f"{entity_id}",
            "brightness": value,
        }

        self._post_method(url, headers, payload, f"set brightness of {entity_id} to {value}")

    def set_input_boolean(self, entity_id, state):
        service = 'turn_on' if state == 'on' else 'turn_off'
        url = f"{self.config.url}/api/services/input_boolean/{service}"
        headers = {
            "Authorization": f"Bearer {self.config.access_token}",
            "Content-Type": "application/json",
        }

        payload = {"entity_id": entity_id}

        response = requests.post(url, headers=headers, json=payload, verify=self.config.verify_option)

        # Optionally check for a successful response
        if response.status_code == 200:
            print(f"Successfully set {entity_id} to {state}")
        else:
            print(f"Failed to set {entity_id} to {state}: {response.text}")

    def _post_method(self, url, headers, data, operation_description):
        err = None
        try:
            response = requests.post(url, headers=headers, json=data, verify=self.config.verify_option)
            if response.status_code == 200:
                _log.info(f"Success: {operation_description}")
            else:
                err = f"Failed to {operation_description}. Status code: {response.status_code}. " \
                      f"Response: {response.text}"

        except requests.RequestException as e:
            err = f"Error when attempting - {operation_description} : {e}"
        if err:
            _log.error(err)
            raise Exception(err)

    @classmethod
    def unique_remote_id(cls, config_name: str, config: HARemoteConfig) -> tuple:
        """Unique Remote ID
        Subclasses should use this class method to return a hashable identifier which uniquely identifies a single
         remote -- e.g., if multiple remotes may exist at a single IP address, but on different ports,
         the unique ID might be the tuple: (ip_address, port).
        The base class returns the name of the device configuration file, requiring a separate DriverAgent for each.
        """
        return config.url,