import voluptuous as vol
from homeassistant import config_entries
from homeassistant.core import callback
from homeassistant import data_entry_flow
from homeassistant.helpers import entity_registry
from homeassistant.helpers.selector import (
    BooleanSelector,
    EntitySelector,
    EntitySelectorConfig,
    NumberSelector,
    NumberSelectorConfig,
    NumberSelectorMode,
    SelectSelector,
    SelectSelectorConfig,
    SelectSelectorMode,
    TextSelector,
    TextSelectorConfig,
    TextSelectorType
)
from homeassistant.const import (
    CONF_NAME,
    Platform
)
from homeassistant.components.sensor.const import SensorDeviceClass
from .const import (
    DOMAIN,
    CLIENT,
    DEVICE_TYPE_CLIMATE,
    DEVICE_TYPE_GENERIC,
    CONF_DEVICE_TYPE,
    CONF_INFRARED_ID,
    CONF_DEVICE_ID,
    CONF_TEMPERATURE_SENSOR,
    CONF_HUMIDITY_SENSOR,
    CONF_TEMP_MIN,
    CONF_TEMP_MAX,
    CONF_TEMP_STEP,
    CONF_HVAC_MODES,
    CONF_FAN_MODES,
    CONF_TEMP_HVAC_MODE,
    CONF_FAN_HVAC_MODE,
    CONF_EXTRA_SENSORS,
    CONF_COMPATIBILITY_OPTIONS,
    CONF_HVAC_POWER_ON,
    CONF_TEMP_POWER_ON,
    CONF_FAN_POWER_ON,
    CONF_DRY_MIN_TEMP,
    CONF_DRY_MIN_FAN,
    DEFAULT_DEVICE_TYPES,
    DEFAULT_MIN_TEMP,
    DEFAULT_MAX_TEMP,
    DEFAULT_PRECISION,
    DEFAULT_HVAC_MODES,
    DEFAULT_FAN_MODES,
    DEFAULT_TEMP_HVAC_MODE,
    DEFAULT_FAN_HVAC_MODE,
    DEFAULT_EXTRA_SENSORS,
    DEFAULT_HVAC_POWER_ON,
    DEFAULT_TEMP_POWER_ON,
    DEFAULT_FAN_POWER_ON,
    DEFAULT_DRY_MIN_TEMP,
    DEFAULT_DRY_MIN_FAN,
    DEFAULT_POWER_ON_MODES
)
from .api import (
    TuyaClimateAPI,
    TuyaGenericAPI
)


