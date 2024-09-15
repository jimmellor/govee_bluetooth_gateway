#!/usr/bin/python
'''
This is a python Bluetooth advertisement scanner for the Govee brand Bluetooth
temperature sensor.  Tested on model H5075 using Raspberry Pi 3.
Temperature, humidity, and battery level is published as MQTT messages.

Credit:  I used information for Govee advertisement format from
github.com/Thrilleratplay/GoveeWatcher

Install dependencies:
 sudo apt-get install python3-pip libglib2.0-dev
 sudo pip3 install bluepy
 sudo apt install -y mosquitto mosquitto-clients
 sudo pip3 install paho-mqtt

Needs sudo to run on Raspbian
sudo python3 govee_ble_mqtt_pi.py

Run in background
sudo nohup python3 govee_ble_mqtt_pi.py &

'''

from __future__ import print_function

import configparser

from time import gmtime, strftime, sleep
from bluepy.btle import Scanner, DefaultDelegate, BTLEException
import sys

# influx db imports

from influxdb import InfluxDBClient

#from influxdb_client import InfluxDBClient, Point
#from influxdb_client.client.write_api import SYNCHRONOUS

# configuration
# NOTE on a raspberry pi the config file should be in /boot so that it is easily accessible from PC or Mac with a card reader
conf = configparser.ConfigParser()

conf.read('/boot/govee_ble_mqtt_pi.conf')

# influx db configuration
dbname = conf['influxdb']['name']
dbuser = conf['influxdb']['user']
dbpass = conf['influxdb']['pass']
dbhost = conf['influxdb']['host']
dbport = conf['influxdb']['port']
influxdbclient = InfluxDBClient(dbhost, dbport, dbuser, dbpass, dbname)

# site configuration
site_name = conf['site']['name']
site_location = conf['site']['location']

# hygrometer names
hygrometer_names = conf['hygrometers']

def on_connect(client, userdata, flags, rc):
    print("Connected with result code "+str(rc))

def on_message(client, userdata, msg):
    print("on message")

class ScanDelegate(DefaultDelegate):
    
    global client
    
    def handleDiscovery(self, dev, isNewDev, isNewData):
        #if (dev.addr == "a4:c1:38:xx:xx:xx") or (dev.addr == "a4:c1:38:xx:xx:xx"):
        if dev.addr[:8]=="a4:c1:38":
            #returns a list, of which the [2] item of the [3] tupple is manufacturing data
            adv_list = dev.getScanData()
            adv_manuf_data = adv_list[3][2]

            #resolve the name of the hygrometer
            try:
                #device_id is the last 4 characters of the Complete Local Name which is in [0][2] of the scan data. It's used to resolve the name in the config file
                device_id = adv_list[0][2].split("_")[1]
                device_name = hygrometer_names[device_id]
            except KeyError:
                device_name = device_id
            
            #this is the location of the encoded temp/humidity and battery data
            temp_hum_data = adv_manuf_data[6:12]
            battery = adv_manuf_data[12:14]

            print("temp hum data = ", temp_hum_data)
            print("battery data = ", battery)
            #convert to integer
            val = (int(temp_hum_data, 16))

            #decode tip from eharris: https://github.com/Thrilleratplay/GoveeWatcher/issues/2
            is_negative = False
            temp_C = 500
            humidity = 500
            if (val & 0x800000):
                is_negative = True
                val = val ^ 0x800000
            try:
                humidity = (val % 1000) / 10
                temp_C = int(val / 1000) / 10
                if (is_negative):
                    temp_C = 0 - temp_C
            except:
                print("issues with integer conversion")

            try:
                battery_percent = int(adv_manuf_data[12:14]) / 64 * 100
            except:
                battery_percent = 200
            battery_percent = round(battery_percent)

            temp_F = round(temp_C*9/5+32, 1)

            try:
                hum_percent = ((int(temp_hum_data, 16)) % 1000) / 10
            except:
                hum_percent = 200
            hum_percent = round(hum_percent)
            mac=dev.addr
            signal = dev.rssi

            # createa a json object for influxdb client with the temperature, humidity, battery, rssi, timestamp in the format "2009-11-10T23:00:00Z"
            time = strftime("%Y-%m-%dT%H:%M:%SZ", gmtime())
            json_body = [
                {
                    "measurement": "TempHumidity",
                    "time": time,
                    "tags": {
                        "MAC": mac,
                        "site": site_name,
                        "location": site_location,
                        "device_name": device_name
                    },
                    "fields": {
                        "temp_C": temp_C,
                        "humidity_percent": hum_percent,
                        "battery_percent": battery_percent,
                        "ressi": signal
                    }
                }
            ]


            # write the json object to the influxdb
            influxdbclient.write_points(json_body)

scanner = Scanner().withDelegate(ScanDelegate())

while True:
    scanner.scan(60.0, passive=True)

