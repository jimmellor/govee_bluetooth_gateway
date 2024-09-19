#!/usr/bin/python
'''
This is a python Bluetooth advertisement scanner for the Govee brand Bluetooth
temperature sensor.  Tested on model H5075 using Raspberry Pi Zero W.
Temperature, humidity, and battery level is published to local influxdb database using cronograf for visualization.

Chronograph can be used to visualize the data by browsing to http://<host>:8888.  The data is stored in the "hygrometers" database.  The data is stored in the "TempHumidity" measurement.  The data is downsampled to 1 minute intervals and stored in the "TempHumidityDownsampled" measurement.  The data is stored with the following tags: MAC, site, location, device_name.  The fields are temp_C, humidity_percent, battery_percent, rssi.

Credit:
Forked from tsaitsai/govee_bluetooth_gateway who used information for Govee advertisement format from
github.com/Thrilleratplay/GoveeWatcher

INSTALLATION:

Install dependencies:
 sudo apt-get install python3-pip libglib2.0-dev
 sudo pip3 install bluepy
 sudo pip3 install influxdb
 sudo apt-get install influxdb
 sudo apt-get install chronograf

Create the influx database
    influx
    CREATE DATABASE "hygrometers"

Configure the influxdb retention policies, one for 1 day and one for infinity which will be used for downsampling
    CREATE RETENTION POLICY "1day" ON "hygrometers" DURATION 1d REPLICATION 1 DEFAULT
    CREATE RETENTION POLICY "inf" on "hygrometers" DURATION inf REPLICATION 1

Configure the influxdb continuous query to downsample the data
    CREATE CONTINUOUS QUERY "cq1m" ON "hygrometers" BEGIN SELECT mean(temp_C) as temp_C, mean(humidity_percent) as humidity_percent, mean(battery_percent) as battery_percent INTO "hygrometers"."inf"."TempHumidityDownsampled" FROM "TempHumidity" GROUP BY time(1min), MAC, site, location, device_name END             


The configuration file is stored in /boot/firmware/govee_gateway.conf

The configuration file is in the following format:
[influxdb]
name = hygrometers
user = admin #default user is admin
pass = admin #default password is admin
host = localhost
port = 8086

[site]
name = 1 Accacia Ave
location = lat, long

[hygrometers]
D34E = Living Room  #last four digits of the MAC address of the hygrometer, also appears in the device name
AD4F = Bedroom

The configuration file is read at the beginning of the script.  The script will scan for the Govee hygrometers and publish the data to the influxdb database.
Needs sudo to run on Raspbian:
sudo python3 govee_gateway.py

Run in background:
sudo nohup python3 govee_gateway.py &

Run as a service
Create a service file:
sudo nano /etc/systemd/system/govee_gateway.service

Add the following to the file:
[Unit]
Description=Govee Gateway
After=multi-user.target

[Service]
Type=idle
ExecStart=/usr/bin/python3 /home/pi/govee_bluetooth_gateway/govee_gateway.py
Restart=always
User=root

[Install]
WantedBy=multi-user.target

Enable and start the service:
sudo systemctl enable govee_gateway.service
sudo systemctl start govee_gateway.service
'''

from __future__ import print_function

import configparser

from time import gmtime, strftime, sleep
from bluepy.btle import Scanner, DefaultDelegate, BTLEException
import sys

import logging

# influx db imports
from influxdb import InfluxDBClient

# configuration
# NOTE on a raspberry pi the config file should be in /boot/firmware so that it is easily accessible from PC or Mac with a card reader
conf = configparser.ConfigParser()

conf.read('/boot/firmware/govee_gateway.conf')

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

# logging config
import logging
logging.basicConfig(
    filename="/var/log/govee_gateway.log",
    encoding="utf-8",
    filemode="a",
    format="{asctime} - {levelname} - {message}",
    style="{",
    datefmt="%Y-%m-%d %H:%M",
    level=logging.DEBUG
)

class ScanDelegate(DefaultDelegate):
    
    global client
    
    def handleDiscovery(self, dev, isNewDev, isNewData):
        #if (dev.addr == "a4:c1:38:xx:xx:xx") or (dev.addr == "a4:c1:38:xx:xx:xx"):
        if dev.addr[:8]=="a4:c1:38":
            #returns a list, of which the [2] item of the [3] tupple is manufacturing data
            adv_list = dev.getScanData()
            adv_manuf_data = adv_list[3][2]
            logger.debug("adv_list = ", adv_list)

            #resolve the name of the hygrometer
            try:
                # Resolve device_id get the last five characters of the MAC address, remove the semi-colons, make it uppercase
                device_id = dev.addr[-5:].replace(":", "").upper()
                device_name = hygrometer_names[device_id]
            except KeyError: #name doesn't exist in the config file
                device_name = device_id
            
            #this is the location of the encoded temp/humidity and battery data
            temp_hum_data = adv_manuf_data[6:12]
            battery = adv_manuf_data[12:14]

            # need to log output while we get occastional errors
            logging.debug("temp hum data = ", str(temp_hum_data))
            logging.debug("battery data = ", str(battery))
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
                logging.error("issues with integer conversion", exc_info=True)

            try:
                battery_percent = int(adv_manuf_data[12:14]) / 64 * 100
            except:
                logging.error("adv_manuf_data = ", adv_manuf_data)
                logging.error("issues with battery conversion from hex to int", exc_info=True)
                battery_percent = 200
            battery_percent = round(battery_percent)

            temp_F = round(temp_C*9/5+32, 1)

            try:
                hum_percent = ((int(temp_hum_data, 16)) % 1000) / 10
            except:
                logging.error("temp_hum_data = ", str(temp_hum_data))
                logging.error("issues with humidity conversion from hex to int", exc_info=True)
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

