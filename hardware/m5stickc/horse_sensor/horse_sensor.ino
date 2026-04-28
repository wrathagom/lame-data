#include <M5StickCPlus.h>
#include <Wire.h>
#include <WiFi.h>
#include <WiFiUdp.h>
#include <ArduinoOTA.h>
#include "config.h"
#include "esp_mac.h"

// Bump this when shipping a firmware-affecting change. The Pi reads this
// string verbatim from the source file and compares it against what each
// stick reports over BAT to drive the fleet-update banner.
const char* FIRMWARE_VERSION = "1.0.2";

// Device ID derived from hardware MAC address
String deviceID;

// Currently connected network
int connectedNetworkIndex = -1;
const char* currentPiIP = "10.42.0.1";  // Default

// OPTIMAL SETTINGS
const int BATCH_SIZE = 20;
const int SEND_INTERVAL = 100;

WiFiUDP udp;
unsigned long lastBatteryUpdate = 0;

// IMU FIFO constants
const uint8_t MPU6886_ADDR = 0x68;
const uint8_t FIFO_COUNT_H = 0x72;
const uint8_t FIFO_R_W = 0x74;
const uint8_t INT_STATUS = 0x3A;
const int FIFO_SAMPLE_BYTES = 14;  // 2 bytes each: ax,ay,az,temp,gx,gy,gz
const unsigned long SAMPLE_INTERVAL_US = 4000;  // 250 Hz = 4ms per sample
unsigned long fifoOverflows = 0;

// Sync state
unsigned long syncMillis = 0;
bool syncReceived = false;
const unsigned long BATTERY_UPDATE_INTERVAL = 30000;

// Batching
String batchBuffer[BATCH_SIZE];
int batchCount = 0;
unsigned long lastSendTime = 0;

// Connection management
unsigned long lastConnectionCheck = 0;
const unsigned long CONNECTION_CHECK_INTERVAL = 5000;
bool wasConnected = false;

// Display management
bool displayOn = false;
unsigned long displayOnTime = 0;
const unsigned long DISPLAY_TIMEOUT = 2000;

//Button Management
unsigned long lastButtonCheck = 0;
const unsigned long BUTTON_CHECK_INTERVAL = 1000;  // ms

// USB power management — when plugged into the charging hub, keep the screen
// on so you can glance at all five sticks and confirm they're charging.
bool usbPowered = false;
unsigned long lastPowerCheck = 0;
unsigned long lastPluggedInRefresh = 0;
const unsigned long POWER_CHECK_INTERVAL = 2000;       // poll VBUS every 2s
const unsigned long PLUGGED_IN_REFRESH_INTERVAL = 10000; // redraw battery % every 10s while plugged

// AXP192 power-input-status register: bit 5 = VBUS present (USB plugged in).
bool isUsbPowered() {
  return (M5.Axp.Read8bit(0x00) & 0x20) != 0;
}

// AXP192 power-operation-mode register: bit 6 = battery actively charging.
// Distinct from "plugged in but already full" — useful for accurate labeling.
bool isChargingActive() {
  return (M5.Axp.Read8bit(0x01) & 0x40) != 0;
}

String getDeviceID() {
  // Use device-unique portion of MAC (bytes 3, 4, 5 in standard order)
  uint8_t mac[6];
  esp_efuse_mac_get_default(mac);
  // mac[0-2] = OUI (manufacturer), mac[3-5] = device-unique
  char id[7];
  sprintf(id, "%02X%02X%02X", mac[3], mac[4], mac[5]);
  return String(id);
}

void setup() {
  M5.begin(true, true, false);
  M5.IMU.Init();
  M5.IMU.SetAccelFsr(M5.IMU.AFS_16G);
  M5.IMU.enableFIFO(M5.IMU.ODR_250Hz);
  M5.IMU.resetFIFO();

  // Get unique device ID from hardware
  deviceID = getDeviceID();

  // Turn off screen immediately after initialization
  M5.Lcd.fillScreen(BLACK);
  M5.Axp.ScreenBreath(0);

  // CPU optimization
  setCpuFrequencyMhz(80);

  // Connect to WiFi
  connectToWiFi();

  udp.begin(udpPort);
  lastSendTime = millis();
  lastConnectionCheck = millis();

  delay(1000);
}

