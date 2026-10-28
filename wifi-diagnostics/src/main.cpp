#include <BoardApp.h>
#include <ArduinoJson.h>
#include <WiFi.h>
#include <WiFiUdp.h>
#include <HTTPClient.h>
#include <esp_wifi.h>
#include <ping/ping_sock.h>
#include <mbedtls/base64.h>
#include <atomic>

namespace {
String pending;
uint32_t lastStatus = 0, lastProbe = 0, interval = 0;
std::atomic<uint32_t> disconnects{0}, reason{0};
std::atomic<uint32_t> associations{0}, gotIps{0};
void emit(JsonDocument &d) { d["ms"] = millis(); Serial.print("DIAG "); serializeJson(d, Serial); Serial.println(); }
void status() {
 JsonDocument d; d["type"]="status"; d["connected"]=WiFi.status()==WL_CONNECTED;
 d["ssid"]=WiFi.SSID(); d["bssid"]=WiFi.BSSIDstr(); d["rssi"]=WiFi.RSSI(); d["channel"]=WiFi.channel();
 d["ip"]=WiFi.localIP().toString(); d["gateway"]=WiFi.gatewayIP().toString(); d["mask"]=WiFi.subnetMask().toString();
 d["dns0"]=WiFi.dnsIP(0).toString(); d["dns1"]=WiFi.dnsIP(1).toString();
 wifi_ap_record_t ap{}; d["associated"]=esp_wifi_sta_get_ap_info(&ap)==ESP_OK;
 d["associations"]=associations.load(); d["got_ips"]=gotIps.load();
 d["disconnects"]=disconnects.load(); d["last_disconnect_reason"]=reason.load(); d["heap"]=ESP.getFreeHeap(); emit(d);
}
struct PingResult { std::atomic<bool> done{false}; uint32_t sent=0, replies=0, duration=0; };
void ping(IPAddress ip) {
 PingResult result; esp_ping_config_t cfg=ESP_PING_DEFAULT_CONFIG(); cfg.count=3; cfg.interval_ms=300; cfg.timeout_ms=1000;
 ipaddr_aton(ip.toString().c_str(), &cfg.target_addr);
 esp_ping_callbacks_t cb{}; cb.cb_args=&result;
 cb.on_ping_end=[](esp_ping_handle_t h, void *p) { auto *r=static_cast<PingResult*>(p);
 esp_ping_get_profile(h,ESP_PING_PROF_REQUEST,&r->sent,4); esp_ping_get_profile(h,ESP_PING_PROF_REPLY,&r->replies,4);
 esp_ping_get_profile(h,ESP_PING_PROF_DURATION,&r->duration,4); r->done=true; };
 esp_ping_handle_t h; int err=esp_ping_new_session(&cfg,&cb,&h);
 if (!err) { esp_ping_start(h); while(!result.done) delay(5); esp_ping_delete_session(h); }
 JsonDocument d; d["type"]="ping"; d["target"]=ip.toString(); d["sent"]=result.sent; d["replies"]=result.replies; d["duration_ms"]=result.duration; d["error"]=err; emit(d);
}
void tcp(IPAddress ip, int port) {
 WiFiClient c; uint32_t start=millis(); bool ok=c.connect(ip,port,2000); c.stop();
 JsonDocument d; d["type"]="tcp"; d["target"]=ip.toString(); d["port"]=port; d["ok"]=ok; d["duration_ms"]=millis()-start; emit(d);
}
void dns(IPAddress server) {
 WiFiUDP u; uint8_t q[512]={}; uint16_t id=esp_random(); q[0]=id>>8; q[1]=id; q[2]=1; q[5]=1;
 size_t n=12; const char *labels[]={"connectivitycheck","gstatic","com"};
 for(auto label:labels) { size_t len=strlen(label); q[n++]=len; memcpy(q+n,label,len); n+=len; }
 q[n++]=0; q[n++]=0; q[n++]=1; q[n++]=0; q[n++]=1;
 uint32_t start=millis(); bool ok=false; int rcode=-1, answers=0; String source;
 u.begin(0); u.beginPacket(server,53); u.write(q,n); u.endPacket();
 while(millis()-start<2500) { int size=u.parsePacket(); if(size) { IPAddress from=u.remoteIP(); int fromPort=u.remotePort(); int got=u.read(q,sizeof(q));
 if(got>=12 && from==server && fromPort==53 && q[0]==(id>>8) && q[1]==(id&255) && (q[2]&128)) { ok=true; rcode=q[3]&15; answers=(q[6]<<8)|q[7]; source=from.toString(); break; } } delay(5); }
 u.stop(); JsonDocument d; d["type"]="dns"; d["server"]=server.toString(); d["query"]="connectivitycheck.gstatic.com"; d["reply"]=ok; d["rcode"]=rcode; d["answers"]=answers; d["duration_ms"]=millis()-start; emit(d);
}
void fetch(const String &url, bool body, JsonDocument *request=nullptr) {
 JsonDocument d; d["type"]="http"; d["url"]=url;
 if(!url.startsWith("http://")) { d["error"]="only http URLs supported"; emit(d); return; }
 HTTPClient h; WiFiClient c; h.setConnectTimeout(2500); h.setTimeout(3000); const char *headers[]={"Location","WWW-Authenticate","Server"}; h.collectHeaders(headers,3);
 uint32_t start=millis(); h.begin(c,url);
 if(request) for(JsonPair kv:(*request)["headers"].as<JsonObject>()) h.addHeader(kv.key().c_str(),kv.value().as<String>());
 String method=request ? ((*request)["method"] | "GET") : "GET";
 String payload=request ? ((*request)["body"] | "") : "";
 int code=h.sendRequest(method.c_str(),payload); d["code"]=code; d["duration_ms"]=millis()-start; d["length"]=h.getSize();
 d["location"]=h.header("Location"); d["authenticate"]=h.header("WWW-Authenticate"); d["server"]=h.header("Server"); emit(d);
 if(body && code>0) { uint32_t bytes=0, idle=millis(); int remaining=h.getSize(); auto *stream=h.getStreamPtr();
 while((h.connected() || stream->available()) && remaining!=0 && bytes<65536 && millis()-idle<3000) {
 int avail=stream->available(); if(avail) { uint8_t buf[384]; int want=std::min(avail,384); if(remaining>0) want=std::min(want,remaining); int got=stream->readBytes(buf,want);
 unsigned char encoded[513]; size_t out; mbedtls_base64_encode(encoded,sizeof(encoded),&out,buf,got);
 JsonDocument chunk; chunk["type"]="body"; chunk["base64"]=String((char*)encoded,out); emit(chunk); bytes+=got; if(remaining>0) remaining-=got; idle=millis(); } else delay(5); }
 JsonDocument end; end["type"]="body_end"; end["bytes"]=bytes; end["truncated"]=remaining!=0; emit(end); }
 h.end();
}
void probe() { status(); if(WiFi.status()!=WL_CONNECTED) return; ping(WiFi.gatewayIP()); ping(IPAddress(1,1,1,1)); tcp(IPAddress(1,1,1,1),443); tcp(IPAddress(8,8,8,8),53); dns(WiFi.dnsIP()); dns(IPAddress(1,1,1,1)); dns(IPAddress(8,8,8,8)); fetch("http://connectivitycheck.gstatic.com/generate_204",false); fetch("http://www.msftconnecttest.com/connecttest.txt",false); }
void command(const String &line) { if(line=="DIAG:STATUS") { status(); JsonDocument d; d["type"]="done"; d["command"]=line; emit(d); }
 else if(line.startsWith("DIAG:")) { if(pending.length()) Serial.println("DIAG:ERROR busy"); else pending=line; } }
}
void appSetup() {
 BoardRuntime::setSerialCommandHandler(command);
 WiFi.onEvent([](WiFiEvent_t event, WiFiEventInfo_t info) { if(event==ARDUINO_EVENT_WIFI_STA_DISCONNECTED) { ++disconnects; reason=info.wifi_sta_disconnected.reason; }
 if(event==ARDUINO_EVENT_WIFI_STA_CONNECTED) ++associations;
 if(event==ARDUINO_EVENT_WIFI_STA_GOT_IP) ++gotIps; });
 M5.Display.fillScreen(TFT_BLACK); M5.Display.setTextSize(2); M5.Display.println("Wi-Fi diagnostics\nUSB commands ready"); Serial.println("DIAG:READY");
}
void appLoop() {
 if(millis()-lastStatus>10000) { status(); lastStatus=millis(); }
 if(pending.length()) { String cmd=pending; pending="";
 if(cmd=="DIAG:STATUS") status();
 else if(cmd=="DIAG:PROBE") probe();
 else if(cmd=="DIAG:SCAN") { int count=WiFi.scanNetworks(); JsonDocument d; d["type"]="scan"; auto a=d["networks"].to<JsonArray>(); for(int i=0;i<count;i++) { auto n=a.add<JsonObject>(); n["ssid"]=WiFi.SSID(i); n["bssid"]=WiFi.BSSIDstr(i); n["rssi"]=WiFi.RSSI(i); n["channel"]=WiFi.channel(i); } emit(d); WiFi.scanDelete(); }
 else if(cmd.startsWith("DIAG:FETCH ")) fetch(cmd.substring(11),true);
 else if(cmd.startsWith("DIAG:REQUEST ")) { JsonDocument r; if(!deserializeJson(r,cmd.substring(13))) fetch(r["url"].as<String>(),true,&r); cmd="DIAG:REQUEST"; }
 else if(cmd.startsWith("DIAG:STATIC ")) { JsonDocument r; if(!deserializeJson(r,cmd.substring(12))) {
 IPAddress ip,gw,mask,dnsip; ip.fromString(r["ip"] | "0.0.0.0"); gw.fromString(r["gateway"] | "0.0.0.0"); mask.fromString(r["mask"] | "255.255.255.0"); dnsip.fromString(r["dns"] | "0.0.0.0");
 WiFi.config(ip,gw,mask,dnsip); } }
 else if(cmd=="DIAG:DHCP") WiFi.config(IPAddress(0,0,0,0),IPAddress(0,0,0,0),IPAddress(0,0,0,0));
 else if(cmd.startsWith("DIAG:MONITOR ")) { interval=cmd.substring(13).toInt()*1000; if(interval && interval<30000) interval=30000; lastProbe=millis(); }
 else if(cmd=="DIAG:POWERSAVE OFF") WiFi.setSleep(false);
 else if(cmd=="DIAG:POWERSAVE ON") WiFi.setSleep(true);
 JsonDocument d; d["type"]="done"; d["command"]=cmd; emit(d);
 }
 if(interval && millis()-lastProbe>=interval) { probe(); lastProbe=millis(); }
 if(M5.BtnA.wasPressed()) pending="DIAG:PROBE";
}
