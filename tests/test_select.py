"""Tests for the Dynalite area preset select."""

import pytest

import dynalite_devices_lib.const as dyn_const
from dynalite_devices_lib.dynet import DynetPacket
from dynalite_devices_lib.select import DynaliteAreaPresetSelectDevice
from dynalite_devices_lib.switch import DynalitePresetSwitchDevice

from .common import packet_notification, preset_notification


def area_config(template=dyn_const.CONF_SELECT, **extra):
    """Return a config with one area of three presets."""
    area = {
        dyn_const.CONF_NAME: "Office",
        dyn_const.CONF_NO_DEFAULT: True,
        dyn_const.CONF_PRESET: {
            "1": {dyn_const.CONF_NAME: "High", dyn_const.CONF_FADE: 0.5},
            "4": {dyn_const.CONF_NAME: "Off"},
            "2": {},
        },
    }
    if template:
        area[dyn_const.CONF_TEMPLATE] = template
    return {dyn_const.CONF_ACTIVE: False, dyn_const.CONF_AREA: {"1": area}, **extra}


def get_select(devices) -> DynaliteAreaPresetSelectDevice:
    """Return the only select in a list of devices."""
    [select] = [d for d in devices if isinstance(d, DynaliteAreaPresetSelectDevice)]
    return select


def preset_switch(bridge, area, preset) -> DynalitePresetSwitchDevice:
    """Return the (possibly hidden) switch of a preset."""
    # pylint: disable=protected-access
    return bridge._added_presets[area][preset]


@pytest.mark.asyncio
async def test_no_select_without_template(mock_gateway):
    """Without the select template, an area's presets are switches."""
    devices = mock_gateway.configure_dyn_dev(area_config(template=None), 3)
    assert all(isinstance(d, DynalitePresetSwitchDevice) for d in devices)


@pytest.mark.asyncio
async def test_preset_select(mock_gateway):
    """Test selecting presets from the select, and following the bus."""
    [select] = mock_gateway.configure_dyn_dev(area_config(), 1)
    assert not select.available
    assert await mock_gateway.async_setup_dyn_dev()
    await mock_gateway.check_single_update(None)
    assert select.category == "select"
    assert select.name == "Office"
    assert select.unique_id == "dynalite_area_1_preset_select"
    assert select.available
    assert select.presets == {1: "High", 2: "Preset 2", 4: "Off"}
    assert select.options == ["High", "Preset 2", "Off"]
    assert select.current_option is None
    assert select.current_preset is None
    # select from the select: sends the preset with its own fade
    await select.async_select_option("High")
    await mock_gateway.check_single_write(
        DynetPacket.select_area_preset_packet(1, 1, 0.5)
    )
    await mock_gateway.check_single_update(select)
    await mock_gateway.check_notifications([preset_notification(1, 1)])
    assert select.current_option == "High"
    assert select.current_preset == 1
    await select.async_select_preset(4)
    await mock_gateway.check_single_write(
        DynetPacket.select_area_preset_packet(1, 4, 0)
    )
    await mock_gateway.check_single_update(select)
    await mock_gateway.check_notifications([preset_notification(1, 4)])
    assert select.current_option == "Off"
    # a preset from the bus, e.g. a keypad
    packet = DynetPacket.report_area_preset_packet(1, 2)
    await mock_gateway.receive(packet)
    await mock_gateway.check_single_update(select)
    await mock_gateway.check_notifications(
        [packet_notification(packet.raw_msg), preset_notification(1, 2)]
    )
    assert select.current_option == "Preset 2"
    # the same preset again does not update the select
    await mock_gateway.receive(packet)
    await mock_gateway.check_updates([])
    await mock_gateway.check_notifications(
        [packet_notification(packet.raw_msg), preset_notification(1, 2)]
    )
    # turning the (hidden) preset switch off clears the select
    await preset_switch(mock_gateway.dyn_dev, 1, 2).async_turn_off()
    await mock_gateway.check_single_update(select)
    assert select.current_option is None
    # unknown options and presets are refused without sending anything
    with pytest.raises(ValueError):
        await select.async_select_option("Nope")
    with pytest.raises(ValueError):
        await select.async_select_preset(3)
    await mock_gateway.check_writes([])


@pytest.mark.asyncio
async def test_preset_select_new_preset(mock_gateway):
    """A preset first seen on the bus becomes an option, not a switch."""
    [select] = mock_gateway.configure_dyn_dev(area_config(), 1)
    assert await mock_gateway.async_setup_dyn_dev()
    await mock_gateway.check_single_update(None)
    mock_gateway.new_dev_func.reset_mock()
    packet = DynetPacket.report_area_preset_packet(1, 6)
    await mock_gateway.receive(packet)
    assert select.options == ["High", "Preset 2", "Off", "Preset 6"]
    assert select.current_option == "Preset 6"
    mock_gateway.new_dev_func.assert_not_called()
    # once for the new option, once for the new current option
    await mock_gateway.check_updates([select, select])
    await mock_gateway.check_notifications(
        [packet_notification(packet.raw_msg), preset_notification(1, 6)]
    )