// Runs once per successful WiFi connect. Hostname is per-device so the fleet
// shows up distinctly in mDNS browsers (Arduino IDE Network Ports, PlatformIO,
// `dns-sd -B _arduino._tcp` from the Pi).
void setupOTA() {
  String hostname = "horse-" + deviceID;
  ArduinoOTA.setHostname(hostname.c_str());
  ArduinoOTA.setPassword(otaPassword);

  ArduinoOTA.onStart([]() {
    // Flash incoming — light the LCD so the user has visual confirmation.
    M5.Axp.ScreenBreath(50);
    M5.Lcd.fillScreen(BLACK);
    M5.Lcd.setRotation(0);
    M5.Lcd.setTextSize(2);
    M5.Lcd.setCursor(10, 40);
    M5.Lcd.setTextColor(YELLOW);
    M5.Lcd.print("Updating");
    M5.Lcd.setCursor(10, 70);
    M5.Lcd.print("Firmware");
    M5.Lcd.setCursor(10, 110);
    M5.Lcd.setTextColor(WHITE);
    M5.Lcd.print("0%");
  });

  ArduinoOTA.onProgress([](unsigned int progress, unsigned int total) {
    int pct = total > 0 ? (progress * 100) / total : 0;
    // Overwrite just the percentage line to avoid full-screen flicker.
    M5.Lcd.fillRect(10, 110, 120, 24, BLACK);
    M5.Lcd.setCursor(10, 110);
    M5.Lcd.setTextColor(WHITE);
    M5.Lcd.printf("%d%%", pct);
  });

  ArduinoOTA.onEnd([]() {
    M5.Lcd.fillRect(10, 110, 120, 24, BLACK);
    M5.Lcd.setCursor(10, 110);
    M5.Lcd.setTextColor(GREEN);
    M5.Lcd.print("Rebooting");
  });

  ArduinoOTA.onError([](ota_error_t error) {
    M5.Lcd.fillScreen(BLACK);
    M5.Lcd.setCursor(10, 60);
    M5.Lcd.setTextColor(RED);
    M5.Lcd.print("OTA FAILED");
    M5.Lcd.setCursor(10, 100);
    M5.Lcd.setTextSize(1);
    M5.Lcd.printf("err=%d", (int)error);
  });

  ArduinoOTA.begin();
}

void connectToWiFi() {
  WiFi.mode(WIFI_STA);
  WiFi.setTxPower(WIFI_POWER_19_5dBm);

  // Try each network in priority order
  for (int i = 0; i < NUM_NETWORKS; i++) {
    WiFi.begin(networks[i].ssid, networks[i].password);

    // Wait up to 10 seconds for connection
    int attempts = 0;
    while (WiFi.status() != WL_CONNECTED && attempts < 20) {
      delay(500);
      attempts++;
    }

    if (WiFi.status() == WL_CONNECTED) {
      // Successfully connected!
      connectedNetworkIndex = i;
      currentPiIP = networks[i].piIP;
      setCpuFrequencyMhz(160);
      wasConnected = true;
      setupOTA();
      return;
    }

    // Failed to connect to this network, try next one
    WiFi.disconnect();
    delay(500);
  }

  // Failed to connect to any network
  connectedNetworkIndex = -1;
  setCpuFrequencyMhz(80);
  WiFi.mode(WIFI_OFF);
}

void checkConnection() {
  if (millis() - lastConnectionCheck < CONNECTION_CHECK_INTERVAL) {
    return;
  }
  lastConnectionCheck = millis();
  
  if (WiFi.status() != WL_CONNECTED) {
    if (wasConnected) {
      wasConnected = false;
      connectedNetworkIndex = -1;
      setCpuFrequencyMhz(80);
    }
    
    // Try to reconnect to any available network
    WiFi.mode(WIFI_STA);
    
    for (int i = 0; i < NUM_NETWORKS; i++) {
      WiFi.begin(networks[i].ssid, networks[i].password);
      delay(500);
      
      if (WiFi.status() == WL_CONNECTED) {
        connectedNetworkIndex = i;
        currentPiIP = networks[i].piIP;
        setCpuFrequencyMhz(160);
        wasConnected = true;
        setupOTA();
        return;
      }

      WiFi.disconnect();
    }

    // Still not connected, turn off WiFi to save power
    WiFi.mode(WIFI_OFF);
  }
}

