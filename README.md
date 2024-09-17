# govee_bluetooth_gateway
**Data logger for Govee brand bluetooth sensors**

This is a python Bluetooth advertisement scanner for the Govee brand Bluetooth
temperature sensor. Tested on model H5075 using Raspberry Pi Zero W.
Temperature, humidity, and battery level is published to local influxdb database (v1.x) using cronograf for visualization.

It uses the *bluepy* library to scan for the Govee advertisement packets, reads the temperature, humidity, battery level and signal strength from the advertisement packet and publishes it to an influxdb database. All data is retained fo 24hrs and a continuous query downsamples to 1 minute intervals and stored in a separate measurement infinately. The script is intended to be run as a service and can be started with systemd, run as root.  It reads the configuration from /boot/firmware/govee_gateway.conf.

This has been optimised for 32 bit raspberry pi products like the Pi Zero W.

Chronograph can be used to visualize the data by browsing to http://<host>:8888.  The data is stored in the "hygrometers" database.  The data is stored in the "TempHumidity" measurement.  The data is downsampled to 1 minute intervals and stored in the "TempHumidityDownsampled" measurement.  The data is stored with the following tags: MAC, site, location, device_name.  The fields are temp_C, humidity_percent, battery_percent, rssi.

Credit:
Forked from tsaitsai/govee_bluetooth_gateway, who used information for Govee advertisement format from
github.com/Thrilleratplay/GoveeWatcher

##INSTALLATION:

###Install dependencies:
 ```
 sudo apt-get install python3-pip libglib2.0-dev
 sudo pip3 install bluepy
 sudo pip3 install influxdb
 sudo apt-get install influxdb
 sudo apt-get install chronograf
```

###Create the influx database:
```
influx
CREATE DATABASE "hygrometers"
```
###Configure the influxdb retention policies
One for 1 day and one for infinity which will be used for downsampling
```
CREATE RETENTION POLICY "1day" ON "hygrometers" DURATION 1d REPLICATION 1 DEFAULT
CREATE RETENTION POLICY "inf" on "hygrometers" DURATION inf REPLICATION 1
```

###Configure the influxdb continuous query to downsample the data
```
CREATE CONTINUOUS QUERY "cq1m" ON "hygrometers" BEGIN SELECT mean(temp_C) as temp_C, mean(humidity_percent) as humidity_percent, mean(battery_percent) as battery_percent INTO "hygrometers"."inf"."TempHumidityDownsampled" FROM "TempHumidity" GROUP BY time(1min), MAC, site, location, device_name END             
```

The configuration file is stored in `/boot/firmware/govee_gateway.conf`

The configuration file is in the following format:
```
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
```

The configuration file is read at the beginning of the script.  The script will scan for the Govee hygrometers and publish the data to the influxdb database.

Needs sudo to run on Raspbian:
`sudo python3 govee_gateway.py`

Run in background:
`sudo nohup python3 govee_gateway.py &`

Run as a service
Create a service file:
`sudo nano /etc/systemd/system/govee_gateway.service`

Add the following to the file:
```
[Unit]
Description=Govee Gateway
After=multi-user.target

[Service]
Type=simple
ExecStart=/usr/bin/python3 /home/pi/govee_bluetooth_gateway/govee_gateway.py
User=root

[Install]
WantedBy=multi-user.target
```
Enable and start the service:
```
sudo systemctl enable govee_gateway.service
sudo systemctl start govee_gateway.service
```
Get the status:
`sudo systemctl start govee_gateway.service`