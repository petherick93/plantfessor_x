import datetime
import logging
import os
import time

import Adafruit_DHT
import gspread
import smbus

from oauth2client.service_account import ServiceAccountCredentials


# The DHT22 Sensor and GPIO pin #
SENSOR = Adafruit_DHT.DHT22
PIN = 4

GDOCS_OAUTH_JSO = 'plantfessorx-auth.json'

# Google Docs spreadsheet name.
GDOCS_SPREADSHEET_NAME = 'plantfessor_x'

# How long to wait (in seconds) between measurements.
FREQUENCY_SECONDS = 1800


def setup_logging():
    path_dir = os.path.realpath(__file__)
    log_name = datetime.now().strftime('plantfessor_x_watch_log_%d_%m_%Y.log')
    logging.basicConfig(filename=os.path.join(path_dir, 'logs', log_name), level=logging.DEBUG)


def login_open_sheet(oauth_key_file, spreadsheet):
    """Connect to Google Docs spreadsheet and return the first worksheet."""
    try:
        scope = ['https://spreadsheets.google.com/feeds']
        oauth_key_file_path = os.path.join(os.path.realpath(__file__), 'auth', oauth_key_file)
        credentials = ServiceAccountCredentials.from_json_keyfile_name(oauth_key_file_path, scope)
        gc = gspread.authorize(credentials)
        worksheet = gc.open(spreadsheet).sheet1
        return worksheet

    except Exception as ex:
        logging.error('Google sheet login failed with error:', ex)
        return None


def get_light_data():
    # Get I2C bus
    bus = smbus.SMBus(1)

    # TSL2561 address, 0x39(57)
    # Select control register, 0x00(00) with command register, 0x80(128)
    # 0x03(03) Power ON mode
    bus.write_byte_data(0x39, 0x00 | 0x80, 0x03)

    # TSL2561 address, 0x39(57)
    # Select timing register, 0x01(01) with command register, 0x80(128)
    # 0x02(02) Nominal integration time = 402ms
    bus.write_byte_data(0x39, 0x01 | 0x80, 0x02)

    # Read data back from 0x0C(12) with command register, 0x80(128), 2 bytes
    # ch0 LSB, ch0 MSB
    data = bus.read_i2c_block_data(0x39, 0x0C | 0x80, 2)

    # Read data back from 0x0E(14) with command register, 0x80(128), 2 bytes
    # ch1 LSB, ch1 MSB
    data1 = bus.read_i2c_block_data(0x39, 0x0E | 0x80, 2)

    # Convert the data
    full_spectrum_light = data[1] * 256 + data[0]
    infrared_light = data1[1] * 256 + data1[0]
    visible_light = full_spectrum_light - infrared_light

    return full_spectrum_light, infrared_light, visible_light


def main():
    # setup logging, and initialize plantfessor_x_sheet
    setup_logging()
    plantfessor_x_sheet = None

    # setup a continue loop
    while True:
        # grab our data file
        if plantfessor_x_sheet is None:
            logging.info('Logging in and Grabbing Plantfessor X Sheet')
            plantfessor_x_sheet = login_open_sheet(GDOCS_OAUTH_JSO, GDOCS_SPREADSHEET_NAME)

        # grab the temperature and humidity data
        logging.info('Grabbing Humidity and Temperature data')
        humidity, temperature = Adafruit_DHT.read_retry(SENSOR, PIN)

        # if none, wait 30 seconds and try again
        if humidity is None and temperature is None:
            # log and wait
            logging.warning('Failed to grab data, waiting 30 seconds')
            time.sleep(30)

            # try and grab the temperature and humidity data again
            humidity, temperature = Adafruit_DHT.read_retry(SENSOR, PIN)

        # grab the light data
        logging.info('Grabbing Light data')
        full_spectrum_light, infrared_light, visible_light = get_light_data()

        # if none, wait 30 seconds and try again
        if full_spectrum_light is None and infrared_light is None and visible_light is None:
            logging.warning('Failed to grab data, waiting 30 seconds')
            time.sleep(30)
            # try and grab the light data again
            full_spectrum_light, infrared_light, visible_light = get_light_data()

        # Append the data in the spreadsheet, including a timestamp
        try:
            plantfessor_x_sheet.append_row(
                (datetime.datetime.now(), temperature, humidity, full_spectrum_light, infrared_light, visible_light)
            )

        except:
            # Error appending data, most likely because credentials are stale.
            # Null out the worksheet so a login is performed at the top of the loop.
            logging.warning("Couldn't append data, waiting 30 seconds to try again".format(FREQUENCY_SECONDS))
            plantfessor_x_sheet = None
            time.sleep(30)
            continue

        # wait designated amount of time until collection data again
        time.sleep(FREQUENCY_SECONDS)


if __name__ == '__main__':
    main()