class ConfigFlowHandler(config_entries.ConfigFlow, domain=DOMAIN):
    VERSION = 1
    MINOR_VERSION = 1
    CONNECTION_CLASS = config_entries.CONN_CLASS_CLOUD_POLL
    
    async def async_step_user(self, user_input):
        if self.hass.data.get(DOMAIN, {}).get(CLIENT, None) is None:
            return self.async_abort(reason="credentials")

        if user_input is not None:
            device_type = user_input.get(CONF_DEVICE_TYPE)
            
            if device_type == DEVICE_TYPE_CLIMATE:
                return await self.async_step_climate()
                
            if device_type == DEVICE_TYPE_GENERIC:
                return await self.async_step_generic()

        data_schema = vol.Schema({
            vol.Required(CONF_DEVICE_TYPE): SelectSelector(
                SelectSelectorConfig(options=DEFAULT_DEVICE_TYPES, multiple=False, mode=SelectSelectorMode.DROPDOWN, translation_key=CONF_DEVICE_TYPE)
            )
        })
        return self.async_show_form(step_id="user", data_schema=data_schema, last_step=False)


    async def async_step_climate(self, user_input=None):
        errors = {}

        if user_input is not None:
            overwrite_invalid_user_input(user_input)
            client = self.hass.data.get(DOMAIN, {}).get(CLIENT)
            infrared_id = user_input.get(CONF_INFRARED_ID)
            climate_id = user_input.get(CONF_DEVICE_ID)
            registry = entity_registry.async_get(self.hass)
            entity_id = registry.async_get_entity_id(Platform.CLIMATE, DOMAIN, f"{infrared_id}_{climate_id}")
            if entity_id is not None:
                errors["base"] = "already_configured"
            elif not await async_is_valid_climate(self.hass, infrared_id, climate_id):
                errors["base"] = "connection"
            else:
                user_input[CONF_DEVICE_TYPE] = DEVICE_TYPE_CLIMATE
                return self.async_create_entry(title=user_input[CONF_NAME], data=user_input)

        data = {}
        data.update(device_data())
        data.update(climate_data())
        data_schema = vol.Schema(data)
        return self.async_show_form(step_id="climate", data_schema=data_schema, errors=errors)
        
        
    async def async_step_generic(self, user_input=None):
        errors = {}

        if user_input is not None:
            client = self.hass.data.get(DOMAIN, {}).get(CLIENT)
            infrared_id = user_input.get(CONF_INFRARED_ID)
            device_id = user_input.get(CONF_DEVICE_ID)
            if not await async_is_valid_device(self.hass, infrared_id, device_id):
                errors["base"] = "connection"
            else:
                user_input[CONF_DEVICE_TYPE] = DEVICE_TYPE_GENERIC
                return self.async_create_entry(title=user_input[CONF_NAME], data=user_input)
        
        data = {}
        data.update(device_data())
        data_schema = vol.Schema(data)
        return self.async_show_form(step_id="generic", data_schema=data_schema, errors=errors)
        
    @staticmethod
    @callback
    def async_get_options_flow(config_entry):
        return OptionsFlowHandler()


class OptionsFlowHandler(config_entries.OptionsFlow):
    async def async_step_init(self, user_input):
        return await self.async_step_user(user_input)

    async def async_step_user(self, user_input):
        config = {**self.config_entry.data, **self.config_entry.options}
        device_type = config.get(CONF_DEVICE_TYPE, None)
        
        if device_type == DEVICE_TYPE_CLIMATE:
            return await self.async_step_climate()
                
        return self.async_abort(reason="not_configurable")
        
    async def async_step_climate(self, user_input=None):
        if user_input is not None:
            overwrite_invalid_user_input(user_input)
            self.hass.config_entries.async_update_entry(
                self.config_entry, data=self.config_entry.data | user_input
            )
            return self.async_create_entry(title="", data={})

        config = {**self.config_entry.data, **self.config_entry.options}
        data_schema = vol.Schema(climate_data(config))
        return self.async_show_form(step_id="climate", data_schema=data_schema)


def device_data():
    return {
        vol.Required(CONF_INFRARED_ID): TextSelector(
            TextSelectorConfig(type=TextSelectorType.TEXT)
        ),
        vol.Required(CONF_DEVICE_ID): TextSelector(
            TextSelectorConfig(type=TextSelectorType.TEXT)
        ),
        vol.Required(CONF_NAME): TextSelector(
            TextSelectorConfig(type=TextSelectorType.TEXT)
        )
    }

