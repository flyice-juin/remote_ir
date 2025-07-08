"""
Tasmota IR Integration for Home Assistant
支持通过HTTP API控制Tasmota红外设备
"""
import logging
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant

_LOGGER = logging.getLogger(__name__)

DOMAIN = "tasmota_ir"

async def async_setup(hass: HomeAssistant, config: dict):
    """Set up the Tasmota IR component."""
    return True

async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry):
    """Set up Tasmota IR from a config entry."""
    hass.data.setdefault(DOMAIN, {})
    
    # 根据设备类型只设置对应的平台
    device_type = entry.data.get("device_type", "climate")
    
    if device_type == "climate":
        platforms = ["climate"]
    elif device_type == "fan":
        platforms = ["fan"]
    elif device_type == "remote":
        # 遥控器类型创建button实体而不是remote实体
        platforms = ["button"]
    else:
        _LOGGER.error("Unknown device type: %s", device_type)
        return False
    
    # 只为指定的设备类型创建平台
    for platform in platforms:
        hass.async_create_task(
            hass.config_entries.async_forward_entry_setup(entry, platform)
        )
    
    return True

async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry):
    """Unload a config entry."""
    device_type = entry.data.get("device_type", "climate")
    
    if device_type == "climate":
        platforms = ["climate"]
    elif device_type == "fan":
        platforms = ["fan"]
    elif device_type == "remote":
        platforms = ["button"]
    else:
        platforms = []
    
    # 修复异步卸载问题 - 正确处理异步操作
    unload_tasks = []
    for platform in platforms:
        unload_tasks.append(
            hass.config_entries.async_forward_entry_unload(entry, platform)
        )
    
    # 等待所有卸载任务完成
    if unload_tasks:
        unload_results = await asyncio.gather(*unload_tasks, return_exceptions=True)
        unload_ok = all(
            result is True or not isinstance(result, Exception) 
            for result in unload_results
        )
    else:
        unload_ok = True
    
    if unload_ok:
        hass.data[DOMAIN].pop(entry.entry_id, None)
    
    return unload_ok

# 添加必要的导入
import asyncio