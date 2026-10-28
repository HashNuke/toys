#include <BoardApp.h>
#include "SerialUpdate.h"

#ifndef HN_BOOTSTRAP
#include <WiFi.h>
#include <WiFiClientSecure.h>
#include <HTTPClient.h>
#include <ArduinoJson.h>
#include <time.h>
#include "TrustRoots.h"

struct Story { String title; unsigned id = 0; int score = 0; int comments = 0; };
Story stories[5];
bool haveStories = false;
bool wasConnected = false;
bool readingStory = false;
int selected = 0;
int detailPage = 0;
uint32_t lastAttempt = 0;
uint32_t lastSuccess = 0;
bool refreshRequested = true;
String status = "Connecting...";
constexpr uint16_t BG = 0x1082;
constexpr uint16_t HN_ACCENT = 0xFBE0;

void text(int x, int y, const String &value, uint16_t color = TFT_WHITE) {
  M5.Display.setTextColor(color, BG);
  M5.Display.setCursor(x, y);
  M5.Display.print(value);
}

// Wrap at word boundaries and retain the complete headline for detail pages.
int wrap(const String &value, String *lines, int maxLines, int width) {
  String remaining = value;
  int count = 0;
  while (remaining.length() && count < maxLines) {
    int end = remaining.length();
    while (end > 1 && M5.Display.textWidth(remaining.substring(0, end)) > width) --end;
    if (end < int(remaining.length())) {
      int space = remaining.lastIndexOf(' ', end);
      if (space > 0) end = space;
    }
    lines[count++] = remaining.substring(0, end);
    remaining = remaining.substring(end);
    remaining.trim();
  }
  return count;
}

void draw() {
  M5.Display.fillScreen(BG);
  M5.Display.setFont(&fonts::Font2);
  M5.Display.setTextSize(1);
  M5.Display.fillRect(0, 0, 320, 30, HN_ACCENT);
  M5.Display.setTextColor(TFT_BLACK, HN_ACCENT);
  M5.Display.setCursor(10, 6);
  M5.Display.print("HACKER NEWS   /   TOP 5");
  if (!haveStories) {
    text(12, 52, status);
    if (WiFi.status() != WL_CONNECTED) {
      text(12, 88, "Wi-Fi setup via USB", HN_ACCENT);
      text(12, 112, "Connect to your computer.");
      text(12, 140, "Run the Wi-Fi setup tool.");
      text(12, 166, "Saved Wi-Fi reconnects at boot.");
    }
  } else if (!readingStory) {
    for (int i = 0; i < 5; ++i) {
      int y = 34 + i * 35;
      text(7, y, String(i + 1), i == selected ? HN_ACCENT : TFT_LIGHTGREY);
      String lines[16];
      int count = wrap(stories[i].title, lines, 16, 286);
      text(26, y, count ? lines[0] : "Unavailable");
      if (count > 1) {
        String second = lines[1];
        if (count > 2) {
          while (second.length() && M5.Display.textWidth(second + "...") > 286)
            second.remove(second.length() - 1);
          second += "...";
        }
        text(26, y + 16, second);
      }
    }
    M5.Display.setFont(&fonts::Font0);
    String label = status;
    if (status == "Live") label = "Updated " + String((millis() - lastSuccess) / 60000) + "m ago | auto: 5m";
    text(8, 213, label, TFT_LIGHTGREY);
  } else {
    text(12, 40, "#" + String(selected + 1) + "    " + String(stories[selected].score) + " points    " + String(stories[selected].comments) + " comments", HN_ACCENT);
    String lines[32];
    int count = wrap(stories[selected].title, lines, 32, 296);
    for (int i = 0; i < 7 && detailPage * 7 + i < count; ++i)
      text(12, 70 + i * 18, lines[detailPage * 7 + i]);
    M5.Display.setFont(&fonts::Font0);
    text(12, 207, "news.ycombinator.com/item?id=" + String(stories[selected].id), TFT_LIGHTGREY);
  }
  M5.Display.setFont(&fonts::Font0);
  M5.Display.drawFastHLine(0, 226, 320, TFT_DARKGREY);
  text(12, 232, readingStory ? "A:back       B:next       C:page" : "A:refresh    B:read       C:select", HN_ACCENT);
}

bool getJson(const String &path, JsonDocument &doc, bool item = false) {
  WiFiClientSecure client;
  client.setCACert(HN_ROOTS);
  client.setHandshakeTimeout(10);
  HTTPClient http;
  http.setConnectTimeout(8000);
  http.setTimeout(8000);
  if (!http.begin(client, "https://hacker-news.firebaseio.com/v0/" + path + ".json")) return false;
  const int code = http.GET();
  if (code != HTTP_CODE_OK) {
    Serial.printf("HN:HTTP error %d\n", code);
    http.end();
    return false;
  }
  String body = http.getString();
  http.end();
  DeserializationError error;
  if (item) {
    JsonDocument filter;
    for (const char *key : {"id", "title", "score", "descendants", "dead", "deleted"}) filter[key] = true;
    error = deserializeJson(doc, body, DeserializationOption::Filter(filter));
  } else error = deserializeJson(doc, body);
  return !error;
}

