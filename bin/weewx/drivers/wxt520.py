#!/usr/bin/env python
#
# Copyright 2014 Matthew Wall
# See the file LICENSE.txt for your rights.

"""Driver for WXT520 weather stations (Vaisala).
http://www.vaisala.com/Vaisala%20Documents/User%20Guides%20and%20Quick%20Ref%20Guides/M210906EN-C.pdf

"""

from __future__ import with_statement
import serial
import syslog
import time
import re

import weewx.drivers

DRIVER_NAME = 'wxt520'
DRIVER_VERSION = '0.1'


def loader(config_dict, _):
    print "test in loader"
    print config_dict
    return WXT520Driver(**config_dict[DRIVER_NAME])


def confeditor_loader():
    return WXT520ConfEditor()


DEFAULT_PORT = '/dev/ttyUSB0'
DEBUG_READ = 0


def logmsg(level, msg):
    syslog.syslog(level, 'WXT520: %s' % msg)


def logdbg(msg):
    logmsg(syslog.LOG_DEBUG, msg)


def loginf(msg):
    logmsg(syslog.LOG_INFO, msg)


def logerr(msg):
    logmsg(syslog.LOG_ERR, msg)


def _format(buf):
    return ' '.join(["%0.2X" % ord(c) for c in buf])


class WXT520Driver(weewx.drivers.AbstractDevice):
    """weewx driver that communicates with a VXT520 station
    
    port - serial port
    [Required. Default is /dev/ttyS0]

    polling_interval - how often to query the serial interface, seconds
    [Optional. Default is 1]

    max_tries - how often to retry serial communication before giving up
    [Optional. Default is 5]

    retry_wait - how long to wait, in seconds, before retrying after a failure
    [Optional. Default is 10]
    """

    def __init__(self, **stn_dict):
        self.port = stn_dict.get('port', DEFAULT_PORT)
        self.polling_interval = float(stn_dict.get('polling_interval', 1))
        self.max_tries = int(stn_dict.get('max_tries', 5))
        self.retry_wait = int(stn_dict.get('retry_wait', 10))
        self.last_rain = None
        loginf('driver version is %s' % DRIVER_VERSION)
        loginf('using serial port %s' % self.port)
        loginf('polling interval is %s' % self.polling_interval)
        global DEBUG_READ
        DEBUG_READ = int(stn_dict.get('debug_read', DEBUG_READ))

    @property
    def hardware_name(self):
        return "WXT520"

    def genLoopPackets(self):
        ntries = 0
        while ntries < self.max_tries:
            ntries += 1
            try:
                packet = {'dateTime': int(time.time() + 0.5),
                          'usUnits': weewx.US}
                # open a new connection to the station for each reading
                with Station(self.port) as station:
                    readings = station.get_readings()
                data = Station.parse_readings(readings)
                packet.update(data)
                self._augment_packet(packet)
                ntries = 0
                yield packet
                if self.polling_interval:
                    time.sleep(self.polling_interval)
            except (serial.serialutil.SerialException, weewx.WeeWxIOError), e:
                logerr("Failed attempt %d of %d to get LOOP data: %s" %
                       (ntries, self.max_tries, e))
                time.sleep(self.retry_wait)
        else:
            msg = "Max retries (%d) exceeded for LOOP data" % self.max_tries
            logerr(msg)
            raise weewx.RetriesExceeded(msg)

    def _augment_packet(self, packet):
        # calculate the rain delta from rain total
        if self.last_rain is not None:
            packet['rain'] = packet['long_term_rain'] - self.last_rain
        else:
            packet['rain'] = None
        self.last_rain = packet['long_term_rain']

        # no wind direction when wind speed is zero
        if 'windSpeed' in packet and not packet['windSpeed']:
            packet['windDir'] = None


