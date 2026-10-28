#include "BoardRuntime.h"
#include "BoardSerialUpdate.h"
#include <BoardIdentity.h>
#include <ArduinoJson.h>
#include <NimBLEDevice.h>
#include <Preferences.h>
#include <WiFi.h>
#include <esp_wifi.h>
#include <esp_system.h>
#include <mbedtls/ecdh.h>
#include <mbedtls/ecdsa.h>
#include <mbedtls/gcm.h>
#include <mbedtls/md.h>
#include <mbedtls/sha256.h>
#include <atomic>

namespace {
const char *SERVICE = "521cb560-6ce7-4d51-b234-76f821098001";
const char *HELLO = "521cb560-6ce7-4d51-b234-76f821098002";
const char *COMMAND = "521cb560-6ce7-4d51-b234-76f821098003";
const char *RESULT = "521cb560-6ce7-4d51-b234-76f821098004";
const char *DOMAIN = "toys-board-v1";
NimBLECharacteristic *helloChar, *resultChar;
SemaphoreHandle_t guard;
Preferences prefs;
uint8_t privateKey[32], publicKey[65], senderPublic[65], challenge[32];
uint8_t incoming[768];
size_t expected = 0, received = 0, queued = 0;
uint16_t owner = 0xffff;
uint32_t receiveStarted = 0, challengeStarted = 0, pauseUntil = 0, restartAt = 0;
std::atomic<bool> busy{false};
bool ready = false, refresh = false, wifiChanged = false, wifiPending = false;
wifi_config_t previousWifi{};
uint32_t wifiStarted = 0;
std::atomic<uint32_t> ipGeneration{0};
uint32_t wifiStartGeneration = 0;
String candidateSsid;
uint8_t responseKey[32], responseChallenge[32];
String responseRequest;
bool responseViaSerial = false;
void (*appSerialHandler)(const String&) = nullptr;

int randomBytes(void *, unsigned char *out, size_t len) { esp_fill_random(out, len); return 0; }
String hex(const uint8_t *bytes, size_t len) {
  String value;
  value.reserve(len * 2);
  for (size_t i = 0; i < len; ++i) { char b[3]; snprintf(b, sizeof(b), "%02x", bytes[i]); value += b; }
  return value;
}
void newChallenge() {
  esp_fill_random(challenge, sizeof(challenge));
  challengeStarted = millis();
  JsonDocument doc;
  doc["v"] = 1; doc["id"] = BOARD_DEVICE_ID;
  doc["public"] = hex(publicKey, sizeof(publicKey));
  doc["challenge"] = hex(challenge, sizeof(challenge));
  String hello; serializeJson(doc, hello);
  helloChar->setValue(hello.c_str());
}
void reject(const char *reason) {
  String error = String("ERROR:") + reason;
  resultChar->setValue(error.c_str());
  Serial.printf("BOARD:REJECT %s\n", reason);
  busy = false;
}
void reply(const char *error = nullptr) {
  JsonDocument doc;
  doc["request_id"] = responseRequest;
  doc["result"] = error ? "error" : "ok";
  if (error) doc["error"] = error;
  doc["wifi_connected"] = WiFi.status() == WL_CONNECTED;
  doc["ip"] = WiFi.localIP().toString();
  doc["serial_update"] = true;
  doc["free_heap"] = ESP.getFreeHeap();
  if (responseViaSerial) {
    Serial.print("BOARD:RESULT ");
    serializeJson(doc, Serial);
    Serial.println();
    busy = false;
    return;
  }
  String plain; serializeJson(doc, plain);
  String aad = String(DOMAIN) + " response" + BOARD_DEVICE_ID;
  uint8_t associated[128];
  memcpy(associated, aad.c_str(), aad.length());
  memcpy(associated + aad.length(), responseChallenge, 32);
  uint8_t output[512];
  esp_fill_random(output, 12);
  mbedtls_gcm_context gcm; mbedtls_gcm_init(&gcm);
  int ret = mbedtls_gcm_setkey(&gcm, MBEDTLS_CIPHER_ID_AES, responseKey, 256);
  if (!ret) ret = mbedtls_gcm_crypt_and_tag(&gcm, MBEDTLS_GCM_ENCRYPT, plain.length(), output, 12,
      associated, aad.length() + 32, (const uint8_t *)plain.c_str(), output + 12, 16, output + 12 + plain.length());
  mbedtls_gcm_free(&gcm);
  if (!ret) resultChar->setValue(output, 12 + plain.length() + 16);
  else resultChar->setValue("ERROR:response encryption failed");
  memset(responseKey, 0, sizeof(responseKey));
  busy = false;
}

class Writes : public NimBLECharacteristicCallbacks {
  void onWrite(NimBLECharacteristic *chr, NimBLEConnInfo &connection) override {
    auto data = chr->getValue();
    if (data.size() < 5 || xSemaphoreTake(guard, pdMS_TO_TICKS(50)) != pdTRUE) return;
    const uint8_t *p = (const uint8_t *)data.data();
    size_t total = (p[0] << 8) | p[1], offset = (p[2] << 8) | p[3];
    if (busy) { xSemaphoreGive(guard); return; }
    if (received && millis() - receiveStarted > 10000) received = expected = 0;
    if (offset == 0 && total >= 131 && total <= sizeof(incoming)) {
      received = 0; expected = total; owner = connection.getConnHandle(); receiveStarted = millis();
      resultChar->setValue("");
    }
    if (owner != connection.getConnHandle() || total != expected || offset != received || received + data.size() - 4 > expected) {
      received = expected = 0;
      resultChar->setValue("ERROR:invalid fragments");
    } else {
      memcpy(incoming + received, p + 4, data.size() - 4);
      received += data.size() - 4;
      if (received == expected) { queued = received; busy = true; received = expected = 0; }
    }
    xSemaphoreGive(guard);
  }
} writes;
class Connections : public NimBLEServerCallbacks {
  void onDisconnect(NimBLEServer *, NimBLEConnInfo &connection, int) override {
    xSemaphoreTake(guard, portMAX_DELAY);
    if (owner == connection.getConnHandle()) { received = expected = 0; owner = 0xffff; }
    xSemaphoreGive(guard);
    NimBLEDevice::startAdvertising();
  }
} connections;

bool decrypt(const uint8_t *packet, size_t length, JsonDocument &doc) {
  if (length < 131 || memcmp(packet, "BR1\0", 4) || memcmp(packet + 4, challenge, 32)) { reject("stale or invalid envelope"); return false; }
  size_t cipherSize = (packet[113] << 8) | packet[114], end = 115 + cipherSize;
  if (cipherSize < 16 || cipherSize > 528 || end >= length || length > end + 72) { reject("invalid length"); return false; }
  uint8_t digest[32];
  mbedtls_sha256_context sha; mbedtls_sha256_init(&sha);
  mbedtls_sha256_starts_ret(&sha, 0);
  mbedtls_sha256_update_ret(&sha, (const uint8_t *)DOMAIN, strlen(DOMAIN));
  mbedtls_sha256_update_ret(&sha, (const uint8_t *)BOARD_DEVICE_ID, strlen(BOARD_DEVICE_ID));
  mbedtls_sha256_update_ret(&sha, packet, end);
  mbedtls_sha256_finish_ret(&sha, digest); mbedtls_sha256_free(&sha);
  mbedtls_ecdsa_context signature; mbedtls_ecdsa_init(&signature);
  int ret = mbedtls_ecp_group_load(&signature.grp, MBEDTLS_ECP_DP_SECP256R1);
  if (!ret) ret = mbedtls_ecp_point_read_binary(&signature.grp, &signature.Q, senderPublic, 65);
  if (!ret) ret = mbedtls_ecdsa_read_signature(&signature, digest, 32, packet + end, length - end);
  mbedtls_ecdsa_free(&signature);
  if (ret) { reject("signature invalid"); return false; }
  mbedtls_ecp_group group; mbedtls_ecp_group_init(&group);
  mbedtls_ecp_point peer; mbedtls_ecp_point_init(&peer);
  mbedtls_mpi scalar, shared; mbedtls_mpi_init(&scalar); mbedtls_mpi_init(&shared);
  ret = mbedtls_ecp_group_load(&group, MBEDTLS_ECP_DP_SECP256R1);
  if (!ret) ret = mbedtls_mpi_read_binary(&scalar, privateKey, 32);
  if (!ret) ret = mbedtls_ecp_point_read_binary(&group, &peer, packet + 36, 65);
  if (!ret) ret = mbedtls_ecdh_compute_shared(&group, &shared, &peer, &scalar, randomBytes, nullptr);
  uint8_t secret[32]{};
  if (!ret) ret = mbedtls_mpi_write_binary(&shared, secret, 32);
  mbedtls_mpi_free(&scalar); mbedtls_mpi_free(&shared); mbedtls_ecp_point_free(&peer); mbedtls_ecp_group_free(&group);
  String info = String(DOMAIN) + BOARD_DEVICE_ID;
  // HKDF-SHA256, one 32-byte output block. Arduino's IDF build omits hkdf.c.
  uint8_t prk[32]{}, expand[64]{};
  const auto sha256 = mbedtls_md_info_from_type(MBEDTLS_MD_SHA256);
  if (!ret) ret = mbedtls_md_hmac(sha256, challenge, 32, secret, 32, prk);
  memcpy(expand, info.c_str(), info.length()); expand[info.length()] = 1;
  if (!ret) ret = mbedtls_md_hmac(sha256, prk, 32, expand, info.length() + 1, responseKey);
  memset(prk, 0, sizeof(prk));
  memset(secret, 0, sizeof(secret));
  String aad = String(DOMAIN) + " request" + BOARD_DEVICE_ID;
  uint8_t associated[128]; memcpy(associated, aad.c_str(), aad.length()); memcpy(associated + aad.length(), challenge, 32);
  uint8_t plain[513]{};
  mbedtls_gcm_context gcm; mbedtls_gcm_init(&gcm);
  if (!ret) ret = mbedtls_gcm_setkey(&gcm, MBEDTLS_CIPHER_ID_AES, responseKey, 256);
  if (!ret) ret = mbedtls_gcm_auth_decrypt(&gcm, cipherSize - 16, packet + 101, 12, associated, aad.length() + 32,
      packet + end - 16, 16, packet + 115, plain);
  mbedtls_gcm_free(&gcm);
  if (ret || deserializeJson(doc, plain, cipherSize - 16)) { memset(plain, 0, sizeof(plain)); reject("encrypted command invalid"); return false; }
  memset(plain, 0, sizeof(plain));
  responseRequest = doc["request_id"].as<String>();
  memcpy(responseChallenge, challenge, 32);
  newChallenge(); // Consume the challenge before any command changes state.
  return true;
}
void executeCommand(JsonDocument &doc) {
  String command = doc["command"].as<String>();
  if (responseRequest.length() != 16) { reply("invalid request ID"); return; }
  if (command == "status") reply();
  else if (command == "refresh") { refresh = true; reply(); }
  else if (command == "serial_download") { pauseUntil = millis() + 180000; reply(); }
  else if (command == "reboot") { restartAt = millis() + 1000; reply(); }
  else if (command == "wifi_set" || command == "wifi_reconnect") {
    if (command == "wifi_reconnect") {
      wifi_config_t saved{};
      if (esp_wifi_get_config(WIFI_IF_STA, &saved) != ESP_OK) { reply("cannot read saved Wi-Fi"); return; }
      doc["ssid"] = String((char *)saved.sta.ssid, strnlen((char *)saved.sta.ssid, sizeof(saved.sta.ssid)));
      doc["password"] = String((char *)saved.sta.password, strnlen((char *)saved.sta.password, sizeof(saved.sta.password)));
      memset(&saved, 0, sizeof(saved));
    }
    String ssid = doc["ssid"].as<String>(), password = doc["password"].as<String>();
    if (!doc["ssid"].is<const char *>() || !doc["password"].is<const char *>() || ssid.length() < 1 || ssid.length() > 32 ||
        (password.length() && (password.length() < 8 || password.length() > 63)) || strlen(ssid.c_str()) != ssid.length() || strlen(password.c_str()) != password.length()) {
      reply("invalid Wi-Fi credentials"); return;
    }
    if (esp_wifi_get_config(WIFI_IF_STA, &previousWifi) != ESP_OK || esp_wifi_set_storage(WIFI_STORAGE_RAM) != ESP_OK) {
      reply("cannot stage Wi-Fi configuration"); return;
    }
    WiFi.setAutoReconnect(false);
    wifiStartGeneration = ipGeneration.load();
    candidateSsid = ssid;
    WiFi.disconnect(false, false);
    WiFi.begin(ssid.c_str(), password.c_str());
    memset((void *)password.c_str(), 0, password.length());
    wifiStarted = millis(); wifiPending = true;
    Serial.println("BOARD:WIFI_TESTING");
  } else reply("unknown command");
}
void execute(const uint8_t *packet, size_t len) {
  responseViaSerial = false;
  JsonDocument doc;
  if (decrypt(packet, len, doc)) executeCommand(doc);
}
void serialCommand(const String &line) {
  JsonDocument doc;
  if (line.startsWith("BOARD:WIFI ")) {
    if (deserializeJson(doc, line.substring(11)) || !doc.is<JsonObject>()) {
      Serial.println("BOARD:ERROR invalid Wi-Fi JSON"); return;
    }
    doc["command"] = "wifi_set";
  } else if (line == "BOARD:WIFI_RECONNECT") doc["command"] = "wifi_reconnect";
  else if (line == "BOARD:STATUS") doc["command"] = "status";
  else { if (appSerialHandler) appSerialHandler(line); return; }
  if (!doc["request_id"].is<const char *>()) {
    uint8_t id[8]; esp_fill_random(id, sizeof(id)); doc["request_id"] = hex(id, sizeof(id));
  }
  const String id = doc["request_id"].as<String>();
  xSemaphoreTake(guard, portMAX_DELAY);
  bool occupied = busy.load();
  if (!occupied) { busy = true; received = expected = 0; }
  xSemaphoreGive(guard);
  if (occupied) {
    JsonDocument error; error["request_id"] = id; error["result"] = "error"; error["error"] = "another command is in progress";
    Serial.print("BOARD:RESULT "); serializeJson(error, Serial); Serial.println(); return;
  }
  responseViaSerial = true;
  responseRequest = id;
  executeCommand(doc);
}
}