void showStatus() {
  // Turn on screen
  M5.Axp.ScreenBreath(50);
  displayOn = true;
  displayOnTime = millis();

  // Clear and setup display
  M5.Lcd.fillScreen(BLACK);
  M5.Lcd.setRotation(0);  // UPDATED TO ROTATION 0
  M5.Lcd.setTextSize(2);

  // Display Device Info
  M5.Lcd.setCursor(10, 20);
  M5.Lcd.setTextColor(YELLOW);
  M5.Lcd.printf("ID: %s\n", deviceID.c_str());

  M5.Lcd.setCursor(10, 50);
  M5.Lcd.setTextColor(CYAN);
  M5.Lcd.printf("%s\n", deviceName);

  // Display Battery
  float battVoltage = M5.Axp.GetBatVoltage();
  float battPercent = (battVoltage - 3.0) / (4.2 - 3.0) * 100;
  if (battPercent > 100) battPercent = 100;
  if (battPercent < 0) battPercent = 0;

  M5.Lcd.setCursor(10, 80);

  // Color code battery level
  if (battPercent > 50) {
    M5.Lcd.setTextColor(GREEN);
  } else if (battPercent > 20) {
    M5.Lcd.setTextColor(ORANGE);
  } else {
    M5.Lcd.setTextColor(RED);
  }
  M5.Lcd.printf("Batt: %.0f%%\n", battPercent);

  // Display connection status and network name
  M5.Lcd.setCursor(10, 110);
  if (WiFi.status() == WL_CONNECTED && connectedNetworkIndex >= 0) {
    M5.Lcd.setTextColor(GREEN);
    M5.Lcd.printf("%s", networks[connectedNetworkIndex].ssid);
  } else {
    M5.Lcd.setTextColor(RED);
    M5.Lcd.print("No WiFi");
  }

  // Charging status — only shown when USB is plugged in.
  if (isUsbPowered()) {
    M5.Lcd.setCursor(10, 140);
    if (isChargingActive()) {
      M5.Lcd.setTextColor(GREEN);
      M5.Lcd.print("Charging");
    } else {
      M5.Lcd.setTextColor(CYAN);
      M5.Lcd.print("Charged");
    }
  }

  // FIFO overflow count gets its own line so it never overlaps the charging
  // status. Both are signal — power state and lost samples — and you want
  // to see them at the same time, especially when a stick is still on the
  // hub but somehow dropping samples.
  if (fifoOverflows > 0) {
    M5.Lcd.setCursor(10, 170);
    M5.Lcd.setTextColor(RED);
    M5.Lcd.printf("FIFO OVF: %lu", fifoOverflows);
  }
}

void checkDisplayTimeout() {
  // When plugged into the charging hub we deliberately keep the screen lit
  // so all five sticks are visible at a glance. The USB poll re-renders the
  // battery values every few seconds so stale info doesn't sit on screen.
  if (usbPowered) return;

  if (displayOn && (millis() - displayOnTime > DISPLAY_TIMEOUT)) {
    // Turn off display after timeout
    M5.Axp.ScreenBreath(0);
    M5.Lcd.fillScreen(BLACK);
    displayOn = false;
  }
}

// Poll VBUS presence; drive the display on/off transitions. Called from loop().
void checkPowerState() {
  if (millis() - lastPowerCheck < POWER_CHECK_INTERVAL) {
    return;
  }
  lastPowerCheck = millis();

  bool nowUsb = isUsbPowered();

  if (nowUsb && !usbPowered) {
    // Just plugged in — wake the screen.
    showStatus();
    lastPluggedInRefresh = millis();
  } else if (!nowUsb && usbPowered) {
    // Just unplugged — hand control back to the normal timeout path so the
    // screen blanks ~2s from now instead of staying on indefinitely.
    displayOnTime = millis();
  } else if (nowUsb && displayOn &&
             (millis() - lastPluggedInRefresh > PLUGGED_IN_REFRESH_INTERVAL)) {
    // Periodic refresh while plugged — battery % creeping up, etc.
    showStatus();
    lastPluggedInRefresh = millis();
  }

  usbPowered = nowUsb;
}