def climate_data(config=None):
    if config is None:
        temperature_sensor = vol.Optional(CONF_TEMPERATURE_SENSOR)
        humidity_sensor = vol.Optional(CONF_HUMIDITY_SENSOR)
        temp_min = vol.Required(CONF_TEMP_MIN, default=DEFAULT_MIN_TEMP)
        temp_max = vol.Required(CONF_TEMP_MAX, default=DEFAULT_MAX_TEMP)
        temp_step = vol.Required(CONF_TEMP_STEP, default=DEFAULT_PRECISION)
        hvac_modes = vol.Required(CONF_HVAC_MODES, default=DEFAULT_HVAC_MODES)
        fan_modes = vol.Required(CONF_FAN_MODES, default=DEFAULT_FAN_MODES)
        temp_hvac_mode = vol.Optional(CONF_TEMP_HVAC_MODE, default=DEFAULT_TEMP_HVAC_MODE)
        fan_hvac_mode = vol.Optional(CONF_FAN_HVAC_MODE, default=DEFAULT_FAN_HVAC_MODE)
        extra_sensors = vol.Optional(CONF_EXTRA_SENSORS, default=DEFAULT_EXTRA_SENSORS)
        hvac_power_on = vol.Optional(CONF_HVAC_POWER_ON, default=DEFAULT_HVAC_POWER_ON)
        temp_power_on = vol.Optional(CONF_TEMP_POWER_ON, default=DEFAULT_TEMP_POWER_ON)
        fan_power_on = vol.Optional(CONF_FAN_POWER_ON, default=DEFAULT_FAN_POWER_ON)
        dry_min_temp = vol.Optional(CONF_DRY_MIN_TEMP, default=DEFAULT_DRY_MIN_TEMP)
        dry_min_fan = vol.Optional(CONF_DRY_MIN_FAN, default=DEFAULT_DRY_MIN_FAN)
    else:
        if config.get(CONF_TEMPERATURE_SENSOR, None) is None:
            temperature_sensor = vol.Optional(CONF_TEMPERATURE_SENSOR)
        else:
            temperature_sensor = vol.Optional(CONF_TEMPERATURE_SENSOR, default=config.get(CONF_TEMPERATURE_SENSOR))

        if config.get(CONF_HUMIDITY_SENSOR, None) is None:
            humidity_sensor = vol.Optional(CONF_HUMIDITY_SENSOR)
        else:
            humidity_sensor = vol.Optional(CONF_HUMIDITY_SENSOR, default=config.get(CONF_HUMIDITY_SENSOR))

        temp_min = vol.Required(CONF_TEMP_MIN, default=config.get(CONF_TEMP_MIN, DEFAULT_MIN_TEMP))
        temp_max = vol.Required(CONF_TEMP_MAX, default=config.get(CONF_TEMP_MAX, DEFAULT_MAX_TEMP))
        temp_step = vol.Required(CONF_TEMP_STEP, default=config.get(CONF_TEMP_STEP, DEFAULT_PRECISION))
        hvac_modes = vol.Required(CONF_HVAC_MODES, default=config.get(CONF_HVAC_MODES, DEFAULT_HVAC_MODES))
        fan_modes = vol.Required(CONF_FAN_MODES, default=config.get(CONF_FAN_MODES, DEFAULT_FAN_MODES))
        temp_hvac_mode = vol.Optional(CONF_TEMP_HVAC_MODE, default=config.get(CONF_TEMP_HVAC_MODE, DEFAULT_TEMP_HVAC_MODE))
        fan_hvac_mode = vol.Optional(CONF_FAN_HVAC_MODE, default=config.get(CONF_FAN_HVAC_MODE, DEFAULT_FAN_HVAC_MODE))
        extra_sensors = vol.Optional(CONF_EXTRA_SENSORS, default=config.get(CONF_EXTRA_SENSORS, DEFAULT_EXTRA_SENSORS))
        hvac_power_on = vol.Optional(CONF_HVAC_POWER_ON, default=config.get(CONF_COMPATIBILITY_OPTIONS, {}).get(CONF_HVAC_POWER_ON, DEFAULT_HVAC_POWER_ON))
        temp_power_on = vol.Optional(CONF_TEMP_POWER_ON, default=config.get(CONF_COMPATIBILITY_OPTIONS, {}).get(CONF_TEMP_POWER_ON, DEFAULT_TEMP_POWER_ON))        
        fan_power_on = vol.Optional(CONF_FAN_POWER_ON, default=config.get(CONF_COMPATIBILITY_OPTIONS, {}).get(CONF_FAN_POWER_ON, DEFAULT_FAN_POWER_ON))        
        dry_min_temp = vol.Optional(CONF_DRY_MIN_TEMP, default=config.get(CONF_COMPATIBILITY_OPTIONS, {}).get(CONF_DRY_MIN_TEMP, DEFAULT_DRY_MIN_TEMP))
        dry_min_fan = vol.Optional(CONF_DRY_MIN_FAN, default=config.get(CONF_COMPATIBILITY_OPTIONS, {}).get(CONF_DRY_MIN_FAN, DEFAULT_DRY_MIN_FAN))

    return {
        temperature_sensor: EntitySelector(
            EntitySelectorConfig(domain=Platform.SENSOR, device_class=SensorDeviceClass.TEMPERATURE, multiple=False)
        ),
        humidity_sensor: EntitySelector(
            EntitySelectorConfig(domain=Platform.SENSOR, device_class=SensorDeviceClass.HUMIDITY, multiple=False)
        ),
        temp_min: NumberSelector(
            NumberSelectorConfig(min=DEFAULT_MIN_TEMP, max=DEFAULT_MAX_TEMP, step=1, mode=NumberSelectorMode.BOX)
        ),
        temp_max: NumberSelector(
            NumberSelectorConfig(min=DEFAULT_MIN_TEMP, max=DEFAULT_MAX_TEMP, step=1, mode=NumberSelectorMode.BOX)
        ),
        temp_step: NumberSelector(
            NumberSelectorConfig(min=0.1, max=1, step=0.1, mode=NumberSelectorMode.BOX)
        ),
        hvac_modes: SelectSelector(
            SelectSelectorConfig(options=DEFAULT_HVAC_MODES, multiple=True, mode=SelectSelectorMode.DROPDOWN, translation_key=CONF_HVAC_MODES)
        ),
        fan_modes: SelectSelector(
            SelectSelectorConfig(options=DEFAULT_FAN_MODES, multiple=True, mode=SelectSelectorMode.DROPDOWN, translation_key=CONF_FAN_MODES)
        ),
        temp_hvac_mode: BooleanSelector(),
        fan_hvac_mode: BooleanSelector(),
        extra_sensors: BooleanSelector(),
        vol.Required(CONF_COMPATIBILITY_OPTIONS): data_entry_flow.section(
            vol.Schema(
                {
                    hvac_power_on: SelectSelector(
                        SelectSelectorConfig(options=DEFAULT_POWER_ON_MODES, multiple=False, mode=SelectSelectorMode.LIST, translation_key=CONF_HVAC_POWER_ON)
                    ),
                    temp_power_on: SelectSelector(
                        SelectSelectorConfig(options=DEFAULT_POWER_ON_MODES, multiple=False, mode=SelectSelectorMode.LIST, translation_key=CONF_TEMP_POWER_ON)
                    ),
                    fan_power_on: SelectSelector(
                        SelectSelectorConfig(options=DEFAULT_POWER_ON_MODES, multiple=False, mode=SelectSelectorMode.LIST, translation_key=CONF_FAN_POWER_ON)
                    ),
                    dry_min_temp: BooleanSelector(),
                    dry_min_fan: BooleanSelector()
                }
            ),
            {"collapsed": True}
        )
    }

async def async_is_valid_climate(hass, infrared_id, climate_id):
    try:
        api = TuyaClimateAPI(hass)
        result = await api.async_fetch_data(infrared_id, climate_id)
        return result
    except Exception as e:
        return False

async def async_is_valid_device(hass, infrared_id, device_id):
    try:
        api = TuyaGenericAPI(hass)
        result = await api.async_fetch_data(infrared_id, device_id)
        return result
    except Exception as e:
        return False

def overwrite_invalid_user_input(user_input):
    hvac_modes = user_input.get(CONF_HVAC_MODES, None)
    if hvac_modes is not None and len(hvac_modes) == 0:
        user_input[CONF_HVAC_MODES] = DEFAULT_HVAC_MODES

    fan_modes = user_input.get(CONF_FAN_MODES, None)
    if fan_modes is not None and len(fan_modes) == 0:
        user_input[CONF_FAN_MODES] = DEFAULT_FAN_MODES