import logging
import time
from homeassistant.core import callback
from homeassistant.helpers import entity_registry
from homeassistant.helpers.update_coordinator import CoordinatorEntity
from homeassistant.helpers.restore_state import RestoreEntity
from homeassistant.components.climate import ClimateEntity
from homeassistant.components.climate.const import (
    FAN_AUTO,
    HVACMode,
    HVACAction,
    ClimateEntityFeature
)
from homeassistant.const import (
    EVENT_STATE_CHANGED,
    ATTR_ENTITY_ID,
    UnitOfTemperature
)
from homeassistant.const import EVENT_STATE_CHANGED, UnitOfTemperature
from .const import (
    DOMAIN,
    CLIMATE_COORDINATOR,
    DEVICE_TYPE_CLIMATE,
    CONF_DEVICE_TYPE,
    HVAC_ACTIONS,
)
from .helpers import valid_sensor_state
from .entity import TuyaClimateEntity

_LOGGER = logging.getLogger(__package__)


async def async_setup_entry(hass, config_entry, async_add_entities):
    device_type = config_entry.data.get(CONF_DEVICE_TYPE, None)
    if device_type == DEVICE_TYPE_CLIMATE: 
        coordinator = hass.data.get(DOMAIN).get(CLIMATE_COORDINATOR)
        registry = entity_registry.async_get(hass)
        async_add_entities([TuyaClimate(config_entry.data, coordinator, registry)])


