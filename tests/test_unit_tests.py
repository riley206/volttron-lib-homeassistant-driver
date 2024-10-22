import pytest
from unittest.mock import MagicMock, patch
from volttron.driver.interfaces.home_assistant.home_assistant import (
    HomeAssistantInterface,
    HARemoteConfig,
    HAPointConfig,
    HomeAssistantRegister,
)


# Fixture for HARemoteConfig
@pytest.fixture
def ha_remote_config():
    return HARemoteConfig(url='http://localhost:8123',
                          access_token='test_token',
                          verify_ssl=True,
                          ssl_cert_path=None,
                          driver_type='home_assistant')


def test_create_register(ha_remote_config):
    core = MagicMock()
    vip = MagicMock()

    interface = HomeAssistantInterface(config=ha_remote_config, core=core, vip=vip)

    point_config = HAPointConfig(entity_id='light.living_room',
                                 entity_attribute='state',
                                 starting_value=1,
                                 type='int',
                                 units='',
                                 volttron_point_name='Living Room Light',
                                 writable=True)

    register = interface.create_register(point_config)

    assert register.entity_id == 'light.living_room'
    assert register.entity_attribute == 'state'
    assert register.volttron_point_name == 'Living Room Light'
    assert register.reg_type == 'int'
    assert register.value is None    # No value set initially


@patch('requests.get')
def test_get_point(mock_get, ha_remote_config):
    core = MagicMock()
    vip = MagicMock()

    interface = HomeAssistantInterface(config=ha_remote_config, core=core, vip=vip)

    register = HomeAssistantRegister(read_only=False,
                                     units='',
                                     reg_type=int,
                                     entity_id='light.living_room',
                                     entity_attribute='state',
                                     volttron_point_name='Living Room Light')
    interface.get_register_by_name = MagicMock(return_value=register)

    # Mocking the response of the requests.get call
    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.json.return_value = {"state": "on"}
    mock_get.return_value = mock_response

    result = interface.get_point('Living Room Light')

    assert result == "on"    # The mocked entity data has state "on"


@patch('requests.post')
def test_set_point(mock_post, ha_remote_config):
    core = MagicMock()
    vip = MagicMock()

    interface = HomeAssistantInterface(config=ha_remote_config, core=core, vip=vip)

    # Mocking the register and get_register_by_name method
    register = HomeAssistantRegister(read_only=False,
                                     units='',
                                     reg_type=int,
                                     entity_id='light.living_room',
                                     entity_attribute='state',
                                     volttron_point_name='Living Room Light')
    interface.get_register_by_name = MagicMock(return_value=register)

    # Mocking the requests.post response
    mock_response = MagicMock()
    mock_response.status_code = 200    # Simulate a successful POST request
    mock_response.text = "Success"
    mock_post.return_value = mock_response

    result = interface._set_point('Living Room Light', 1)

    assert result == 1    # Set point should return the value it was set to
    assert register.value == 1    # The register value should be updated

    # Verify that the post method was called with the correct URL and payload
    mock_post.assert_called_once_with('http://localhost:8123//api/services/light/turn_on',
                                      headers={
                                          'Authorization': 'Bearer test_token',
                                          'Content-Type': 'application/json',
                                      },
                                      json={'entity_id': 'light.living_room'},
                                      verify=True)


@patch('requests.get')
def test_get_entity_data(mock_get, ha_remote_config):
    core = MagicMock()
    vip = MagicMock()

    interface = HomeAssistantInterface(config=ha_remote_config, core=core, vip=vip)

    # Mocking the response of the requests.get call
    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.json.return_value = {"state": "on", "attributes": {"brightness": 255}}
    mock_get.return_value = mock_response

    result = interface.get_entity_data('light.living_room')

    assert result == {
        "state": "on",
        "attributes": {
            "brightness": 255
        }
    }    # Verify that the mocked response is returned.
