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
import paho.mqtt.client as mqtt

# influx db imports

from influxdb import InfluxDBClient

#from influxdb_client import InfluxDBClient, Point
#from influxdb_client.client.write_api import SYNCHRONOUS

# configuration
# NOTE copy the config file govee_ble_mqtt_pi.conf TO /etc/govee_ble_mqtt_pi.conf and modify it there
conf = configparser.ConfigParser()

config.read('/etc/govee_ble_mqtt_pi.conf')

# influx db configuration
dbname = conf['influxdb']['name']
dbuser = conf['influxdb']['user']
dbpass = conf['influxdb']['pass']
dbhost = conf['influxdb']['host']
dbport = conf['influxdb']['port']
dborg = conf['influxdb']['org']
client = InfluxDBClient(dbhost, dbport, dbuser, dbpass, dnname)

# write_api = client.write_api(write_options=SYNCHRONOUS)
# query_api = client.query_api()

def on_connect(client, userdata, flags, rc):
    print("Connected with result code "+str(rc))

def on_message(client, userdata, msg):
    print("on message")

client = mqtt.Client()
mqtt_prefix = conf['mqtt']['mqtt_gateway_name']
mqtt_gateway_name = conf['mqtt']['mqtt_gateway_name']

class ScanDelegate(DefaultDelegate):
    
    global client
    # mqtt message topic/payload:  /prefix/gateway_name/mac/
    global mqtt_prefix
    global mqtt_gateway_name
    
    def handleDiscovery(self, dev, isNewDev, isNewData):
        #if (dev.addr == "a4:c1:38:xx:xx:xx") or (dev.addr == "a4:c1:38:xx:xx:xx"):
        if dev.addr[:8]=="a4:c1:38":
            #returns a list, of which the [2] item of the [3] tupple is manufacturing data
            adv_list = dev.getScanData()
            adv_manuf_data = adv_list[3][2]
            print("adv list = ", adv_list)
            print("manuf data = ", adv_manuf_data)

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

            #p = Point("MAC",mac).tag("percent humidity", "hum_percent").field("temp_F", temp_F)
            #p = [Point("Temperature").tag("MAC",mac).field("temp_F", temp_F),Point("Humidity").tag("MAC",mac).field("percent humidity", hum_percent),Point("Battery").tag("MAC",mac).field("battery", battery_percent),Point("RSSI").field("rssi",signal)]
            #write_api.write(bucket=bucket, record=p)


            # createa a json object for influxdb client with the temperature, humidity, battery, rssi, timestamp in the format "2009-11-10T23:00:00Z"
            time = strftime("%Y-%m-%dT%H:%M:%SZ", gmtime())
            json_body = [
                {
                    "measurement": "Temperature",
                    "time": time,
                    "tags": {
                        "MAC": mac
                    },
                    "fields": {
                        "temp_C": temp_C
                    }
                },
                {
                    "measurement": "Humidity",
                    "time": time,
                    "tags": {
                        "MAC": mac
                    },
                    "fields": {
                        "percent humidity": hum_percent
                    }
                },
                {
                    "measurement": "Battery",
                    "time": time,
                    "tags": {
                        "MAC": mac
                    },
                    "fields": {
                        "battery": battery_percent
                    }
                },
                {
                    "measurement": "RSSI",
                    "time": time,
                    "tags": {
                        "MAC": mac
                    },
                    "fields": {
                        "rssi": signal
                    }
                }
            ]


            # write the json object to the influxdb
            write_api.write_points(json_body)

            
            #print("mac=", mac, "   percent humidity ", hum_percent, "   temp_F = ", temp_F, "   battery percent=", battery_percent, "  rssi=", signal)
            #mqtt_topic = mqtt_prefix + mqtt_gateway_name + mac + "/"

            #client.publish(mqtt_topic+"rssi", signal, qos=0)
            #client.publish(mqtt_topic+"temp_F", temp_F, qos=0)
            #client.publish(mqtt_topic+"hum", hum_percent, qos=0)
            #client.publish(mqtt_topic+"battery_pct", battery_percent, qos=0)
            
            sys.stdout.flush()

scanner = Scanner().withDelegate(ScanDelegate())

#replace localhost with your MQTT broker
#client.connect("localhost",1883,60)

#client.on_connect = on_connect
#client.on_message = on_message

while True:
    scanner.scan(60.0, passive=True)

