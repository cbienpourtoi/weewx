""" William's code to read data from the WS
"""

import re
import serial
import time

tty = '/dev/ttyUSB0'
baud = 19200 
ser = serial.Serial(tty, baud)


while True:
    s = ser.readline().replace('\r\n', '')
    if re.match('^\dR\d', s):
        d = dict()
        ss = s.split(',')
    d['station_id'], d['pkt_type'] = ss[0].split('R')
        d.update(dict((k, v) for k,v in [x.split('=') for x in ss[1:]]))
    print d
    time.sleep(0.1)

# WXT520 packet types:
# Acknowledge Active Command (a) - manual pg 71
# aR0 - Composite Data Message Query
# aR1 - Wind Data Message
# aR2 - Pressure, Temperature and Humidity
# aR3 - Precipitation Data Message
# aR5 - Supervisor Data Message

