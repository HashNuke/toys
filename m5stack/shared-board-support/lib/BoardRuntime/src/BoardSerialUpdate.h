#pragma once
#include <Arduino.h>
#include <Update.h>
#include <M5Unified.h>

// Application-level download mode for the original ESP32 (not its ROM loader).
// Each 1024-byte chunk must be acknowledged before sending another.
using BoardSerialCommandHandler = void (*)(const String &);
inline BoardSerialCommandHandler &boardSerialCommandHandler() {
  static BoardSerialCommandHandler handler = nullptr;
  return handler;
}
inline void serviceSerialUpdate() {
  static String line;
  static bool overflow = false;
  while (Serial.available()) {
    const char c = Serial.read();
    if (c == '\r') continue;
    if (c != '\n') {
      if (!overflow && line.length() < 512) line += c;
      else { overflow = true; line = ""; }
      continue;
    }
    String command = line;
    line = "";
    if (overflow) {
      overflow = false;
      Serial.println("BOARD:ERROR command too long");
      continue;
    }
    if (command == "HN:PING") {
      Serial.println("HN:PONG serial-update-v1");
      continue;
    }
    if (!command.startsWith("HN:UPDATE ")) {
      if (boardSerialCommandHandler()) boardSerialCommandHandler()(command);
      continue;
    }
    unsigned int size = 0;
    char md5[33] = {};
    if (sscanf(command.c_str(), "HN:UPDATE %u %32s", &size, md5) != 2 ||
        size == 0 || size > 0x1b0000 || strlen(md5) != 32) {
      Serial.println("HN:ERROR invalid header");
      continue;
    }
    if (!Update.begin(size, U_FLASH)) {
      Serial.printf("HN:ERROR %s\n", Update.errorString());
      continue;
    }
    if (!Update.setMD5(md5)) {
      Update.abort();
      Serial.println("HN:ERROR invalid digest");
      continue;
    }
    M5.Display.fillScreen(TFT_BLACK);
    M5.Display.setTextColor(TFT_WHITE);
    M5.Display.setTextSize(2);
    M5.Display.setCursor(12, 24);
    M5.Display.println("Software download");
    M5.Display.println("  Receiving firmware...");
    Serial.setTimeout(15000);
    Serial.println("HN:READY");
    uint8_t buffer[1024];
    size_t received = 0;
    bool failed = false;
    while (received < size) {
      const size_t count = min(sizeof(buffer), size_t(size - received));
      if (Serial.readBytes(buffer, count) != count ||
          Update.write(buffer, count) != count) {
        failed = true;
        break;
      }
      received += count;
      Serial.printf("HN:ACK %u\n", unsigned(received));
      M5.Display.fillRect(12, 115, 290, 24, TFT_BLACK);
      M5.Display.setCursor(12, 115);
      M5.Display.printf("%u%%", unsigned(received * 100 / size));
    }
    Serial.setTimeout(1000);
    if (failed) {
      Update.abort();
      Serial.println("HN:ERROR transfer incomplete");
    } else if (!Update.end()) {
      Serial.printf("HN:ERROR %s\n", Update.errorString());
    } else {
      Serial.println("HN:DONE");
      Serial.flush();
      delay(200);
      ESP.restart();
    }
    M5.Display.setCursor(12, 155);
    M5.Display.println("Retry serial update.");
  }
}
