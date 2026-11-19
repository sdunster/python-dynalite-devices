"""Support for a Dynalite area's presets as a single select."""

from typing import TYPE_CHECKING, Dict, List, Optional

from .const import CONF_SELECT, CONF_TEMPLATE
from .dynalitebase import DynaliteBaseDevice
from .switch import DynalitePresetSwitchDevice

if TYPE_CHECKING:  # pragma: no cover
    from .dynalite_devices import DynaliteDevices


class DynaliteAreaPresetSelectDevice(DynaliteBaseDevice):
    """All the presets of one Dynalite area, as a Home Assistant Select.

    Created for areas with the "select" template. The options are the names of the area's presets, in preset order. It
    follows the preset switches of the area: the current option is the
    preset that was last selected, or None if that isn't known.
    """

    def __init__(self, area: int, bridge: "DynaliteDevices", hidden: bool) -> None:
        """Initialize the select."""
        self._presets: Dict[int, DynalitePresetSwitchDevice] = {}
        self._current: Optional[int] = None
        super().__init__(area, bridge, hidden)

    @property
    def available(self) -> bool:
        """Return if device is available."""
        return self._bridge.available(CONF_TEMPLATE, self._area, CONF_SELECT)

    @property
    def name(self) -> str:
        """Return the name of the device."""
        return self._bridge.get_area_name(self._area)

    @property
    def category(self) -> str:
        """Return the category of the entity: light, switch, cover or select."""
        return "select"

    @property
    def unique_id(self) -> str:
        """Return the ID of this select."""
        return "dynalite_area_" + str(self._area) + "_preset_select"

    def has_preset(self, preset: int) -> bool:
        """Return whether a preset is one of the options."""
        return preset in self._presets

    def add_preset(self, preset: int, device: DynalitePresetSwitchDevice) -> None:
        """Add a preset to the options."""
        self._presets[preset] = device
        device.add_listener(self.listener)
        if device.is_on:
            self._current = preset

    @property
    def presets(self) -> Dict[int, str]:
        """Return the option for each preset number, in preset order.

        An option is the preset's name. When two presets in the area share a
        name, their numbers are added so that every option is unique.
        """
        names = {
            preset: self._bridge.get_preset_option(self._area, preset)
            for preset in sorted(self._presets)
        }
        counts: Dict[str, int] = {}
        for name in names.values():
            counts[name] = counts.get(name, 0) + 1
        return {
            preset: name if counts[name] == 1 else f"{name} ({preset})"
            for preset, name in names.items()
        }

    @property
    def options(self) -> List[str]:
        """Return the options, in preset order."""
        return list(self.presets.values())

    @property
    def current_preset(self) -> Optional[int]:
        """Return the number of the selected preset, if known."""
        return self._current

    @property
    def current_option(self) -> Optional[str]:
        """Return the selected option, if known."""
        if self._current is None:
            return None
        return self.presets[self._current]

    async def async_select_preset(self, preset: int) -> None:
        """Select a preset by number."""
        if preset not in self._presets:
            raise ValueError(f"Preset {preset} is not an option of area {self._area}")
        await self._presets[preset].async_turn_on()

    async def async_select_option(self, option: str) -> None:
        """Select a preset by its option."""
        for preset, name in self.presets.items():
            if name == option:
                await self.async_select_preset(preset)
                return
        raise ValueError(f"{option!r} is not an option of area {self._area}")

    def listener(self, device: DynaliteBaseDevice, stop_fade: bool) -> None:
        """Follow a change in one of the preset switches."""
        # pylint: disable=unused-argument
        assert isinstance(device, DynalitePresetSwitchDevice)
        preset = device.preset
        if device.is_on:  # listeners only hear about changes
            self._current = preset
        elif self._current == preset:
            self._current = None
        else:
            return
        self._bridge.update_device(self)

    def init_level(self, level):
        """Initialize to a preset number."""
        for preset, device in self._presets.items():
            device.init_level(preset == level)
        self._current = level if level in self._presets else None
