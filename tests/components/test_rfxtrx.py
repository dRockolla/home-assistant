"""
tests.components.test_rfxtrx
~~~~~~~~~~~~~~~~~~~~~~~~~

Tests Rfxtrx component.
"""
# pylint: disable=too-many-public-methods,protected-access
import unittest
import time

from homeassistant.components import rfxtrx as rfxtrx
from homeassistant.components.sensor import rfxtrx as rfxtrx_sensor

import pytest

from tests.common import get_test_home_assistant


@pytest.mark.skipif(True, reason='Does not clean up properly, takes 100% CPU')
class TestRFXTRX(unittest.TestCase):
    """ Test the sun module. """

    def setUp(self):
        """ setup hass """
        self.hass = get_test_home_assistant(0)

    def tearDown(self):
        """ Stop down stuff we started. """
        rfxtrx.RECEIVED_EVT_SUBSCRIBERS = []
        rfxtrx.RFX_DEVICES = {}
        rfxtrx.RFXOBJECT = None
        self.hass.stop()

    def test_default_config(self):
        """ Test config """
        self.assertTrue(rfxtrx.setup(self.hass, {
            'rfxtrx': {
                'device': '/dev/serial/by-id/usb' +
                          '-RFXCOM_RFXtrx433_A1Y0NJGR-if00-port0',
                'dummy': True}
        }))

        config = {'devices': {}}
        devices = []

        def add_dev_callback(devs):
            """ callback to add device """
            for dev in devs:
                devices.append(dev)

        rfxtrx_sensor.setup_platform(self.hass, config, add_dev_callback)

        while len(rfxtrx.RFX_DEVICES) < 2:
            time.sleep(0.1)

        self.assertEquals(len(rfxtrx.RFXOBJECT.sensors()), 2)
        self.assertEquals(len(devices), 2)

    def test_config_failing(self):
        """ Test config """
        self.assertFalse(rfxtrx.setup(self.hass, {
            'rfxtrx': {}
        }))
