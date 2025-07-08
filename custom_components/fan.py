"""Support for Tasmota IR Fan devices."""
import logging
import json
import requests
from typing import Any, Dict, List, Optional

from homeassistant.components.fan import FanEntity, FanEntityFeature
from homeassistant.core import HomeAssistant
from homeassistant.config_entries import ConfigEntry
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.util.percentage import (
    ordered_list_item_to_percentage,
    percentage_to_ordered_list_item,
)

from .const import DOMAIN, CONF_DEVICE_IP, CONF_IR_CODES

_LOGGER = logging.getLogger(__name__)

async def async_setup_entry(
    hass: HomeAssistant,
    config_entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up Tasmota IR fan devices."""
    # 只有当设备类型是fan时才创建实体
    if config_entry.data.get("device_type") != "fan":
        return
        
    device_ip = config_entry.data[CONF_DEVICE_IP]
    ir_codes = config_entry.data.get(CONF_IR_CODES, {})
    name = config_entry.data["name"]
    fan_config = config_entry.data.get("fan_config", {})
    
    fan_device = TasmotaIRFan(device_ip, ir_codes, fan_config, name, config_entry.entry_id)
    async_add_entities([fan_device], True)

class TasmotaIRFan(FanEntity):
    """Representation of a Tasmota IR Fan device."""

    def __init__(self, device_ip: str, ir_codes: Dict[str, Any], fan_config: Dict[str, Any], name: str, entry_id: str):
        """Initialize the fan device."""
        self._device_ip = device_ip
        self._ir_codes = ir_codes
        self._fan_config = fan_config
        self._name = name
        self._entry_id = entry_id
        self._unique_id = f"tasmota_ir_fan_{entry_id}"
        
        # 从配置中获取档位数量和预设模式
        self._speed_count = fan_config.get('speed_count', 3)
        self._preset_modes = fan_config.get('preset_modes', [])
        self._oscillation_supported = fan_config.get('oscillation_supported', True)
        
        # 生成档位名称列表
        self._ordered_named_fan_speeds = [f"{i}档" for i in range(1, self._speed_count + 1)]
        
        # State variables
        self._is_on = False
        self._percentage = 0
        self._oscillating = False
        self._preset_mode = None
        self._available = True

    @property
    def unique_id(self) -> str:
        """Return unique ID."""
        return self._unique_id

    @property
    def name(self) -> str:
        """Return the name of the fan."""
        return self._name

    @property
    def is_on(self) -> bool:
        """Return true if the fan is on."""
        return self._is_on

    @property
    def percentage(self) -> Optional[int]:
        """Return the current speed percentage."""
        return self._percentage

    @property
    def speed_count(self) -> int:
        """Return the number of speeds the fan supports."""
        return self._speed_count

    @property
    def oscillating(self) -> bool:
        """Return whether or not the fan is currently oscillating."""
        return self._oscillating

    @property
    def preset_mode(self) -> Optional[str]:
        """Return the current preset mode."""
        return self._preset_mode

    @property
    def preset_modes(self) -> Optional[List[str]]:
        """Return a list of available preset modes."""
        return self._preset_modes if self._preset_modes else None

    @property
    def supported_features(self) -> FanEntityFeature:
        """Flag supported features."""
        features = FanEntityFeature(0)
        
        # 检查是否支持摆头
        if self._oscillation_supported and "swing" in self._ir_codes:
            features |= FanEntityFeature.OSCILLATE
            
        # 检查是否有档位控制
        speed_keys = [f"speed_{i}" for i in range(1, self._speed_count + 1)]
        if any(key in self._ir_codes for key in speed_keys):
            features |= FanEntityFeature.SET_SPEED
            
        # 检查是否有预设模式
        if self._preset_modes:
            preset_keys = [f"preset_{mode}" for mode in self._preset_modes]
            if any(key in self._ir_codes for key in preset_keys):
                features |= FanEntityFeature.PRESET_MODE
                
        return features

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
            "model": f"红外风扇控制器 ({self._speed_count}档)",
            "sw_version": "1.0.0",
        }

    async def async_turn_on(
        self,
        percentage: Optional[int] = None,
        preset_mode: Optional[str] = None,
        **kwargs,
    ) -> None:
        """Turn on the fan."""
        if preset_mode is not None:
            await self.async_set_preset_mode(preset_mode)
        elif percentage is not None:
            await self.async_set_percentage(percentage)
        else:
            await self._send_ir_command("power")
            self._is_on = True
        self.async_write_ha_state()

    async def async_turn_off(self, **kwargs) -> None:
        """Turn off the fan."""
        await self._send_ir_command("power")
        self._is_on = False
        self._percentage = 0
        self._preset_mode = None
        self.async_write_ha_state()

    async def async_set_percentage(self, percentage: int) -> None:
        """Set the speed percentage of the fan."""
        if percentage == 0:
            await self.async_turn_off()
            return

        # Convert percentage to speed level (1-based)
        speed_level = max(1, min(self._speed_count, 
                                round(percentage * self._speed_count / 100)))
        speed_key = f"speed_{speed_level}"
        
        if speed_key in self._ir_codes:
            await self._send_ir_command(speed_key)
            self._percentage = percentage
            self._is_on = True
            self._preset_mode = None  # 清除预设模式
        else:
            _LOGGER.warning("Speed key %s not found in IR codes", speed_key)
            
        self.async_write_ha_state()

    async def async_set_preset_mode(self, preset_mode: str) -> None:
        """Set the preset mode of the fan."""
        if preset_mode not in self._preset_modes:
            _LOGGER.warning("Preset mode %s not supported", preset_mode)
            return
            
        preset_key = f"preset_{preset_mode}"
        if preset_key in self._ir_codes:
            await self._send_ir_command(preset_key)
            self._preset_mode = preset_mode
            self._is_on = True
            self._percentage = None  # 预设模式时清除百分比
        else:
            _LOGGER.warning("Preset key %s not found in IR codes", preset_key)
            
        self.async_write_ha_state()

    async def async_oscillate(self, oscillating: bool) -> None:
        """Set oscillation."""
        if self._oscillation_supported and "swing" in self._ir_codes:
            await self._send_ir_command("swing")
            self._oscillating = oscillating
        self.async_write_ha_state()

    async def _send_ir_command(self, command_key: str) -> None:
        """Send IR command to Tasmota device."""
        if command_key not in self._ir_codes:
            _LOGGER.error("未找到命令的红外码: %s", command_key)
            return

        try:
            code = self._ir_codes[command_key]
            
            # Build IR command
            ir_data = {
                "Protocol": code["protocol"],
                "Bits": code["bits"],
                "Data": code["data"],
                "Repeat": code.get("repeat", 0)
            }

            _LOGGER.info("发送红外命令到 %s: %s = %s", self._device_ip, command_key, ir_data)

            # Encode command
            command_json = json.dumps(ir_data, separators=(',', ':'))
            import urllib.parse
            encoded_command = urllib.parse.quote(command_json)
            
            # Send HTTP request
            url = f"http://{self._device_ip}/cm?cmnd=IRsend%20{encoded_command}"
            _LOGGER.debug("发送请求到: %s", url)
            
            response = await self.hass.async_add_executor_job(
                requests.get, url, {"timeout": 10}
            )
            response.raise_for_status()
            
            result = response.json()
            _LOGGER.info("红外命令响应: %s", result)
            
            self._available = True
            
        except requests.exceptions.RequestException as e:
            _LOGGER.error("HTTP请求失败 %s: %s", self._device_ip, e)
            self._available = False
        except Exception as e:
            _LOGGER.error("发送红外命令失败 %s 到 %s: %s", command_key, self._device_ip, e)
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