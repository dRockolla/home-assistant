"""
homeassistant.components.device_tracker.owntracks
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
OwnTracks platform for the device tracker.

For more details about this platform, please refer to the documentation at
https://home-assistant.io/components/device_tracker.owntracks/
"""
import json
import logging
import threading
from collections import defaultdict

import homeassistant.components.mqtt as mqtt
from homeassistant.const import STATE_HOME

DEPENDENCIES = ['mqtt']

REGIONS_ENTERED = defaultdict(list)
MOBILE_BEACONS_ACTIVE = defaultdict(list)

BEACON_DEV_ID = 'beacon'

LOCATION_TOPIC = 'owntracks/+/+'
EVENT_TOPIC = 'owntracks/+/+/event'

_LOGGER = logging.getLogger(__name__)

LOCK = threading.Lock()

CONF_MAX_GPS_ACCURACY = 'max_gps_accuracy'


def setup_scanner(hass, config, see):
    """ Set up an OwnTracks tracker. """

    max_gps_accuracy = config.get(CONF_MAX_GPS_ACCURACY)

    def owntracks_location_update(topic, payload, qos):
        """ MQTT message received. """

        # Docs on available data:
        # http://owntracks.org/booklet/tech/json/#_typelocation
        try:
            data = json.loads(payload)
        except ValueError:
            # If invalid JSON
            _LOGGER.error(
                'Unable to parse payload as JSON: %s', payload)
            return

        if (not isinstance(data, dict) or data.get('_type') != 'location') or (
                'acc' in data and max_gps_accuracy is not None and data[
                    'acc'] > max_gps_accuracy):
            return

        dev_id, kwargs = _parse_see_args(topic, data)

        # Block updates if we're in a region
        with LOCK:
            if REGIONS_ENTERED[dev_id]:
                _LOGGER.debug(
                    "location update ignored - inside region %s",
                    REGIONS_ENTERED[-1])
                return

            see(**kwargs)
            see_beacons(dev_id, kwargs)

    def owntracks_event_update(topic, payload, qos):
        # pylint: disable=too-many-branches, too-many-statements
        """ MQTT event (geofences) received. """

        # Docs on available data:
        # http://owntracks.org/booklet/tech/json/#_typetransition
        try:
            data = json.loads(payload)
        except ValueError:
            # If invalid JSON
            _LOGGER.error(
                'Unable to parse payload as JSON: %s', payload)
            return

        if not isinstance(data, dict) or data.get('_type') != 'transition':
            return

        # OwnTracks uses - at the start of a beacon zone
        # to switch on 'hold mode' - ignore this
        location = data['desc'].lstrip("-")
        if location.lower() == 'home':
            location = STATE_HOME

        dev_id, kwargs = _parse_see_args(topic, data)

        if data['event'] == 'enter':
            zone = hass.states.get("zone.{}".format(location))
            with LOCK:
                if zone is None:
                    if data['t'] == 'b':
                        # Not a HA zone, and a beacon so assume mobile
                        beacons = MOBILE_BEACONS_ACTIVE[dev_id]
                        if location not in beacons:
                            beacons.append(location)
                        _LOGGER.info("Added beacon %s", location)
                else:
                    # Normal region
                    if not zone.attributes.get('passive'):
                        kwargs['location_name'] = location

                    regions = REGIONS_ENTERED[dev_id]
                    if location not in regions:
                        regions.append(location)
                    _LOGGER.info("Enter region %s", location)
                    _set_gps_from_zone(kwargs, zone)

                see(**kwargs)
                see_beacons(dev_id, kwargs)

        elif data['event'] == 'leave':
            with LOCK:
                regions = REGIONS_ENTERED[dev_id]
                if location in regions:
                    regions.remove(location)
                new_region = regions[-1] if regions else None

                if new_region:
                    # Exit to previous region
                    zone = hass.states.get("zone.{}".format(new_region))
                    if not zone.attributes.get('passive'):
                        kwargs['location_name'] = new_region
                    _set_gps_from_zone(kwargs, zone)
                    _LOGGER.info("Exit to %s", new_region)
                    see(**kwargs)
                    see_beacons(dev_id, kwargs)

                else:
                    _LOGGER.info("Exit to GPS")
                    # Check for GPS accuracy
                    if not ('acc' in data and
                            max_gps_accuracy is not None and
                            data['acc'] > max_gps_accuracy):

                        see(**kwargs)
                        see_beacons(dev_id, kwargs)
                    else:
                        _LOGGER.info("Inaccurate GPS reported")

                beacons = MOBILE_BEACONS_ACTIVE[dev_id]
                if location in beacons:
                    beacons.remove(location)
                    _LOGGER.info("Remove beacon %s", location)

        else:
            _LOGGER.error(
                'Misformatted mqtt msgs, _type=transition, event=%s',
                data['event'])
            return

    def see_beacons(dev_id, kwargs_param):
        """ Set active beacons to the current location """

        kwargs = kwargs_param.copy()
        # the battery state applies to the tracking device, not the beacon
        kwargs.pop('battery', None)
        for beacon in MOBILE_BEACONS_ACTIVE[dev_id]:
            kwargs['dev_id'] = "{}_{}".format(BEACON_DEV_ID, beacon)
            kwargs['host_name'] = beacon
            see(**kwargs)

    mqtt.subscribe(hass, LOCATION_TOPIC, owntracks_location_update, 1)

    mqtt.subscribe(hass, EVENT_TOPIC, owntracks_event_update, 1)

    return True


def _parse_see_args(topic, data):
    """ Parse the OwnTracks location parameters,
        into the format see expects. """

    parts = topic.split('/')
    dev_id = '{}_{}'.format(parts[1], parts[2])
    host_name = parts[1]
    kwargs = {
        'dev_id': dev_id,
        'host_name': host_name,
        'gps': (data['lat'], data['lon'])
    }
    if 'acc' in data:
        kwargs['gps_accuracy'] = data['acc']
    if 'batt' in data:
        kwargs['battery'] = data['batt']
    return dev_id, kwargs


def _set_gps_from_zone(kwargs, zone):
    """ Set the see parameters from the zone parameters """

    if zone is not None:
        kwargs['gps'] = (
            zone.attributes['latitude'],
            zone.attributes['longitude'])
        kwargs['gps_accuracy'] = zone.attributes['radius']
    return kwargs
