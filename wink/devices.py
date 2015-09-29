from .interfaces import *

import time


class CreatableResourceBase(object):
    """Base class for 'creatable' objects, e.g.:
        - triggers
        - alarms
        - scheduled_outlet_states

    """

    # TODO add automatic getters/setters for these fields
    mutable_fields = []

    def __init__(self, parent, data):
        self.parent = parent
        self.data = data

        self.id = data["%s_id" % self.resource_type()]

    def _path(self):
        return "/%ss/%s" % (self.resource_type(), self.id)

    def resource_type(self):
        return self.__class__.__name__

    def get(self):
        return self.parent.wink._get(self._path())

    def update(self, data):
        return self.parent.wink._put(self._path(), data)

    def delete(self):
        return self.parent.wink._delete(self._path())


class CreatableSubResourceBase(CreatableResourceBase):

    def _path(self):
        return "%s%s" % (
            self.parent._path(),
            CreatableResourceBase._path(self)
        )


class DeviceBase(object):
    """Implements functionality shared by all devices:
        - get
        - update

    """

    # list of fields from the device 'get'
    # that should be removed so we only capture
    # the 'state' and 'configuration' of the device
    non_config_fields = []

    # TODO add automatic getters/setters for these fields
    mutable_fields = []

    subdevice_types = []

    def __init__(self, wink, data):
        self.wink = wink
        self.data = data

        self.id = data["%s_id" % self.device_type()]

        self._subdevices = []

        for subdevice_type in self.subdevice_types:
            subdevice_plural = "%ss" % subdevice_type.__name__
            setattr(self, "_%s" % subdevice_plural, [])
            setattr(self,
                    subdevice_plural,
                    self._subdevices_by_type_closure(subdevice_plural))
            subdevice_list = getattr(self, "_%s" % subdevice_plural)

            for subdevice_info in self.data[subdevice_plural]:
                this_obj = subdevice_type(
                    self.wink,
                    subdevice_info)
                self._subdevices.append(this_obj)
                subdevice_list.append(this_obj)

    def _subdevices_by_type_closure(self, subdevice_type):
        return lambda: self.subdevices_by_type(subdevice_type)

    def subdevices_by_type(self, typ):
        return list(getattr(self, "_%s" % typ, []))

    def subdevices(self):
        return list(self._subdevices)

    def _path(self):
        return "/%ss/%s" % (self.device_type(), self.id)

    def device_type(self):
        return self.__class__.__name__

    def get(self):
        return self.wink._get(self._path())

    def update(self, data):
        return self.wink._put(self._path(), data)

    def get_config(self, status=None):
        if not status:
            status = self.get()

        for field in self.non_config_fields:
            if field in status:
                del status[field]

        return status

    def revert(self):
        """
        If you break anything, run this to revert the device
        configuration to the original value from when the object
        was instantiated.
        """

        old_config = self.get_config(self.data)
        self.update(old_config)

        for subdevice in self.subdevices():
            subdevice.revert()

    class trigger(CreatableResourceBase):

        mutable_fields = [
            ("name", str),
            ("enabled", bool),
            ("trigger_configuration", dict),
            ("channel_configuration", dict),
        ]

    def _trigger_path(self):
        return "%s/triggers" % self._path()

    def triggers(self):
        return [
            DeviceBase.trigger(self, x)
            for x
            in self.get().get("triggers", [])
        ]

    def create_trigger(self, data):
        res = self.wink._post(self._trigger_path(), data)

        return DeviceBase.trigger(self, res)


class powerstrip(DeviceBase, Sharable):

    non_config_fields = [
        "powerstrip_id",

        # TODO revisit this decision -- can/should we
        # count them as revertible state?
        "powerstrip_triggers",
        "outlets",
        "last_reading",
        "mac_address",
        "serial",
        "subscription",
        "triggers",
        "user_ids",
    ]

    class outlet(DeviceBase):

        non_config_fields = [
            "outlet_id",
            "outlet_index",
        ]

        mutable_fields = [
            ("name", str),
            ("icon_id", str),
            ("powered", bool),
        ]

        class scheduled_outlet_state(CreatableSubResourceBase):

            mutable_fields = [
                ("name", str),
                ("powered", bool),
                ("enabled", bool),
                ("recurrence", str),
            ]

        def _schedule_path(self):
            return "%s/scheduled_outlet_states" % self._path()

        def create_schedule(self, data):
            res = self.wink._post(self._schedule_path(), data)

            return powerstrip.outlet.scheduled_outlet_state(self, res)

    subdevice_types = [
        outlet
    ]


class eggtray(DeviceBase, Sharable):
    pass


