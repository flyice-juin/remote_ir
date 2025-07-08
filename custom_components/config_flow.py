"""Config flow for Tasmota IR integration."""
import logging
import json
import voluptuous as vol
import requests
from homeassistant import config_entries
from homeassistant.const import CONF_HOST, CONF_NAME
from homeassistant.core import HomeAssistant, callback
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers import config_validation as cv

from .const import DOMAIN, CONF_DEVICE_IP, CONF_VENDOR, CONF_IR_CODES, CONF_BUTTONS

_LOGGER = logging.getLogger(__name__)

# 设备类型选择
DEVICE_TYPES = {
    "climate": "空调 (Climate)",
    "fan": "风扇 (Fan)", 
    "remote": "万能遥控器 (Button)"
}

# 步骤1: 基本设备信息
STEP_USER_DATA_SCHEMA = vol.Schema({
    vol.Required(CONF_HOST): str,
    vol.Required(CONF_NAME, default="Tasmota IR Device"): str,
    vol.Required("device_type", default="climate"): vol.In(DEVICE_TYPES),
})

# 步骤2: 空调配置
STEP_CLIMATE_DATA_SCHEMA = vol.Schema({
    vol.Required(CONF_VENDOR, default="COOLIX"): str,
    vol.Optional("import_config", default=""): str,
})

# 步骤3: 风扇配置  
STEP_FAN_DATA_SCHEMA = vol.Schema({
    vol.Optional("import_config", default=""): str,
})

# 步骤4: 遥控器配置
STEP_REMOTE_DATA_SCHEMA = vol.Schema({
    vol.Optional("import_config", default=""): str,
})

async def validate_input(hass: HomeAssistant, data: dict) -> dict:
    """Validate the user input allows us to connect."""
    host = data[CONF_HOST]
    
    # Test connection to Tasmota device
    try:
        url = f"http://{host}/cm?cmnd=Status"
        response = await hass.async_add_executor_job(
            requests.get, url, {"timeout": 5}
        )
        response.raise_for_status()
        
        # Check if it's a Tasmota device
        result = response.json()
        if "Status" not in result:
            raise InvalidHost("Not a valid Tasmota device")
            
    except requests.exceptions.RequestException:
        raise CannotConnect("Cannot connect to device")
    except Exception:
        raise InvalidHost("Invalid device response")
    
    return {"title": data[CONF_NAME]}

def parse_config_import(config_text: str, device_type: str) -> dict:
    """解析导入的配置文本"""
    try:
        # 尝试解析JSON格式
        if config_text.strip().startswith('{'):
            config_data = json.loads(config_text)
        else:
            # 尝试解析YAML格式的简单键值对
            config_data = {}
            for line in config_text.strip().split('\n'):
                if ':' in line and not line.strip().startswith('#'):
                    key, value = line.split(':', 1)
                    key = key.strip()
                    value = value.strip()
                    
                    # 尝试解析JSON值
                    try:
                        if value.startswith('{') or value.startswith('['):
                            value = json.loads(value)
                        elif value.lower() in ['true', 'false']:
                            value = value.lower() == 'true'
                        elif value.isdigit():
                            value = int(value)
                        elif value.replace('.', '').isdigit():
                            value = float(value)
                    except:
                        pass
                    
                    config_data[key] = value
        
        return config_data
        
    except Exception as e:
        _LOGGER.error(f"Failed to parse config: {e}")
        return {}

class ConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Handle a config flow for Tasmota IR."""

    VERSION = 1

    def __init__(self):
        """Initialize the config flow."""
        self.data = {}

    async def async_step_user(self, user_input=None):
        """Handle the initial step."""
        if user_input is None:
            return self.async_show_form(
                step_id="user", 
                data_schema=STEP_USER_DATA_SCHEMA,
                description_placeholders={
                    "device_types": "\n".join([f"• {v}" for v in DEVICE_TYPES.values()])
                }
            )

        errors = {}

        try:
            info = await validate_input(self.hass, user_input)
            
            # 检查是否已经存在相同的设备
            device_ip = user_input[CONF_HOST]
            device_type = user_input["device_type"]
            device_name = user_input[CONF_NAME]
            
            # 生成唯一ID
            unique_id = f"tasmota_ir_{device_type}_{device_ip.replace('.', '_')}_{device_name.replace(' ', '_')}"
            
            # 检查唯一ID是否已存在
            await self.async_set_unique_id(unique_id)
            self._abort_if_unique_id_configured()
            
            # 将host转换为device_ip
            user_input[CONF_DEVICE_IP] = user_input.pop(CONF_HOST)
            self.data.update(user_input)
            
            # 根据设备类型跳转到相应的配置步骤
            device_type = user_input["device_type"]
            if device_type == "climate":
                return await self.async_step_climate()
            elif device_type == "fan":
                return await self.async_step_fan()
            elif device_type == "remote":
                return await self.async_step_remote()
                
        except CannotConnect:
            errors["base"] = "cannot_connect"
        except InvalidHost:
            errors["base"] = "invalid_host"
        except Exception:  # pylint: disable=broad-except
            _LOGGER.exception("Unexpected exception")
            errors["base"] = "unknown"

        return self.async_show_form(
            step_id="user", 
            data_schema=STEP_USER_DATA_SCHEMA, 
            errors=errors,
            description_placeholders={
                "device_types": "\n".join([f"• {v}" for v in DEVICE_TYPES.values()])
            }
        )

    async def async_step_climate(self, user_input=None):
        """Handle climate device configuration."""
        if user_input is None:
            return self.async_show_form(
                step_id="climate",
                data_schema=STEP_CLIMATE_DATA_SCHEMA,
                description_placeholders={
                    "example_config": """示例配置格式:
{
  "vendor": "COOLIX",
  "supported_modes": ["off", "auto", "cool", "heat", "dry", "fan_only"],
  "min_temp": 16,
  "max_temp": 30
}

或者从软件导出的配置:
vendor: COOLIX
min_temp: 16
max_temp: 30"""
                }
            )

        # 处理导入的配置
        imported_config = {}
        if user_input.get("import_config"):
            imported_config = parse_config_import(user_input["import_config"], "climate")

        # 合并配置
        final_data = {
            **self.data,
            CONF_VENDOR: user_input.get(CONF_VENDOR) or imported_config.get("vendor", "COOLIX"),
            "supported_modes": imported_config.get("supported_modes", ["off", "auto", "cool", "heat", "dry", "fan_only"]),
            "supported_fan_modes": imported_config.get("supported_fan_modes", ["auto", "low", "medium", "high"]),
            "min_temp": imported_config.get("min_temp", 16),
            "max_temp": imported_config.get("max_temp", 30),
            "temp_step": imported_config.get("temp_step", 0.5),
            "swing_modes": imported_config.get("swing_modes", ["off", "vertical", "horizontal", "both"])
        }

        return self.async_create_entry(
            title=f"{self.data[CONF_NAME]} (空调)",
            data=final_data
        )

    async def async_step_fan(self, user_input=None):
        """Handle fan device configuration."""
        if user_input is None:
            return self.async_show_form(
                step_id="fan",
                data_schema=STEP_FAN_DATA_SCHEMA,
                description_placeholders={
                    "example_config": """示例配置格式:
{
  "fan_config": {
    "speed_count": 5,
    "oscillation_supported": true,
    "timer_supported": false,
    "preset_modes": ["自然风", "睡眠模式"]
  },
  "ir_codes": {
    "power": {"protocol": "NEC", "bits": 32, "data": "0x8166817E"},
    "speed_1": {"protocol": "NEC", "bits": 32, "data": "0x8166A15E"},
    "speed_2": {"protocol": "NEC", "bits": 32, "data": "0x816651AE"},
    "speed_3": {"protocol": "NEC", "bits": 32, "data": "0x8166D12E"},
    "speed_4": {"protocol": "NEC", "bits": 32, "data": "0x8166B14E"},
    "speed_5": {"protocol": "NEC", "bits": 32, "data": "0x8166C13E"},
    "swing": {"protocol": "NEC", "bits": 32, "data": "0x8166B14E"},
    "preset_自然风": {"protocol": "NEC", "bits": 32, "data": "0x8166E11E"},
    "preset_睡眠模式": {"protocol": "NEC", "bits": 32, "data": "0x8166F10E"}
  }
}