void fetchNews() {
  lastAttempt = millis();
  refreshRequested = false;
  if (WiFi.status() != WL_CONNECTED) { status = "Offline - reconnecting"; draw(); return; }
  if (time(nullptr) < 1700000000) { status = "Synchronizing clock..."; draw(); return; }
  status = "Refreshing...";
  draw();
  JsonDocument top;
  if (!getJson("topstories", top) || !top.is<JsonArray>() || top.size() < 5) {
    status = haveStories ? "Refresh failed - showing previous stories" : "Fetch failed - retrying in 30s";
    draw();
    return;
  }
  Story next[5];
  for (int i = 0; i < 5; ++i) {
    serviceSerialUpdate();
    JsonDocument item;
    unsigned id = top[i].as<unsigned>();
    if (!id || !getJson("item/" + String(id), item, true) || !item["title"].is<const char *>() || item["dead"].as<bool>() || item["deleted"].as<bool>()) {
      status = haveStories ? "Refresh failed - showing previous stories" : "Story unavailable - retrying in 30s";
      draw();
      return;
    }
    next[i].id = id;
    next[i].title = item["title"].as<String>();
    next[i].title.replace("&amp;", "&");
    next[i].title.replace("&#x27;", "'");
    next[i].title.replace("&quot;", "\"");
    next[i].title.replace("&lt;", "<");
    next[i].title.replace("&gt;", ">");
    next[i].score = item["score"] | 0;
    next[i].comments = item["descendants"] | 0;
  }
  for (int i = 0; i < 5; ++i) {
    stories[i] = next[i];
    Serial.printf("HN:STORY %d %u %s\n", i + 1, stories[i].id, stories[i].title.c_str());
  }
  haveStories = true;
  lastSuccess = millis();
  status = "Live";
  detailPage = 0;
  draw();
  Serial.printf("HN:FETCH_OK count=5 ip=%s\n", WiFi.localIP().toString().c_str());
}
#endif

void appSetup() {
#ifdef HN_BOOTSTRAP
  M5.Display.fillScreen(TFT_BLACK);
  M5.Display.setTextSize(2);
  M5.Display.setCursor(12, 30);
  M5.Display.println("Serial update ready");
  M5.Display.setCursor(12, 80);
  M5.Display.println("Waiting for news app.");
#else
  WiFi.setAutoReconnect(true);
  draw();
  // BoardRuntime connects using saved credentials and handles USB/BLE setup.
  configTime(0, 0, "pool.ntp.org", "time.google.com");
#endif
}

void appLoop() {
#ifndef HN_BOOTSTRAP
  if (BoardRuntime::takeRefresh()) refreshRequested = true;
  if (BoardRuntime::takeWifiChanged()) {
    refreshRequested = true;
  }
  bool connected = WiFi.status() == WL_CONNECTED;
  if (connected && !wasConnected) {
    Serial.printf("HN:WIFI_CONNECTED ip=%s\n", WiFi.localIP().toString().c_str());
    refreshRequested = true;
    status = "Synchronizing clock...";
    draw();
  }
  if (!connected && wasConnected) { status = "Offline - reconnecting"; draw(); }
  wasConnected = connected;
  if (connected && status == "Synchronizing clock..." && time(nullptr) >= 1700000000)
    refreshRequested = true;
  if (M5.BtnA.wasPressed()) {
    if (readingStory) { readingStory = false; draw(); }
    else refreshRequested = true;
  }
  if (M5.BtnB.wasPressed() && haveStories) {
    if (readingStory) selected = (selected + 1) % 5;
    readingStory = true;
    detailPage = 0;
    draw();
  }
  if (M5.BtnC.wasPressed() && haveStories) {
    if (readingStory) {
      M5.Display.setFont(&fonts::Font2);
      String lines[32];
      int count = wrap(stories[selected].title, lines, 32, 296);
      detailPage = (detailPage + 1) % max(1, (count + 6) / 7);
    } else selected = (selected + 1) % 5;
    draw();
  }
  if (connected && (refreshRequested || millis() - lastAttempt >= (status == "Live" ? 300000UL : 30000UL))) fetchNews();
  static uint32_t lastDraw = 0;
  if (haveStories && millis() - lastDraw >= 60000) { lastDraw = millis(); draw(); }
#endif
  delay(5);
}