uint16_t readFIFOCount() {
  Wire1.beginTransmission(MPU6886_ADDR);
  Wire1.write(FIFO_COUNT_H);
  Wire1.endTransmission(false);
  Wire1.requestFrom((uint8_t)MPU6886_ADDR, (uint8_t)2);
  uint16_t count = (Wire1.read() << 8) | Wire1.read();
  return count;
}

void readFIFOSample(uint8_t buf[14]) {
  Wire1.beginTransmission(MPU6886_ADDR);
  Wire1.write(FIFO_R_W);
  Wire1.endTransmission(false);
  Wire1.requestFrom((uint8_t)MPU6886_ADDR, (uint8_t)14);
  for (int i = 0; i < 14; i++) {
    buf[i] = Wire1.read();
  }
}

bool checkFIFOOverflow() {
  Wire1.beginTransmission(MPU6886_ADDR);
  Wire1.write(INT_STATUS);
  Wire1.endTransmission(false);
  Wire1.requestFrom((uint8_t)MPU6886_ADDR, (uint8_t)1);
  uint8_t status = Wire1.read();
  return (status >> 4) & 0x01;  // Bit 4 = FIFO overflow
}

void loop() {
  // Poll USB/charging state; drives screen on/off transitions while plugged
  // into the charging hub. Must run before checkDisplayTimeout so usbPowered
  // is current when the timeout logic decides whether to blank.
  checkPowerState();

  // Auto-turn off display after timeout (no-op while plugged in).
  checkDisplayTimeout();

  // Check WiFi connection periodically
  checkConnection();
  
  // Only sample and stream if connected
  if (WiFi.status() == WL_CONNECTED) {
    // Service any pending OTA transfer. Non-blocking — if an update is being
    // pushed by the Pi, this is where it actually lands.
    ArduinoOTA.handle();

    // Check for incoming sync broadcast (non-blocking)
    int packetSize = udp.parsePacket();
    if (packetSize > 0) {
      char incomingPacket[64];
      int len = udp.read(incomingPacket, sizeof(incomingPacket) - 1);
      if (len > 0) {
        incomingPacket[len] = '\0';
        if (strcmp(incomingPacket, "SYNC") == 0) {
          syncMillis = millis();
          syncReceived = true;
          // Send SYNC_ACK back to the Pi
          char ackBuffer[64];
          snprintf(ackBuffer, sizeof(ackBuffer), "SYNC_ACK,%s,%lu",
                   deviceID.c_str(), syncMillis);
          udp.beginPacket(currentPiIP, udpPort);
          udp.print(ackBuffer);
          udp.endPacket();
        }
      }
    }

    // Drain all available samples from the IMU FIFO
    uint16_t fifoBytes = readFIFOCount();
    int fifoSamples = fifoBytes / FIFO_SAMPLE_BYTES;
    unsigned long now = millis();

    for (int i = 0; i < fifoSamples; i++) {
      uint8_t buf[14];
      readFIFOSample(buf);

      // Parse raw 14 bytes: ax(2), ay(2), az(2), temp(2), gx(2), gy(2), gz(2)
      int16_t rawAx = (int16_t)((buf[0]  << 8) | buf[1]);
      int16_t rawAy = (int16_t)((buf[2]  << 8) | buf[3]);
      int16_t rawAz = (int16_t)((buf[4]  << 8) | buf[5]);
      // buf[6..7] = temp, skip
      int16_t rawGx = (int16_t)((buf[8]  << 8) | buf[9]);
      int16_t rawGy = (int16_t)((buf[10] << 8) | buf[11]);
      int16_t rawGz = (int16_t)((buf[12] << 8) | buf[13]);

      float accX = rawAx * M5.IMU.aRes;
      float accY = rawAy * M5.IMU.aRes;
      float accZ = rawAz * M5.IMU.aRes;
      float gyroX = rawGx * M5.IMU.gRes;
      float gyroY = rawGy * M5.IMU.gRes;
      float gyroZ = rawGz * M5.IMU.gRes;

      // Estimate timestamp: oldest sample first
      unsigned long sampleTime = now - (unsigned long)(fifoSamples - 1 - i) * (SAMPLE_INTERVAL_US / 1000);

      char sample[128];
      snprintf(sample, sizeof(sample), "%s,%lu,%.3f,%.3f,%.3f,%.2f,%.2f,%.2f",
               deviceID.c_str(), sampleTime, accX, accY, accZ, gyroX, gyroY, gyroZ);
      batchBuffer[batchCount] = String(sample);
      batchCount++;

      if (batchCount >= BATCH_SIZE) {
        sendBatch();
        batchCount = 0;
        lastSendTime = millis();
      }
    }

    // Check for FIFO overflow (samples were lost)
    if (checkFIFOOverflow()) {
      fifoOverflows++;
      M5.IMU.resetFIFO();
    }

    // Send remaining partial batch if interval elapsed
    if (batchCount > 0 && (millis() - lastSendTime >= SEND_INTERVAL)) {
      sendBatch();
      batchCount = 0;
      lastSendTime = millis();
    }

    if (millis() - lastBatteryUpdate > BATTERY_UPDATE_INTERVAL) {
      sendBatteryStatus();
      lastBatteryUpdate = millis();
    }

    // LOW PRIORITY: Check button only occasionally
    if (millis() - lastButtonCheck >= BUTTON_CHECK_INTERVAL) {
      M5.update();
      if (M5.BtnA.wasPressed()) {
        showStatus();
      }
      lastButtonCheck = millis();
    }

    delay(100);  // FIFO buffers samples; drain every ~100ms (~25 samples)
    
  } else {
    // Not connected - FIFO keeps buffering; if reconnect is quick we keep those samples.
    // If it overflows, the overflow check on reconnect will catch it and reset.

    M5.update();
    if (M5.BtnA.wasPressed()) {
      showStatus();
    }
    delay(100);
  }
}

