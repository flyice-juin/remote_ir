"""Support for Tasmota IR HVAC devices."""
import logging
import json
import requests
from typing import Any, Dict, List, Optional

from homeassistant.components.climate import ClimateEntity
from homeassistant.components.climate.const import (
    HVACMode,
    ClimateEntityFeature,
)
from homeassistant.const import ATTR_TEMPERATURE, UnitOfTemperature
from homeassistant.core import HomeAssistant
from homeassistant.config_entries import ConfigEntry
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import DOMAIN, CONF_DEVICE_IP, CONF_VENDOR, DEFAULT_VENDOR

_LOGGER = logging.getLogger(__name__)

# Tasmota to HA mode mapping
TASMOTA_TO_HA_MODE = {
    "Off": HVACMode.OFF,
    "Auto": HVACMode.AUTO,
    "Cool": HVACMode.COOL,
    "Heat": HVACMode.HEAT,
    "Dry": HVACMode.DRY,
    "Fan": HVACMode.FAN_ONLY,
}

HA_TO_TASMOTA_MODE = {v: k for k, v in TASMOTA_TO_HA_MODE.items()}

# Fan speed mapping
TASMOTA_TO_HA_FAN = {
    "Auto": "自动",
    "Min": "最小",
    "Low": "低速",
    "Med": "中速",
    "High": "高速",
    "Max": "最大",
}

HA_TO_TASMOTA_FAN = {
    "自动": "Auto",
    "最小": "Min",
    "低速": "Low",
    "中速": "Med",
    "高速": "High",
    "最大": "Max",
}

