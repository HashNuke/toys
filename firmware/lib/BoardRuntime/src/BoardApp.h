#pragma once
#include <M5Unified.h>
#include "BoardRuntime.h"
void appSetup();
void appLoop();
// All board programs use these entry points. Defining an independent setup/loop
// in the same program is a compile error, preventing accidental loss of recovery.
void setup() {
  Serial.setRxBufferSize(1024);
  Serial.begin(115200);
  auto cfg = M5.config();
  cfg.internal_spk = false;
  M5.begin(cfg);
  M5.Display.setRotation(1);
  M5.Display.setBrightness(128);
  BoardRuntime::begin();
  appSetup();
}
void loop() {
  BoardRuntime::poll();
  M5.update();
  if (!BoardRuntime::appPaused()) appLoop();
  delay(5);
}