void sendBatch() {
  if (batchCount == 0) return;
  
  udp.beginPacket(currentPiIP, udpPort);
  
  for (int i = 0; i < batchCount; i++) {
    udp.print(batchBuffer[i]);
    if (i < batchCount - 1) {
      udp.print("|");
    }
  }
  
  udp.endPacket();
}

void sendBatteryStatus() {
  float battVoltage = M5.Axp.GetBatVoltage();
  float battPercent = (battVoltage - 3.0) / (4.2 - 3.0) * 100;
  if (battPercent > 100) battPercent = 100;
  if (battPercent < 0) battPercent = 0;

  // Report "charging" as 1 when VBUS is present AND the battery is actively
  // taking charge. The Pi parser is backwards-compatible and treats the field
  // as optional (defaults to 0) so old firmware still parses cleanly.
  int charging = isUsbPowered() ? 1 : 0;

  // Field 7 is the running firmware version string so the Pi can detect
  // fleet-wide drift. Older Pi code (pre-firmware-manager) just ignored
  // trailing unknown fields.
  //
  // Field 6 ("charging") reports USB-power-present, NOT
  // battery-actively-charging. The Pi gates OTA flash on this — the relevant
  // safety signal is "is the stick getting external power right now" so a
  // mid-flash brownout can't brick it. A topped-off battery on the hub still
  // counts as charging:1 here, even though the AXP charging bit goes false
  // once the battery is full. The LCD's "Charging" vs "Charged" label is a
  // separate, finer distinction; only the BAT field affects OTA gating.
  char buffer[128];
  snprintf(buffer, sizeof(buffer), "BAT,%s,%.2f,%.0f,%lu,%d,%s",
           deviceID.c_str(), battVoltage, battPercent, fifoOverflows, charging,
           FIRMWARE_VERSION);

  udp.beginPacket(currentPiIP, udpPort);
  udp.print(buffer);
  udp.endPacket();
}
