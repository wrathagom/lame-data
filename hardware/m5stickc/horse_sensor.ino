#include <M5StickCPlus.h>
#include <WiFi.h>
#include <WiFiUdp.h>
#include "config.h"

// Currently connected network
int connectedNetworkIndex = -1;
const char* currentPiIP = "10.42.0.1";  // Default

// OPTIMAL SETTINGS
const int BATCH_SIZE = 20;
const int SEND_INTERVAL = 100;

WiFiUDP udp;
float accX, accY, accZ;
unsigned long sampleNumber = 0;
unsigned long lastBatteryUpdate = 0;
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

void setup() {
  M5.begin(true, true, false);
  M5.IMU.Init();
  
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
  M5.Lcd.printf("Device %d\n", DEVICE_ID);
  
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
    M5.Lcd.print("Disconnected");
  }
}

void checkDisplayTimeout() {
  if (displayOn && (millis() - displayOnTime > DISPLAY_TIMEOUT)) {
    // Turn off display after timeout
    M5.Axp.ScreenBreath(0);
    M5.Lcd.fillScreen(BLACK);
    displayOn = false;
  }
}

void loop() {
  // Auto-turn off display after timeout
  checkDisplayTimeout();
  
  // Check WiFi connection periodically
  checkConnection();
  
  // Only sample and stream if connected
  if (WiFi.status() == WL_CONNECTED) {
    M5.IMU.getAccelData(&accX, &accY, &accZ);
    sampleNumber++;
    
    char sample[100];
    snprintf(sample, sizeof(sample), "%d,%lu,%.3f,%.3f,%.3f", 
             DEVICE_ID, sampleNumber, accX, accY, accZ);
    batchBuffer[batchCount] = String(sample);
    batchCount++;
    
    bool batchFull = (batchCount >= BATCH_SIZE);
    bool intervalElapsed = (millis() - lastSendTime >= SEND_INTERVAL);
    
    if (batchFull || intervalElapsed) {
      sendBatch();
      batchCount = 0;
      lastSendTime = millis();
    }
    
    if (millis() - lastBatteryUpdate > BATTERY_UPDATE_INTERVAL) {
      sendBatteryStatus();
      lastBatteryUpdate = millis();
    }

    // LOW PRIORITY: Check button only occasionally (between batches)
    if (millis() - lastButtonCheck >= BUTTON_CHECK_INTERVAL) {
      M5.update();
      if (M5.BtnA.wasPressed()) {
        showStatus();
      }
      lastButtonCheck = millis();
    }
    
    delay(4);
    
  } else {
    // Not connected - check button more frequently since we're not sampling
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
  
  char buffer[100];
  snprintf(buffer, sizeof(buffer), "BAT,%d,%.2f,%.0f", 
           DEVICE_ID, battVoltage, battPercent);
  
  udp.beginPacket(currentPiIP, udpPort);
  udp.print(buffer);
  udp.endPacket();
}