class Station(object):
    def __init__(self, port):
        self.port = port
        self.baudrate = 19200
        self.timeout = 3
        self.serial_port = None

    def __enter__(self):
        self.open()
        return self

    def __exit__(self, _, value, traceback):
        self.close()

    def open(self):
        logdbg("open serial port %s" % self.port)
        self.serial_port = serial.Serial(self.port, self.baudrate,
                                         timeout=self.timeout)

    def close(self):
        if self.serial_port is not None:
            logdbg("close serial port %s" % self.port)
            self.serial_port.close()
            self.serial_port = None

    def get_readings(self):
        s = self.serial_port.readline().replace('\r\n', '')
        if re.match('^\dR\d', s):
            d = dict()
            ss = s.split(',')
        print "d:"
        print d
        print "ss: this is the line divided in words"
        print ss
        d['station_id'], d['pkt_type'] = ss[0].split('R')
        d.update(dict((k, v) for k, v in [x.split('=') for x in ss[1:]]))
        return d

    @staticmethod
    def parse_readings(b):
        """ WXT520 packet types:
		Acknowledge Active Command (a) - manual pg 71
		aR0 - Composite Data Message Query
		aR1 - Wind Data Message
		aR2 - Pressure, Temperature and Humidity
		aR3 - Precipitation Data Message
		aR5 - Supervisor Data Message
        """
        print "b :"
        print b
        data = dict()
        print "data :"
        print data
        data['windSpeed'] = int(b[0:4], 16) * 0.1 * MILE_PER_KM  # mph
        data['windDir'] = int(b[6:8], 16) * 1.411764  # compass degrees
        data['outTemp'] = int(b[8:12], 16) * 0.1  # degree_F
        data['long_term_rain'] = int(b[12:16], 16) * 0.01  # inch
        data['pressure'] = int(b[16:20], 16) * 0.1 * INHG_PER_MBAR  # inHg
        data['inTemp'] = int(b[20:24], 16) * 0.1  # degree_F
        data['outHumidity'] = int(b[24:28], 16) * 0.1  # percent
        data['inHumidity'] = int(b[28:32], 16) * 0.1  # percent
        data['day_of_year'] = int(b[32:36], 16)
        data['minute_of_day'] = int(b[36:40], 16)
        data['daily_rain'] = int(b[40:44], 16) * 0.01  # inch
        data['wind_average'] = int(b[44:48], 16) * 0.1 * MILE_PER_KM  # mph
        return data


class WXT520ConfEditor(weewx.drivers.AbstractConfEditor):
    @property
    def default_stanza(self):
        return """
[WXT520]
    # This section is for the ADS WXT520 series of weather stations.

    # Serial port such as /dev/ttyS0, /dev/ttyUSB0, or /dev/cuaU0
    port = /dev/ttyUSB0

    # The driver to use:
    driver = weewx.drivers.wxt520
"""

    def prompt_for_settings(self):
        print "Specify the serial port on which the station is connected, for"
        print "example /dev/ttyUSB0 or /dev/ttyS0."
        port = self._prompt('port', '/dev/ttyUSB0')
        return {'port': port}

# define a main entry point for basic testing of the station without weewx
# engine and service overhead.  invoke this as follows from the weewx root dir:
#
# PYTHONPATH=bin python bin/weewx/drivers/wxt520.py

if __name__ == '__main__':
    import optparse

    usage = """%prog [options] [--help]"""

    syslog.openlog('WXT520', syslog.LOG_PID | syslog.LOG_CONS)
    syslog.setlogmask(syslog.LOG_UPTO(syslog.LOG_DEBUG))
    parser = optparse.OptionParser(usage=usage)
    parser.add_option('--version', dest='version', action='store_true',
                      help='display driver version')
    parser.add_option('--port', dest='port', metavar='PORT',
                      help='serial port to which the station is connected',
                      default=DEFAULT_PORT)
    (options, args) = parser.parse_args()

    if options.version:
        print "WXT520 driver version %s" % DRIVER_VERSION
        exit(0)

    with Station(options.port) as s:
        while True:
            print time.time(), s.get_readings()