或者从软件导出的配置直接粘贴"""
                }
            )

        # 处理导入的配置
        imported_config = {}
        if user_input.get("import_config"):
            imported_config = parse_config_import(user_input["import_config"], "fan")

        # 提取风扇配置和红外码
        fan_config = imported_config.get("fan_config", {
            "speed_count": 3,
            "oscillation_supported": True,
            "timer_supported": False,
            "preset_modes": []
        })
        
        ir_codes = imported_config.get("ir_codes", {})

        # 合并配置
        final_data = {
            **self.data,
            "fan_config": fan_config,
            CONF_IR_CODES: ir_codes,
            "supported_speeds": [f"{i}档" for i in range(1, fan_config.get("speed_count", 3) + 1)],
            "oscillation_supported": fan_config.get("oscillation_supported", True),
            "preset_modes": fan_config.get("preset_modes", [])
        }

        # 生成标题
        speed_count = fan_config.get("speed_count", 3)
        preset_count = len(fan_config.get("preset_modes", []))
        title_parts = [f"{speed_count}档风扇"]
        if preset_count > 0:
            title_parts.append(f"{preset_count}个预设")

        return self.async_create_entry(
            title=f"{self.data[CONF_NAME]} ({', '.join(title_parts)})",
            data=final_data
        )

    async def async_step_remote(self, user_input=None):
        """Handle remote device configuration."""
        if user_input is None:
            return self.async_show_form(
                step_id="remote",
                data_schema=STEP_REMOTE_DATA_SCHEMA,
                description_placeholders={
                    "example_config": """示例配置格式:
{
  "buttons": {
    "开关1": {"protocol": "NEC", "bits": 32, "data": "0x44BB01FE"},
    "1": {"protocol": "NEC", "bits": 32, "data": "0x44BB817E"},
    "音量+": {"protocol": "NEC", "bits": 32, "data": "0x8166D12E"},
    "频道+": {"protocol": "NEC", "bits": 32, "data": "0x8166B14E"}
  }
}