class cloud_clock(DeviceBase, Sharable):

    non_config_fields = [
        "cloud_clock_id",

        # TODO revisit this decision -- can/should we
        # count them as revertible state?
        "cloud_clock_triggers",
        "dials",  # will be done explicitly, later
        "last_reading",
        "mac_address",
        "serial",
        "subscription",
        "triggers",
        "user_ids",
    ]

    mutable_fields = [
        ("name", str),
    ]

    # while dial clearly belongs to a cloud_clock, the API puts
    # the dial interface at the root level, so I am representing
    # it as a DeviceBase
    class dial(DeviceBase):

        non_config_fields = [
            "dial_id",
            "dial_index",
            "labels",
            "position",
        ]

        mutable_fields = [
            ("name", str),
            ("label", str),
            ("channel_configuration", dict),
            ("dial_configuration", dict),
            ("brightness", int),
        ]

        def templates(self):
            return self.wink._get("/dial_templates")

        def demo(self, delay=5):
            """
            Generates a sequence of updates to run the dial through
            the range of values and positions.
            """

            original = self.get_config()

            # do some stuff
            values = [
                ("min", original["dial_configuration"]["min_value"]),
                ("max", original["dial_configuration"]["max_value"]),
            ]

            # set the dial to manual control
            self.update(dict(
                channel_configuration=dict(channel_id="10"),
                dial_configuration=original["dial_configuration"],
                label="demo!",
            ))
            time.sleep(delay)

            for text, value in values:
                self.update(dict(value=value, label="%s: %s" % (text, value)))
                time.sleep(delay)

            # revert to the original configuration
            self.update(original)

        def flash_value(self, duration=5):
            """
            Temporarily replace the existing label with the current value
            for the specified duration.
            """

            original = self.get_config()

            # set the dial to manual control
            self.update(dict(
                channel_configuration=dict(channel_id="10"),
                dial_configuration=original["dial_configuration"],
                label="%s" % original["value"],
            ))
            time.sleep(duration)

            self.update(dict(
                channel_configuration=original["channel_configuration"],
                dial_configuration=original["dial_configuration"],
                label=original["label"],
                labels=original["labels"],
            ))

    subdevice_types = [
        dial,
    ]

    def rotate(self, direction="left"):
        statuses = [d.get_config() for d in self.dials()]

        if direction == "left":
            statuses.append(statuses.pop(0))
        else:
            statuses.insert(0, statuses.pop(-1))

        for d, new_status in zip(self.dials(), statuses):
            d.update(new_status)

    class alarm(CreatableResourceBase):

        mutable_fields = [
            ("name", str),
            ("recurrence", str),
            ("enabled", bool),
        ]

    def _alarm_path(self):
        return "%s/alarms" % self._path()

    def alarms(self):
        return [
            cloud_clock.alarm(self, x)
            for x
            in self.get().get("alarms", [])
        ]

    def create_alarm(self, name, recurrence, enabled=True):
        data = dict(
            name=name,
            recurrence=recurrence,
            enabled=enabled)

        res = self.wink._post(self._alarm_path(), data)

        return cloud_clock.alarm(self, res)


class piggy_bank(DeviceBase, Sharable):
    pass
    # TODO: deposits


class sensor_pod(DeviceBase, Sharable):
    pass


# Wink Hub
class hub(DeviceBase, Sharable):
    non_config_fields = [
        "created_at",
        "device_manufacturer",
        "hidden_at",
        "lat_lng",
        "linked_service_id",
        "locale",
        "location",
        "manufacturer_device_id",
        "manufacturer_device_model",
        "model_name",
        "triggers",
        "unit",
        "upc_code",
        "upc_id",
    ]

    mutable_fields = [
        ("name", str),
        ("desired_state", dict)
    ]

    def _get_last_reading(self):
        """Get the last reading of the device"""
        state = self.get_config()

        if 'last_reading' in state:
            return state['last_reading']

    def _set_state(self, _pairing_mode=None, _kidde_radio_code=None):
        """Change the devices state"""
        new_state = {}
        if _pairing_mode is not None:
            new_state['pairing_mode'] = _pairing_mode

        if _kidde_radio_code is not None:
            new_state['kidde_radio_code'] = _kidde_radio_code

        self.update(dict(desired_state=new_state))

    def is_update_needed(self):
        """Does the hub require an update"""
        last = self._get_last_reading()

        if 'update_needed' in last:
            return last['update_needed']

        # if unknown, assume false
        return False

    def get_mac_address(self):
        """Return the MAC address of the hub"""
        last = self._get_last_reading()

        if 'mac_address' in last:
            return last['mac_address']

        return 'Unknown'

    def get_ip_address(self):
        """Return the ip address of the hub"""
        last = self._get_last_reading()

        if 'ip_address' in last:
            return last['ip_address']

        return 'Unknown'

    def get_firmware_version(self):
        """Return the firmware version of the hub"""
        last = self._get_last_reading()

        if 'firmware_version' in last:
            return last['firmware_version']

        return 'Unknown'

    def get_pairing_mode(self):
        """Return the pairing mode of the hub"""
        last = self._get_last_reading()

        if 'pairing_mode' in last:
            return last['pairing_mode']

        return 'Unknown'

    def set_pairing_mode(self, pairing_mode=None):
        """Set the pairing mode of the hub"""
        self._set_state(_pairing_mode=pairing_mode)

    def get_kidde_radio_code(self):
        """Return the kidde radio code of the hub"""
        last = self._get_last_reading()

        if 'kidde_radio_code' in last:
            return last['kidde_radio_code']

        return -1

    def set_kidde_radio_code(self, kidde_radio_code=None):
        """Return the kidde radio code of the hub"""
        self._set_state(_kidde_radio_code=kidde_radio_code)


