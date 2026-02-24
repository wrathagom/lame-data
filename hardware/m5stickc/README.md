# M5StickC Plus Sensor

## Configuration

1. Copy `config.h.example` to `config.h`
2. Edit `config.h` with your WiFi credentials and Pi IP addresses
3. (Optional) Set `deviceName` for display convenience - this only appears on the device screen when you press the button

## Upload Instructions

1. Install Arduino IDE
2. Add ESP32 board support (Board Manager URL: `https://dl.espressif.com/dl/package_esp32_index.json`)
3. Install M5StickCPlus library via Library Manager
4. Select board: M5StickC Plus
5. Upload `horse_sensor.ino`

## Multiple Sensors

Each M5StickC automatically gets a unique device ID derived from its hardware MAC address (4-character hex code like "A3F2"). You can flash the same firmware to all devices without any configuration changes.

**To identify each device:**
1. Press Button A on the device to see its unique ID on the screen
2. Note the ID (e.g., "A3F2")
3. Assign device locations in the web UI:
   - Left Front
   - Right Front
   - Left Rear
   - Right Rear
   - Poll/Withers

The hardware ID is automatically included in all data packets, allowing the Pi server to track multiple devices simultaneously.
