"""Support for Tasmota IR Remote devices."""
import logging
import json
import requests
from typing import Any, Dict, List, Optional

from homeassistant.components.remote import RemoteEntity
from homeassistant.core import HomeAssistant
from homeassistant.config_entries import ConfigEntry
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import DOMAIN, CONF_DEVICE_IP, CONF_BUTTONS

_LOGGER = logging.getLogger(__name__)

async def async_setup_entry(
    hass: HomeAssistant,
    config_entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up Tasmota IR remote devices."""
    # 只有当设备类型是remote时才创建实体
    if config_entry.data.get("device_type") != "remote":
        return
        
    device_ip = config_entry.data[CONF_DEVICE_IP]
    buttons = config_entry.data.get(CONF_BUTTONS, {})
    name = config_entry.data["name"]
    
    remote_device = TasmotaIRRemote(device_ip, buttons, name, config_entry.entry_id)
    async_add_entities([remote_device], True)

class TasmotaIRRemote(RemoteEntity):
    """Representation of a Tasmota IR Remote device."""

    def __init__(self, device_ip: str, buttons: Dict[str, Any], name: str, entry_id: str):
        """Initialize the remote device."""
        self._device_ip = device_ip
        self._buttons = buttons
        self._name = name
        self._entry_id = entry_id
        self._unique_id = f"tasmota_ir_remote_{entry_id}"
        self._available = True

    @property
    def unique_id(self) -> str:
        """Return unique ID."""
        return self._unique_id

    @property
    def name(self) -> str:
        """Return the name of the remote."""
        return self._name

    @property
    def is_on(self) -> bool:
        """Return true if the remote is on."""
        return True  # Remote is always "on"

    @property
    def available(self) -> bool:
        """Return True if entity is available."""
        return self._available

    async def async_turn_on(self, **kwargs) -> None:
        """Turn the remote on."""
        pass  # Remote doesn't have on/off state

    async def async_turn_off(self, **kwargs) -> None:
        """Turn the remote off."""
        pass  # Remote doesn't have on/off state

    async def async_send_command(self, command: List[str], **kwargs) -> None:
        """Send commands to the remote."""
        for cmd in command:
            if cmd in self._buttons:
                await self._send_ir_command(cmd)
            else:
                _LOGGER.warning("Unknown command: %s", cmd)

    async def _send_ir_command(self, command_name: str) -> None:
        """Send IR command to Tasmota device."""
        if command_name not in self._buttons:
            _LOGGER.error("Button not found: %s", command_name)
            return

        try:
            button = self._buttons[command_name]
            
            # Build IR command
            ir_data = {
                "Protocol": button["protocol"],
                "Bits": button["bits"],
                "Data": button["data"],
                "Repeat": button.get("repeat", 0)
            }

            _LOGGER.info("Sending IR command to %s: %s = %s", self._device_ip, command_name, ir_data)

            # Encode command - 使用正确的URL编码
            command_json = json.dumps(ir_data, separators=(',', ':'))
            import urllib.parse
            encoded_command = urllib.parse.quote(command_json)
            
            # Send HTTP request - 使用正确的命令格式
            url = f"http://{self._device_ip}/cm?cmnd=IRsend%20{encoded_command}"
            _LOGGER.debug("Sending request to: %s", url)
            
            response = await self.hass.async_add_executor_job(
                requests.get, url, {"timeout": 10}
            )
            response.raise_for_status()
            
            result = response.json()
            _LOGGER.info("IR command response: %s", result)
            
            self._available = True
            
        except requests.exceptions.RequestException as e:
            _LOGGER.error("HTTP request failed for %s: %s", self._device_ip, e)
            self._available = False
        except Exception as e:
            _LOGGER.error("Failed to send IR command %s to %s: %s", command_name, self._device_ip, e)
            self._available = False

    async def async_update(self) -> None:
        """Update the entity."""
        try:
            # Test device availability
            url = f"http://{self._device_ip}/cm?cmnd=Status"
            response = await self.hass.async_add_executor_job(
                requests.get, url, {"timeout": 5}
            )
            response.raise_for_status()
            self._available = True
            
        except Exception as e:
            _LOGGER.debug("Device %s not available: %s", self._device_ip, e)
            self._available = False