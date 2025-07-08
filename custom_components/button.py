"""Support for Tasmota IR Button devices."""
import logging
import json
import requests
from typing import Any, Dict, List, Optional

from homeassistant.components.button import ButtonEntity
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
    """Set up Tasmota IR button devices."""
    # 只有当设备类型是remote时才创建button实体
    if config_entry.data.get("device_type") != "remote":
        return
        
    device_ip = config_entry.data[CONF_DEVICE_IP]
    buttons = config_entry.data.get(CONF_BUTTONS, {})
    device_name = config_entry.data["name"]
    
    # 为每个按键创建一个button实体
    button_entities = []
    for button_name, button_data in buttons.items():
        button_entity = TasmotaIRButton(
            device_ip, 
            button_name, 
            button_data, 
            device_name,
            config_entry.entry_id
        )
        button_entities.append(button_entity)
    
    if button_entities:
        async_add_entities(button_entities, True)
        _LOGGER.info("为 %s 创建了 %d 个按键实体", device_name, len(button_entities))

class TasmotaIRButton(ButtonEntity):
    """Representation of a Tasmota IR Button device."""

    def __init__(self, device_ip: str, button_name: str, button_data: Dict[str, Any], device_name: str, entry_id: str):
        """Initialize the button device."""
        self._device_ip = device_ip
        self._button_name = button_name
        self._button_data = button_data
        self._device_name = device_name
        self._entry_id = entry_id
        
        # 生成唯一ID和实体ID
        safe_button_name = button_name.replace(" ", "_").replace(".", "_").replace("-", "_")
        self._unique_id = f"tasmota_ir_button_{entry_id}_{safe_button_name}"
        self._attr_name = f"{device_name} {button_name}"
        self._available = True

    @property
    def unique_id(self) -> str:
        """Return unique ID."""
        return self._unique_id

    @property
    def name(self) -> str:
        """Return the name of the button."""
        return self._attr_name

    @property
    def available(self) -> bool:
        """Return True if entity is available."""
        return self._available

    @property
    def device_info(self) -> Dict[str, Any]:
        """Return device information."""
        return {
            "identifiers": {(DOMAIN, self._entry_id)},
            "name": self._device_name,
            "manufacturer": "Tasmota",
            "model": "红外遥控器",
            "sw_version": "1.0.0",
        }

    @property
    def icon(self) -> str:
        """Return the icon for the button."""
        # 根据按键名称返回合适的图标
        button_name_lower = self._button_name.lower()
        
        if "power" in button_name_lower or "电源" in button_name_lower or "开关" in button_name_lower:
            return "mdi:power"
        elif "vol" in button_name_lower or "音量" in button_name_lower:
            return "mdi:volume-high"
        elif "ch" in button_name_lower or "频道" in button_name_lower:
            return "mdi:television-guide"
        elif any(num in button_name_lower for num in ["0", "1", "2", "3", "4", "5", "6", "7", "8", "9"]):
            return "mdi:numeric"
        elif "menu" in button_name_lower or "菜单" in button_name_lower:
            return "mdi:menu"
        elif "home" in button_name_lower or "主页" in button_name_lower:
            return "mdi:home"
        elif "back" in button_name_lower or "返回" in button_name_lower:
            return "mdi:arrow-left"
        elif "up" in button_name_lower or "↑" in button_name_lower:
            return "mdi:arrow-up"
        elif "down" in button_name_lower or "↓" in button_name_lower:
            return "mdi:arrow-down"
        elif "left" in button_name_lower or "←" in button_name_lower:
            return "mdi:arrow-left"
        elif "right" in button_name_lower or "→" in button_name_lower:
            return "mdi:arrow-right"
        elif "ok" in button_name_lower or "确定" in button_name_lower:
            return "mdi:check-circle"
        elif "play" in button_name_lower or "播放" in button_name_lower:
            return "mdi:play"
        elif "pause" in button_name_lower or "暂停" in button_name_lower:
            return "mdi:pause"
        elif "stop" in button_name_lower or "停止" in button_name_lower:
            return "mdi:stop"
        else:
            return "mdi:remote"

    async def async_press(self) -> None:
        """Handle the button press."""
        try:
            # 构建红外命令
            ir_data = {
                "Protocol": self._button_data["protocol"],
                "Bits": self._button_data["bits"],
                "Data": self._button_data["data"],
                "Repeat": self._button_data.get("repeat", 0)
            }

            _LOGGER.info("发送红外命令到 %s: %s = %s", self._device_ip, self._button_name, ir_data)

            # 编码命令
            command_json = json.dumps(ir_data, separators=(',', ':'))
            import urllib.parse
            encoded_command = urllib.parse.quote(command_json)
            
            # 发送HTTP请求
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
            _LOGGER.error("发送红外命令失败 %s 到 %s: %s", self._button_name, self._device_ip, e)
            self._available = False

    async def async_update(self) -> None:
        """Update the entity."""
        try:
            # 测试设备可用性
            url = f"http://{self._device_ip}/cm?cmnd=Status"
            response = await self.hass.async_add_executor_job(
                requests.get, url, {"timeout": 5}
            )
            response.raise_for_status()
            self._available = True
            
        except Exception as e:
            _LOGGER.debug("设备 %s 不可用: %s", self._device_ip, e)
            self._available = False