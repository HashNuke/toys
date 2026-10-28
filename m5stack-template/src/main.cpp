#include <BoardApp.h>
// USB Wi-Fi setup is inherited: uv run python -m board_runtime.serial_wifi

void appSetup() {
  M5.Display.setTextSize(2);
  M5.Display.setCursor(12, 32);
  M5.Display.println("New board app");
}

void appLoop() {
  if (BoardRuntime::takeRefresh()) {
    // Respond to the signed Bluetooth refresh command here.
  }
  if (BoardRuntime::takeWifiChanged()) {
    // Your app can resume network work with the new Wi-Fi configuration.
  }
  // Keep this nonblocking so serial and BLE commands remain responsive.
}
