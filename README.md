# govee_bluetooth_gateway
**Data logger for Govee brand bluetooth sensors**

A python BLE advertisement scanner for the Govee brand
temperature and humidity sensors. Tested on model H5075 using Raspberry Pi Zero W. Temperature, humidity, and battery level is published to local influxdb database (v1.x) using cronograf for visualization.

#### How it works

It uses the *bluepy* library to scan for the Govee advertisement packets, reads the temperature, humidity, battery level and signal strength from the advertisement packet and publishes it to an influxdb database. All data is retained fo 24hrs and a continuous query downsamples to 1 minute intervals and stored in a separate measurement infinately. The script is intended to be run as a service and can be started with systemd, run as root.  It reads the configuration from /boot/firmware/govee_gateway.conf.

This has been optimised for 32 bit raspberry pi products like the Pi Zero W.

Chronograph can be used to visualize the data using a browser on another device to access the pi on port 8888 (default).  The data is stored in the "hygrometers" database in the "TempHumidity" measurement, downsampled to 1 minute intervals and stored in the "TempHumidityDownsampled" measurement. Data is tagged with `MAC`, `site`, `location`, `device_name`.  The fields are `temp_C`, `humidity_percent`, `battery_percent`, `rssi`.

#### Credit
Forked from tsaitsai/govee_bluetooth_gateway, who used information for Govee advertisement format from
github.com/Thrilleratplay/GoveeWatcher

#### Installation

##### Install dependencies
 ```
 sudo apt-get install python3-pip libglib2.0-dev
 sudo pip3 install bluepy
 sudo pip3 install influxdb
 sudo apt-get install influxdb
 sudo apt-get install chronograf
```
*Note* this was designed to work influx db 1.x, as it's 32 bit and will run on older hardware.


##### Configure Influx

The Influx CLI must be used to set up the databases. Start the shell by running `influx`

##### Create the influx database
```
CREATE DATABASE "hygrometers"
```

##### Configure the influxdb retention policies
One for 1 day and one for infinity which will be used for downsampling
```
CREATE RETENTION POLICY "1day" ON "hygrometers" DURATION 1d REPLICATION 1 DEFAULT
CREATE RETENTION POLICY "inf" on "hygrometers" DURATION inf REPLICATION 1
```

##### Configure the influxdb continuous query to downsample the data
```
CREATE CONTINUOUS QUERY "cq1m" ON "hygrometers" BEGIN SELECT mean(temp_C) as temp_C, mean(humidity_percent) as humidity_percent, mean(battery_percent) as battery_percent INTO "hygrometers"."inf"."TempHumidityDownsampled" FROM "TempHumidity" GROUP BY time(1min), MAC, site, location, device_name END             
```

The configuration file is stored in `/boot/firmware/govee_gateway.conf`

Similar to the way supplicant.conf can be configured headlessly in Raspbian, you can make configuration changes by modifying this file before you switch on the raspberry pi for the first time. Once you've copied the image to the SD card, open it on any computer with a card reader and edit the file that appears in the 'bootfs' partition.

Two sections you should take note of:
*Site* allows you to specify where the data will be logged, so you can store a location name and lat,long with each record. That should be to identify the location of the logger itself.

*Hygrometers* allows you to name each meter so the data captured is labelled. To do this, the last four hex digits of the meter MAC address are used, and these have to be determined first (using a Bluetooth Scanner for example), then a label, e.g. _hallway_, _bedroom_ added.

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

The configuration file is read when the script first executes, restart it to read any changes.

#### RUNNING:

##### Run from the command line
Needs sudo to run on Raspbian

`sudo python3 govee_gateway.py`

Run in background

`sudo nohup python3 govee_gateway.py &`

##### Run as a service

Create a service file

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
Get the status

`sudo systemctl start govee_gateway.service`