class TuyaClimate(ClimateEntity, RestoreEntity, CoordinatorEntity, TuyaClimateEntity):
    def __init__(self, config, coordinator, registry):
        TuyaClimateEntity.__init__(self, config, registry)
        super().__init__(coordinator, context=self._climate_id)
        self._ac_mode = False
        self._last_mode_switch = 0

    @property
    def name(self):
        return self._name

    @property
    def unique_id(self):
        return self.climate_unique_id()

    @property
    def device_info(self):
        return self.tuya_device_info()

    @property
    def available(self):
        return self.coordinator.is_available(self._climate_id)

    @property
    def temperature_unit(self):
        return UnitOfTemperature.CELSIUS

    @property
    def supported_features(self):
        return (
            ClimateEntityFeature.TURN_OFF
            | ClimateEntityFeature.TURN_ON
            | ClimateEntityFeature.TARGET_TEMPERATURE
            | ClimateEntityFeature.FAN_MODE
        )

    @property
    def min_temp(self):
        return self._min_temp

    @property
    def max_temp(self):
        return self._max_temp

    @property
    def target_temperature_step(self):
        return self._temp_step

    @property
    def current_temperature(self):
        return self.get_temperature_value(convert = True)
    
    @property
    def current_humidity(self):
        return self.get_humidity_value()

    @property
    def hvac_modes(self):
        return self._hvac_modes

    @property
    def fan_modes(self):
        return self._fan_modes

    @property
    def too_cold(self):
        if self.current_temperature is None or self.target_temperature is None:
            return False
        return self.current_temperature < float(self.target_temperature - self._temp_threshold)

    @property
    def too_hot(self):
        if self.current_temperature is None or self.target_temperature is None:
            return False
        return float(self.current_temperature) >= self.target_temperature

    @property
    def hvac_action(self):
        """Return the current running hvac operation."""

        _LOGGER.debug(f"current_temp {self.current_temperature}")
        _LOGGER.debug(f"target_temp {self.target_temperature}")
        _LOGGER.debug(f"too_hot {self.too_hot}")
        _LOGGER.debug(f"too_cold {self.too_cold}")

        self._attr_hvac_action = HVAC_ACTIONS[self._attr_hvac_mode]

        if self._attr_hvac_mode == HVACMode.COOL:
            self._attr_hvac_action = (
                HVACAction.COOLING if not self.too_cold else HVACAction.IDLE
            )

        if self._attr_hvac_mode == HVACMode.HEAT:
            self._attr_hvac_action = (
                HVACAction.HEATING if not self.too_hot else HVACAction.IDLE
            )

        return self._attr_hvac_action

    async def async_added_to_hass(self):
        await super().async_added_to_hass()
        self.load_optional_entities()
        self.hass.bus.async_listen(EVENT_STATE_CHANGED, self._async_handle_event)
        last_state = await self.async_get_last_state()
        if valid_sensor_state(last_state):
            self._attr_hvac_mode = last_state.state
            self._attr_target_temperature = last_state.attributes.get("temperature")
            self._attr_fan_mode = last_state.attributes.get("fan_mode")
        else:
            self._attr_hvac_mode = HVACMode.OFF
            self._attr_target_temperature = 0
            self._attr_fan_mode = FAN_AUTO

    @callback
    async def _async_handle_event(self, event):
        if event.data.get(ATTR_ENTITY_ID) in [self._temperature_sensor, self._humidity_sensor]:
            self.async_write_ha_state()

    @callback
    def _handle_coordinator_update(self):
        """Handle updated data from the coordinator."""
        data = self.coordinator.data.get(self._climate_id)
        if not data:
            return
        # self._attr_hvac_mode = data.hvac_mode if self._ac_mode else HVACMode.OFF
        self._attr_hvac_mode = data.hvac_mode if data.power else HVACMode.OFF
        self._attr_target_temperature = data.temperature
        self._attr_fan_mode = data.fan_mode
        self._async_control_cooling()
        self.async_write_ha_state()

    async def async_turn_on(self):
        _LOGGER.info(f"{self.entity_id} turn on")
        await self.coordinator.async_turn_on(self._infrared_id, self._climate_id)
        self._handle_coordinator_update()

    async def async_turn_off(self):
        _LOGGER.info(f"{self.entity_id} turn off")
        await self.coordinator.async_turn_off(self._infrared_id, self._climate_id)
        self._handle_coordinator_update()

    async def async_set_temperature(self, **kwargs):
        temperature = kwargs.get("temperature", None)
        hvac_mode = kwargs.get("hvac_mode", None)
        if temperature is not None and hvac_mode is not None:
            if hvac_mode is HVACMode.OFF:
                _LOGGER.info(f"{self.entity_id} setting hvac mode to off")
                await self.coordinator.async_turn_off(self._infrared_id, self._climate_id)
            else:
                _LOGGER.info(f"{self.entity_id} setting temperature to {temperature} and hvac mode to {hvac_mode}")
                fan_mode = self.get_hvac_fan_mode(hvac_mode)
                if self.get_hvac_power_on(self._attr_hvac_mode):
                    await self.coordinator.async_turn_on(self._infrared_id, self._climate_id)
                await self.coordinator.async_set_hvac_mode(self._infrared_id, self._climate_id, hvac_mode, temperature, fan_mode)
            self._handle_coordinator_update()
        elif temperature is not None:
            _LOGGER.info(f"{self.entity_id} setting temperature to {temperature}")
            if self.get_temp_power_on(self._attr_hvac_mode):
                await self.coordinator.async_turn_on(
                    self._infrared_id, self._climate_id
                )
            await self.coordinator.async_set_temperature(
                self._infrared_id, self._climate_id, temperature
            )
            self._handle_coordinator_update()

    async def async_set_fan_mode(self, fan_mode):
        _LOGGER.info(f"{self.entity_id} setting fan mode to {fan_mode}")
        if self.get_fan_power_on(self._attr_hvac_mode):
            await self.coordinator.async_turn_on(self._infrared_id, self._climate_id)
        await self.coordinator.async_set_fan_mode(
            self._infrared_id, self._climate_id, fan_mode
        )
        self._handle_coordinator_update()

    async def async_set_hvac_mode(self, hvac_mode):
        _LOGGER.info(f"{self.entity_id} setting hvac mode to {hvac_mode}")
        if hvac_mode is HVACMode.OFF:
            self._attr_hvac_mode = HVACMode.OFF
            self._ac_mode = False
            await self.coordinator.async_turn_off(self._infrared_id, self._climate_id)
        else:
            temperature = self.get_hvac_temperature(hvac_mode)
            fan_mode = self.get_hvac_fan_mode(hvac_mode)
            if self.get_hvac_power_on(self._attr_hvac_mode):
                await self.coordinator.async_turn_on(
                    self._infrared_id, self._climate_id
                )
            await self.coordinator.async_set_hvac_mode(
                self._infrared_id, self._climate_id, hvac_mode, temperature, fan_mode
            )
        self._handle_coordinator_update()

    _MODE_SWITCH_COOLDOWN = 10  # seconds

    def _async_control_cooling(self):
        """Check if we need to switch hvac mode based on temperature thresholds."""

        _LOGGER.debug(f"_async_control_cooling: hvac_mode={self._attr_hvac_mode}, too_cold={self.too_cold}, too_hot={self.too_hot}")

        # When mode is COOL and temperature is too cold, switch to FAN_ONLY mode
        if self._attr_hvac_mode == HVACMode.COOL and self.too_cold:
            elapsed = time.time() - self._last_mode_switch
            if elapsed < self._MODE_SWITCH_COOLDOWN:
                _LOGGER.debug(
                    f"{self.entity_id} too_cold but cooldown active ({elapsed:.1f}s / {self._MODE_SWITCH_COOLDOWN}s)"
                )
                return
            _LOGGER.info(
                f"{self.entity_id} too_cold reached (current={self.current_temperature}, "
                f"target={self.target_temperature}), switching to FAN_ONLY mode"
            )
            self.hass.async_create_task(self._async_switch_to_fan_mode())
            return

        # When mode is FAN_ONLY and temperature is too hot, switch back to COOL mode
        if self._attr_hvac_mode == HVACMode.FAN_ONLY and self.too_hot:
            elapsed = time.time() - self._last_mode_switch
            if elapsed < self._MODE_SWITCH_COOLDOWN:
                _LOGGER.debug(
                    f"{self.entity_id} too_hot but cooldown active ({elapsed:.1f}s / {self._MODE_SWITCH_COOLDOWN}s)"
                )
                return
            _LOGGER.info(
                f"{self.entity_id} too_hot reached (current={self.current_temperature}, "
                f"target={self.target_temperature}), switching back to COOL mode"
            )
            self.hass.async_create_task(self._async_switch_to_cool_mode())
            return

    async def _async_switch_to_fan_mode(self):
        """Switch to FAN_ONLY mode when too_cold."""
        _LOGGER.info(f"{self.entity_id} switching to FAN_ONLY mode")
        temperature = self.get_hvac_temperature(HVACMode.FAN_ONLY)
        fan_mode = self.get_hvac_fan_mode(HVACMode.FAN_ONLY)
        await self.coordinator.async_set_hvac_mode(
            self._infrared_id, self._climate_id, HVACMode.FAN_ONLY, temperature, fan_mode
        )
        self._attr_hvac_mode = HVACMode.FAN_ONLY
        self._last_mode_switch = time.time()
        self.async_write_ha_state()

    async def _async_switch_to_cool_mode(self):
        """Switch back to COOL mode when too_hot."""
        _LOGGER.info(f"{self.entity_id} switching back to COOL mode")
        temperature = self.get_hvac_temperature(HVACMode.COOL)
        fan_mode = self.get_hvac_fan_mode(HVACMode.COOL)
        await self.coordinator.async_set_hvac_mode(
            self._infrared_id, self._climate_id, HVACMode.COOL, temperature, fan_mode
        )
        self._attr_hvac_mode = HVACMode.COOL
        self._last_mode_switch = time.time()
        self.async_write_ha_state()
