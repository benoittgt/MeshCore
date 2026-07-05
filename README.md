# Clone the branch
git clone -b companion-v1.16.0-custom-logo <your-repo-url>

# Flash using esptool (install with: pip install esptool)
esptool.py --chip esp32s3 --port COM3 write_flash 0x10000 bin/Heltec_v3_companion_radio_ble.bin

Replace COM3 with your actual COM port (check Device Manager under "Ports"). If the device isn't detected, hold BOOT, press RST, release both to enter download mode.

Or via PlatformIO (builds from source):

pio run -e Heltec_v3_companion_radio_ble --target upload