async def async_setup_entry(
    hass: HomeAssistant,
    config_entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up Tasmota IR climate devices."""
    # 只有当设备类型是climate时才创建实体
    if config_entry.data.get("device_type") != "climate":
        return
        
    device_ip = config_entry.data[CONF_DEVICE_IP]
    vendor = config_entry.data.get(CONF_VENDOR, DEFAULT_VENDOR)
    name = config_entry.data["name"]
    
    climate_device = TasmotaIRClimate(device_ip, vendor, name, config_entry.entry_id)
    async_add_entities([climate_device], True)

class TasmotaIRClimate(ClimateEntity):
    """Representation of a Tasmota IR HVAC device."""

    def __init__(self, device_ip: str, vendor: str, name: str, entry_id: str):
        """Initialize the climate device."""
        self._device_ip = device_ip
        self._vendor = vendor
        self._name = name
        self._entry_id = entry_id
        self._unique_id = f"tasmota_ir_climate_{entry_id}"
        
        # State variables
        self._hvac_mode = HVACMode.OFF
        self._current_temperature = None
        self._target_temperature = 25
        self._fan_mode = "自动"
        self._swing_mode = "关闭"
        self._available = True
        
        # Features
        self._attr_supported_features = (
            ClimateEntityFeature.TARGET_TEMPERATURE |
            ClimateEntityFeature.FAN_MODE |
            ClimateEntityFeature.SWING_MODE
        )

    @property
    def unique_id(self) -> str:
        """Return unique ID."""
        return self._unique_id

    @property
    def name(self) -> str:
        """Return the name of the climate device."""
        return self._name

    @property
    def supported_features(self) -> ClimateEntityFeature:
        """Return the list of supported features."""
        return self._attr_supported_features

    @property
    def temperature_unit(self) -> str:
        """Return the unit of measurement."""
        return UnitOfTemperature.CELSIUS

    @property
    def current_temperature(self) -> Optional[float]:
        """Return the current temperature."""
        return self._current_temperature

    @property
    def target_temperature(self) -> Optional[float]:
        """Return the temperature we try to reach."""
        return self._target_temperature

    @property
    def hvac_mode(self) -> HVACMode:
        """Return current operation mode."""
        return self._hvac_mode

    @property
    def hvac_modes(self) -> List[HVACMode]:
        """Return the list of available operation modes."""
        return list(HA_TO_TASMOTA_MODE.keys())

    @property
    def fan_mode(self) -> Optional[str]:
        """Return the fan setting."""
        return self._fan_mode

    @property
    def fan_modes(self) -> Optional[List[str]]:
        """Return the list of available fan modes."""
        return list(HA_TO_TASMOTA_FAN.keys())

    @property
    def swing_mode(self) -> Optional[str]:
        """Return the swing setting."""
        return self._swing_mode

    @property
    def swing_modes(self) -> Optional[List[str]]:
        """Return the list of available swing modes."""
        return ["关闭", "垂直", "水平", "双向"]

    @property
    def min_temp(self) -> float:
        """Return the minimum temperature."""
        return 16

    @property
    def max_temp(self) -> float:
        """Return the maximum temperature."""
        return 30

    @property
    def target_temperature_step(self) -> float:
        """Return the supported step of target temperature."""
        return 1

    @property
    def available(self) -> bool:
        """Return True if entity is available."""
        return self._available

    @property
    def device_info(self) -> Dict[str, Any]:
        """Return device information."""
        return {
            "identifiers": {(DOMAIN, self._entry_id)},
            "name": self._name,
            "manufacturer": "Tasmota",
            "model": "红外空调控制器",
            "sw_version": "1.0.0",
        }

    async def async_set_temperature(self, **kwargs) -> None:
        """Set new target temperature."""
        temperature = kwargs.get(ATTR_TEMPERATURE)
        if temperature is None:
            return

        self._target_temperature = temperature
        await self._send_hvac_command()
        self.async_write_ha_state()

    async def async_set_hvac_mode(self, hvac_mode: HVACMode) -> None:
        """Set new target hvac mode."""
        self._hvac_mode = hvac_mode
        await self._send_hvac_command()
        self.async_write_ha_state()

    async def async_set_fan_mode(self, fan_mode: str) -> None:
        """Set new target fan mode."""
        self._fan_mode = fan_mode
        await self._send_hvac_command()
        self.async_write_ha_state()

    async def async_set_swing_mode(self, swing_mode: str) -> None:
        """Set new target swing operation."""
        self._swing_mode = swing_mode
        await self._send_hvac_command()
        self.async_write_ha_state()

    async def _send_hvac_command(self) -> None:
        """Send HVAC command to Tasmota device."""
        try:
            # Build command data
            command_data = {
                "Vendor": self._vendor,
                "Power": "Off" if self._hvac_mode == HVACMode.OFF else "On",
                "Mode": HA_TO_TASMOTA_MODE.get(self._hvac_mode, "Auto"),
                "Temp": int(self._target_temperature),
                "Celsius": "On",
                "FanSpeed": HA_TO_TASMOTA_FAN.get(self._fan_mode, "Auto"),
                "SwingV": "Auto" if self._swing_mode in ["垂直", "双向"] else "Off",
                "SwingH": "Auto" if self._swing_mode in ["水平", "双向"] else "Off",
                "Quiet": "Off",
                "Turbo": "Off",
                "Econo": "Off",
                "Light": "Off",
                "Beep": "Off"
            }

            _LOGGER.info("发送空调命令到 %s: %s", self._device_ip, command_data)

            # Encode command - 使用正确的URL编码
            command_json = json.dumps(command_data, separators=(',', ':'))
            import urllib.parse
            encoded_command = urllib.parse.quote(command_json)
            
            # Send HTTP request - 使用正确的命令格式
            url = f"http://{self._device_ip}/cm?cmnd=IRHVAC%20{encoded_command}"
            _LOGGER.debug("发送请求到: %s", url)
            
            response = await self.hass.async_add_executor_job(
                requests.get, url, {"timeout": 10}
            )
            response.raise_for_status()
            
            result = response.json()
            _LOGGER.info("空调命令响应: %s", result)
            
            self._available = True
            
        except requests.exceptions.RequestException as e:
            _LOGGER.error("HTTP请求失败 %s: %s", self._device_ip, e)
            self._available = False
        except Exception as e:
            _LOGGER.error("发送空调命令失败 %s: %s", self._device_ip, e)
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
            _LOGGER.debug("设备 %s 不可用: %s", self._device_ip, e)
            self._available = False