或者从软件导出的配置直接粘贴"""
                }
            )

        # 处理导入的配置
        imported_config = {}
        if user_input.get("import_config"):
            imported_config = parse_config_import(user_input["import_config"], "remote")

        # 合并配置
        final_data = {
            **self.data,
            CONF_BUTTONS: imported_config.get("buttons", {})
        }

        # 检查是否有按键配置
        buttons = final_data.get(CONF_BUTTONS, {})
        if not buttons:
            return self.async_show_form(
                step_id="remote",
                data_schema=STEP_REMOTE_DATA_SCHEMA,
                errors={"base": "no_buttons"},
                description_placeholders={
                    "example_config": """请导入包含按键配置的数据，例如:
{
  "buttons": {
    "开关1": {"protocol": "NEC", "bits": 32, "data": "0x44BB01FE"},
    "1": {"protocol": "NEC", "bits": 32, "data": "0x44BB817E"}
  }
}"""
                }
            )

        button_count = len(buttons)
        return self.async_create_entry(
            title=f"{self.data[CONF_NAME]} ({button_count}个按键)",
            data=final_data
        )

    @staticmethod
    @callback
    def async_get_options_flow(config_entry):
        """Get the options flow for this handler."""
        return OptionsFlowHandler(config_entry)

class OptionsFlowHandler(config_entries.OptionsFlow):
    """Handle options flow for Tasmota IR."""

    def __init__(self, config_entry):
        """Initialize options flow."""
        self.config_entry = config_entry

    async def async_step_init(self, user_input=None):
        """Manage the options."""
        if user_input is not None:
            # 处理配置更新
            if user_input.get("update_device_config"):
                # 跳转到设备特定的配置更新
                device_type = self.config_entry.data.get("device_type", "climate")
                
                if device_type == "climate":
                    return await self.async_step_climate_options()
                elif device_type == "fan":
                    return await self.async_step_fan_options()
                elif device_type == "remote":
                    return await self.async_step_remote_options()
            
            # 更新设备IP - 修复重新加载问题
            if "device_ip" in user_input and user_input["device_ip"] != self.config_entry.data.get(CONF_DEVICE_IP):
                # 创建新的数据字典，包含更新的IP
                new_data = dict(self.config_entry.data)
                new_data[CONF_DEVICE_IP] = user_input["device_ip"]
                
                # 更新配置条目
                self.hass.config_entries.async_update_entry(
                    self.config_entry, data=new_data
                )
                
                # 重新加载集成以应用新的IP配置
                await self.hass.config_entries.async_reload(self.config_entry.entry_id)
                
                return self.async_create_entry(title="", data={})
            
            # 如果没有任何更改，直接返回
            return self.async_create_entry(title="", data={})

        # 显示选项菜单
        device_type = self.config_entry.data.get("device_type", "climate")
        current_ip = self.config_entry.data.get(CONF_DEVICE_IP, "")
        
        # 显示设备特定信息
        extra_info = ""
        if device_type == "climate":
            vendor = self.config_entry.data.get(CONF_VENDOR, "Unknown")
            extra_info = f"\n空调品牌: {vendor}"
        elif device_type == "fan":
            fan_config = self.config_entry.data.get("fan_config", {})
            speed_count = fan_config.get("speed_count", 3)
            preset_count = len(fan_config.get("preset_modes", []))
            extra_info = f"\n风扇档位: {speed_count}档"
            if preset_count > 0:
                extra_info += f", {preset_count}个预设模式"
        elif device_type == "remote":
            buttons = self.config_entry.data.get(CONF_BUTTONS, {})
            extra_info = f"\n按键数量: {len(buttons)}"
        
        options_schema = vol.Schema({
            vol.Optional("device_ip", default=current_ip): str,
            vol.Optional("update_device_config", default=False): bool,
        })
        
        return self.async_show_form(
            step_id="init",
            data_schema=options_schema,
            description_placeholders={
                "device_type": DEVICE_TYPES.get(device_type, device_type),
                "current_ip": current_ip,
                "extra_info": extra_info
            }
        )

    async def async_step_climate_options(self, user_input=None):
        """Handle climate options."""
        if user_input is not None:
            # 处理更新的配置
            new_data = dict(self.config_entry.data)
            
            # 更新空调品牌
            if user_input.get(CONF_VENDOR):
                new_data[CONF_VENDOR] = user_input[CONF_VENDOR]
            
            # 处理导入的配置
            if user_input.get("update_config"):
                imported_config = parse_config_import(user_input["update_config"], "climate")
                if imported_config:
                    # 更新相关配置
                    if "vendor" in imported_config:
                        new_data[CONF_VENDOR] = imported_config["vendor"]
                    if "supported_modes" in imported_config:
                        new_data["supported_modes"] = imported_config["supported_modes"]
                    if "supported_fan_modes" in imported_config:
                        new_data["supported_fan_modes"] = imported_config["supported_fan_modes"]
                    if "min_temp" in imported_config:
                        new_data["min_temp"] = imported_config["min_temp"]
                    if "max_temp" in imported_config:
                        new_data["max_temp"] = imported_config["max_temp"]
                    if "temp_step" in imported_config:
                        new_data["temp_step"] = imported_config["temp_step"]
                    if "swing_modes" in imported_config:
                        new_data["swing_modes"] = imported_config["swing_modes"]
            
            # 更新配置条目
            self.hass.config_entries.async_update_entry(
                self.config_entry, data=new_data
            )
            
            # 重新加载集成以应用新配置
            await self.hass.config_entries.async_reload(self.config_entry.entry_id)
            
            return self.async_create_entry(title="", data={})

        current_vendor = self.config_entry.data.get(CONF_VENDOR, "COOLIX")
        
        return self.async_show_form(
            step_id="climate_options",
            data_schema=vol.Schema({
                vol.Required(CONF_VENDOR, default=current_vendor): str,
                vol.Optional("update_config", default=""): str,
            }),
            description_placeholders={
                "current_config": f"当前空调品牌: {current_vendor}\n\n可以导入新的配置来更新设备设置"
            }
        )

    async def async_step_fan_options(self, user_input=None):
        """Handle fan options."""
        if user_input is not None:
            # 处理更新的配置
            new_data = dict(self.config_entry.data)
            
            if user_input.get("update_config"):
                imported_config = parse_config_import(user_input["update_config"], "fan")
                if imported_config:
                    # 更新风扇配置
                    if "fan_config" in imported_config:
                        new_data["fan_config"] = imported_config["fan_config"]
                        
                        # 更新相关字段
                        fan_config = imported_config["fan_config"]
                        new_data["supported_speeds"] = [f"{i}档" for i in range(1, fan_config.get("speed_count", 3) + 1)]
                        new_data["oscillation_supported"] = fan_config.get("oscillation_supported", True)
                        new_data["preset_modes"] = fan_config.get("preset_modes", [])
                        
                    # 更新红外码
                    if "ir_codes" in imported_config:
                        new_data[CONF_IR_CODES] = imported_config["ir_codes"]
                        
                    # 更新标题
                    fan_config = new_data.get("fan_config", {})
                    speed_count = fan_config.get("speed_count", 3)
                    preset_count = len(fan_config.get("preset_modes", []))
                    title_parts = [f"{speed_count}档风扇"]
                    if preset_count > 0:
                        title_parts.append(f"{preset_count}个预设")
                    
                    new_title = f"{new_data.get('name', 'Tasmota IR Device')} ({', '.join(title_parts)})"
                    
                    # 更新配置条目
                    self.hass.config_entries.async_update_entry(
                        self.config_entry, 
                        data=new_data,
                        title=new_title
                    )
                    
                    # 重新加载集成以应用新配置
                    await self.hass.config_entries.async_reload(self.config_entry.entry_id)
                    
                    return self.async_create_entry(title="", data={})
            
            # 如果没有配置更新，直接返回
            return self.async_create_entry(title="", data={})

        current_fan_config = self.config_entry.data.get("fan_config", {})
        current_codes = self.config_entry.data.get(CONF_IR_CODES, {})
        
        speed_count = current_fan_config.get("speed_count", 3)
        preset_modes = current_fan_config.get("preset_modes", [])
        
        return self.async_show_form(
            step_id="fan_options",
            data_schema=vol.Schema({
                vol.Optional("update_config", default=""): str,
            }),
            description_placeholders={
                "current_config": f"当前风扇配置:\n档位数量: {speed_count}\n预设模式: {', '.join(preset_modes) if preset_modes else '无'}\n已配置按键: {len(current_codes)}\n\n可以导入新的配置来更新风扇设置"
            }
        )

    async def async_step_remote_options(self, user_input=None):
        """Handle remote options."""
        if user_input is not None:
            # 处理更新的配置
            new_data = dict(self.config_entry.data)
            
            if user_input.get("update_config"):
                imported_config = parse_config_import(user_input["update_config"], "remote")
                if imported_config and "buttons" in imported_config:
                    new_data[CONF_BUTTONS] = imported_config["buttons"]
                    
                    # 更新标题以反映新的按键数量
                    button_count = len(imported_config["buttons"])
                    device_name = self.config_entry.data.get("name", "Tasmota IR Device")
                    new_title = f"{device_name} ({button_count}个按键)"
                    
                    # 更新配置条目
                    self.hass.config_entries.async_update_entry(
                        self.config_entry, 
                        data=new_data,
                        title=new_title
                    )
                    
                    # 重新加载集成以应用新配置
                    await self.hass.config_entries.async_reload(self.config_entry.entry_id)
                    
                    return self.async_create_entry(title="", data={})
            
            # 如果没有配置更新，直接返回
            return self.async_create_entry(title="", data={})

        current_buttons = self.config_entry.data.get(CONF_BUTTONS, {})
        
        return self.async_show_form(
            step_id="remote_options",
            data_schema=vol.Schema({
                vol.Optional("update_config", default=""): str,
            }),
            description_placeholders={
                "current_config": f"当前按键数量: {len(current_buttons)}\n按键列表: {', '.join(current_buttons.keys()) if current_buttons else '无'}\n\n可以导入新的配置来更新按键设置"
            }
        )

class CannotConnect(HomeAssistantError):
    """Error to indicate we cannot connect."""

class InvalidHost(HomeAssistantError):
    """Error to indicate there is invalid host."""