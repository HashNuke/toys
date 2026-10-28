#pragma once
#include <Arduino.h>
namespace BoardRuntime {
void begin();
void poll();
// Called for application commands after reserved recovery/configuration commands.
void setSerialCommandHandler(void (*handler)(const String&));
bool appPaused();
bool takeRefresh();
bool takeWifiChanged();
}