# DropCam / NestCam
class camera(DeviceBase, Sharable):
    non_config_fields = [

    ]

    mutable_fields = [
        ("name", str),
        ("desired_state", str)
    ]
    pass


# MyQ Chamberlin devices
class garage_door(DeviceBase, Sharable):
    non_config_fields = [
        "radio_type",
        "upc_code",
        "upc_id",
        "model_name",
        "lat_lng",
        "order",
        "triggers",
        "manufacturer_device_model",
        "manufacturer_device_id",
        "location",
        "locale",
        "device_manufacturer",
        "created_at",
        "unit",
        "hidden_at",
        "capabilities",
    ]

    mutable_fields = [
        ("name", str),
        ("desired_state", str)
    ]

    def _get_last_reading(self):
        """Get the last reading of the device"""
        state = self.get_config()

        if 'last_reading' in state:
            return state['last_reading']

    def current_position(self):
        """Read the current position of the door"""
        last = self._get_last_reading()

        if 'position' in last:
            if last['position'] == 0.0:
                return 'Closed'
            elif last['position'] == 1.0:
                return 'Open'
            elif last['position'] > 0.0 and last['position'] < 1.0:
                return 'Moving'

        return 'Unknown'

    def is_fault(self):
        """Query the device to see if there was a fault"""
        last = self._get_last_reading()

        if 'fault' in last:
            return last['fault']

        return 'Unknown'

    def _set_state(self, position=None):
        """Change the devices state"""
        new_state = {
                        'position': position
                    }

        self.update(dict(desired_state=new_state))

    def open(self):
        """Open the garage door"""
        self._set_state(position=1.0)

    def close(self):
        """Close the garage door"""
        self._set_state(position=0.0)


# GE Link lightbulb
class light_bulb(DeviceBase, Sharable):
    non_config_fields = [
        "radio_type",
        "upc_code",
        "upc_id",
        "model_name",
        "lat_lng",
        "order",
        "triggers",
        "manufacturer_device_id",
        "manufacturer_device_model",
        "location",
        "locale",
        "device_manufacturer",
        "created_at",
        "unit",
        "hidden_at",
        "capabilities",
        "gang_id",
    ]

    mutable_fields = [
        ("name", str),
        ("desired_state", dict)
    ]

    def _get_last_reading(self):
        """Get the last reading of the device"""
        state = self.get_config()

        if 'last_reading' in state:
            return state['last_reading']

    def _set_state(self, brightness=None, powered=None):
        """Change the devices state"""
        new_state = {}
        if brightness is not None:
            new_state['brightness'] = brightness

        if powered is not None:
            new_state['powered'] = powered

        self.update(dict(desired_state=new_state))

    def set_brightness(self, brightness=1.0):
        """Set the brightness of the bulb, regardless of powered state"""
        self._set_state(brightness)

    def is_on(self):
        """Check if the bulb is powered on or not"""
        last = self._get_last_reading()

        if 'powered' in last:
            return last['powered']

        return 'Unknown'

    def get_brightness(self):
        """Get the current brightness setting for the bulb"""
        last = self._get_last_reading()

        # Artificially give a brightness of 0.0 if device
        # is powered off, since it retains last brightness
        # even if there is no power
        if 'powered' in last and last['powered'] == False:
            return 0.0

        if 'brightness' in last:
            return last['brightness']

        return -1

    def turn_on(self):
        """Turn the bulb on"""
        self._set_state(powered=True)

    def turn_off(self):
        """Turn the bulb off"""
        self._set_state(powered=False)

    def toggle(self):
        """Toggle the current bulb power state"""
        state = self.is_on()

        # An unknown state will try to turn off
        if state:
            self.turn_off()
        else:
            self.turn_on()
