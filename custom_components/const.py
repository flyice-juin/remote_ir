"""Constants for the Tasmota IR integration."""

DOMAIN = "tasmota_ir"

# Configuration keys
CONF_DEVICE_IP = "device_ip"
CONF_VENDOR = "vendor"
CONF_IR_CODES = "ir_codes"
CONF_BUTTONS = "buttons"

# Default values
DEFAULT_NAME = "Tasmota IR Device"
DEFAULT_VENDOR = "COOLIX"

# HVAC constants
HVAC_MODES = ["off", "auto", "cool", "heat", "dry", "fan_only"]
FAN_MODES = ["auto", "low", "medium", "high"]
SWING_MODES = ["off", "vertical", "horizontal", "both"]

# Update intervals
SCAN_INTERVAL = 30  # seconds