@pytest.mark.asyncio
async def test_preset_select_no_presets_yet(mock_gateway):
    """A select area with no presets gets its select with the first one."""
    mock_gateway.configure_dyn_dev(
        {
            dyn_const.CONF_ACTIVE: False,
            dyn_const.CONF_AREA: {
                "7": {
                    dyn_const.CONF_TEMPLATE: dyn_const.CONF_SELECT,
                    dyn_const.CONF_NO_DEFAULT: True,
                }
            },
        },
        0,
    )
    assert await mock_gateway.async_setup_dyn_dev()
    await mock_gateway.check_single_update(None)
    packet = DynetPacket.report_area_preset_packet(7, 3)
    await mock_gateway.receive(packet)
    mock_gateway.new_dev_func.assert_called_once()
    [select] = mock_gateway.new_dev_func.mock_calls[0][1][0]
    assert select.name == "Area 7"
    assert select.options == ["Preset 3"]
    assert select.current_preset == 3
    await mock_gateway.check_single_update(select)
    await mock_gateway.check_notifications(
        [packet_notification(packet.raw_msg), preset_notification(7, 3)]
    )


@pytest.mark.asyncio
async def test_preset_select_default_presets(mock_gateway):
    """Without nodefault, the global presets are options too."""
    devices = mock_gateway.configure_dyn_dev(
        {
            dyn_const.CONF_ACTIVE: False,
            dyn_const.CONF_AREA: {
                "1": {
                    dyn_const.CONF_NAME: "Gate",
                    dyn_const.CONF_TEMPLATE: dyn_const.CONF_SELECT,
                    dyn_const.CONF_PRESET: {"2": {dyn_const.CONF_NAME: "Pulse"}},
                },
                "2": {dyn_const.CONF_NAME: "Hall"},
            },
        },
        3,
    )
    select = get_select(devices)
    assert select.presets == {1: "On", 2: "Pulse", 4: "Off"}
    # the other area still gets the global presets as visible switches
    hall = [d for d in devices if d is not select]
    assert sorted(d.unique_id for d in hall) == [
        "dynalite_area_2_preset_1",
        "dynalite_area_2_preset_4",
    ]


@pytest.mark.asyncio
async def test_preset_select_duplicate_names(mock_gateway):
    """Presets with the same name get their numbers added."""
    [select] = mock_gateway.configure_dyn_dev(
        {
            dyn_const.CONF_ACTIVE: False,
            dyn_const.CONF_AREA: {
                "1": {
                    dyn_const.CONF_TEMPLATE: dyn_const.CONF_SELECT,
                    dyn_const.CONF_NO_DEFAULT: True,
                    dyn_const.CONF_PRESET: {
                        "1": {dyn_const.CONF_NAME: "Scene"},
                        "2": {dyn_const.CONF_NAME: "Scene"},
                        "3": {dyn_const.CONF_NAME: "Other"},
                    },
                }
            },
        },
        1,
    )
    assert select.options == ["Scene (1)", "Scene (2)", "Other"]
    assert await mock_gateway.async_setup_dyn_dev()
    await mock_gateway.check_single_update(None)
    await select.async_select_option("Scene (2)")
    await mock_gateway.check_single_write(
        DynetPacket.select_area_preset_packet(1, 2, 0)
    )
    await mock_gateway.check_single_update(select)
    await mock_gateway.check_notifications([preset_notification(1, 2)])


@pytest.mark.asyncio
async def test_preset_select_reconfigure(mock_gateway):
    """Changing an area to the select template in a reconfigure adds it."""
    switches = mock_gateway.configure_dyn_dev(area_config(template=None), 3)
    next(d for d in switches if d.preset == 4).init_level(1)
    [select] = mock_gateway.configure_dyn_dev(area_config(), 1)
    assert select.options == ["High", "Preset 2", "Off"]
    assert select.current_option == "Off"
    # a second reconfigure doesn't add it again
    mock_gateway.configure_dyn_dev(area_config(), 0)


def test_preset_select_init_level(mock_gateway):
    """init_level sets the current preset without sending anything."""
    [select] = mock_gateway.configure_dyn_dev(area_config(), 1)
    select.init_level(4)
    assert select.current_option == "Off"
    assert preset_switch(mock_gateway.dyn_dev, 1, 4).is_on
    select.init_level(9)
    assert select.current_option is None
