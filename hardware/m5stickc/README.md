# M5StickC Plus Sensor

## Configuration

1. Copy `config.h.example` to `config.h`
2. Edit `config.h` with your WiFi credentials and Pi IP addresses
3. Set `DEVICE_ID` (1-5) for each sensor

## Upload Instructions

1. Install Arduino IDE
2. Add ESP32 board support (Board Manager URL: `https://dl.espressif.com/dl/package_esp32_index.json`)
3. Install M5StickCPlus library via Library Manager
4. Select board: M5StickC Plus
5. Upload `horse_sensor.ino`

## Multiple Sensors

For multiple sensors, create separate `config.h` files or change `DEVICE_ID` before flashing each unit:
- Device 1: Left Front
- Device 2: Right Front
- Device 3: Left Rear
- Device 4: Right Rear
- Device 5: Poll/Withers