namespace BoardRuntime {
void setSerialCommandHandler(void (*handler)(const String&)) { appSerialHandler = handler; }
void begin() {
  WiFi.mode(WIFI_STA);
  WiFi.onEvent([](WiFiEvent_t) { ++ipGeneration; }, ARDUINO_EVENT_WIFI_STA_GOT_IP);
  uint8_t mac[6]; esp_read_mac(mac, ESP_MAC_WIFI_STA);
  char actualId[13]; snprintf(actualId, sizeof(actualId), "%02x%02x%02x%02x%02x%02x", mac[0], mac[1], mac[2], mac[3], mac[4], mac[5]);
  if (strcmp(actualId, BOARD_DEVICE_ID)) { Serial.println("BOARD:ERROR firmware enrolled for a different board"); return; }
  guard = xSemaphoreCreateMutex();
  prefs.begin("toys-board", false);
  if (prefs.getBytesLength("private") == 32) prefs.getBytes("private", privateKey, 32);
  else { memcpy(privateKey, BOARD_DEVICE_PRIVATE, 32); prefs.putBytes("private", privateKey, 32); }
  if (prefs.getBytesLength("sender") == 65) prefs.getBytes("sender", senderPublic, 65);
  else { memcpy(senderPublic, BOARD_SENDER_PUBLIC, 65); prefs.putBytes("sender", senderPublic, 65); }
  mbedtls_ecp_group group; mbedtls_ecp_group_init(&group);
  mbedtls_mpi scalar; mbedtls_mpi_init(&scalar);
  mbedtls_ecp_point point; mbedtls_ecp_point_init(&point);
  size_t written = 0;
  int ret = mbedtls_ecp_group_load(&group, MBEDTLS_ECP_DP_SECP256R1);
  if (!ret) ret = mbedtls_mpi_read_binary(&scalar, privateKey, 32);
  if (!ret) ret = mbedtls_ecp_mul(&group, &point, &scalar, &group.G, randomBytes, nullptr);
  if (!ret) ret = mbedtls_ecp_point_write_binary(&group, &point, MBEDTLS_ECP_PF_UNCOMPRESSED, &written, publicKey, 65);
  mbedtls_ecp_point_free(&point); mbedtls_mpi_free(&scalar); mbedtls_ecp_group_free(&group);
  if (ret || written != 65 || memcmp(publicKey, BOARD_DEVICE_PUBLIC, 65)) { Serial.println("BOARD:ERROR identity mismatch"); return; }
  String name = String("Toys-") + String(BOARD_DEVICE_ID).substring(6);
  NimBLEDevice::init(name.c_str()); NimBLEDevice::setMTU(247);
  auto server = NimBLEDevice::createServer(); server->setCallbacks(&connections);
  auto service = server->createService(SERVICE);
  helloChar = service->createCharacteristic(HELLO, NIMBLE_PROPERTY::READ, 512);
  resultChar = service->createCharacteristic(RESULT, NIMBLE_PROPERTY::READ, 512);
  auto commandChar = service->createCharacteristic(COMMAND, NIMBLE_PROPERTY::WRITE, 244);
  commandChar->setCallbacks(&writes);
  newChallenge(); service->start();
  auto advert = NimBLEDevice::getAdvertising();
  advert->enableScanResponse(true); advert->addServiceUUID(SERVICE); advert->setName(name.c_str()); advert->start();
  ready = true;
  boardSerialCommandHandler() = serialCommand;
  WiFi.begin();
  Serial.println("HN:BOOT serial-update-v1");
  Serial.printf("BOARD:READY id=%s ble=%s\n", BOARD_DEVICE_ID, name.c_str());
}
void poll() {
  serviceSerialUpdate();
  if (!ready) return;
  uint8_t packet[768]; size_t len = 0;
  xSemaphoreTake(guard, portMAX_DELAY);
  if (queued) { len = queued; memcpy(packet, incoming, len); memset(incoming, 0, sizeof(incoming)); queued = 0; }
  xSemaphoreGive(guard);
  if (len) { execute(packet, len); memset(packet, 0, sizeof(packet)); }
  const bool candidateConnected = wifiPending && ipGeneration.load() != wifiStartGeneration &&
      WiFi.status() == WL_CONNECTED && WiFi.SSID() == candidateSsid;
  if (wifiPending && (candidateConnected || millis() - wifiStarted > 30000)) {
    const bool connected = candidateConnected;
    wifi_config_t accepted{};
    if (connected) esp_wifi_get_config(WIFI_IF_STA, &accepted);
    else WiFi.disconnect(false, false);
    esp_wifi_set_storage(WIFI_STORAGE_FLASH);
    const bool saved = esp_wifi_set_config(WIFI_IF_STA, connected ? &accepted : &previousWifi) == ESP_OK;
    if (!connected || !saved) { esp_wifi_set_config(WIFI_IF_STA, &previousWifi); esp_wifi_connect(); }
    WiFi.setAutoReconnect(true);
    wifiPending = false; wifiChanged = connected && saved;
    candidateSsid = "";
    memset(&previousWifi, 0, sizeof(previousWifi)); memset(&accepted, 0, sizeof(accepted));
    Serial.println(wifiChanged ? "BOARD:WIFI_SAVED" : "BOARD:WIFI_RESTORED");
    reply(wifiChanged ? nullptr : "new Wi-Fi failed; previous configuration restored");
  }
  if (!busy && millis() - challengeStarted > 120000) newChallenge();
  if (restartAt && int32_t(millis() - restartAt) >= 0) ESP.restart();
}
bool appPaused() { return wifiPending || (pauseUntil && int32_t(pauseUntil - millis()) > 0); }
bool takeRefresh() { bool result = refresh; refresh = false; return result; }
bool takeWifiChanged() { bool result = wifiChanged; wifiChanged = false; return result; }
}
