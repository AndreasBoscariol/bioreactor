#include <ArduinoJson.h>
#include <SPI.h>
#include <Adafruit_MAX31855.h>
#include <math.h>

/* ---- pin map ---- */
const uint8_t PUMP1_IN1 = 2;
const uint8_t PUMP1_IN2 = 3;
const uint8_t PUMP2_IN1 = 4;
const uint8_t PUMP2_IN2 = 5;

// relays (active‑low board)
const uint8_t RELAY_HEATER   = 10;  // R1
const uint8_t RELAY_STIR     = 11;  // R2
const uint8_t RELAY_LIGHTS   = 12;  // R3
const uint8_t RELAY_AERATOR  = 13;  // R4

const uint8_t IR_LED_PIN  = A2;
const uint8_t PHOTO1_PIN  = A0;
const uint8_t PHOTO2_PIN  = A1;

/* ---- thermocouples on SPI ---- */
const uint8_t TC1_CS = 8;
const uint8_t TC2_CS = 9;
Adafruit_MAX31855 tc1(TC1_CS);
Adafruit_MAX31855 tc2(TC2_CS);

/* ---- state (explicitly initialized) ---- */
bool heater  = false,
     aerator = false,
     lights  = false,
     stir    = false;
bool pump1   = false,
     pump2   = false,
     irled   = false;

void setup() {
  // relays
  pinMode(RELAY_HEATER,  OUTPUT);
  pinMode(RELAY_AERATOR, OUTPUT);
  pinMode(RELAY_LIGHTS,  OUTPUT);
  pinMode(RELAY_STIR,    OUTPUT);

  // pumps
  pinMode(PUMP1_IN1, OUTPUT);  pinMode(PUMP1_IN2, OUTPUT);
  pinMode(PUMP2_IN1, OUTPUT);  pinMode(PUMP2_IN2, OUTPUT);

  // IR LED & sensors
  pinMode(IR_LED_PIN, OUTPUT);
  pinMode(PHOTO1_PIN, INPUT);
  pinMode(PHOTO2_PIN, INPUT);

  // defaults: relays OFF (HIGH), pumps OFF, IR OFF
  digitalWrite(RELAY_HEATER,  HIGH);
  digitalWrite(RELAY_AERATOR, HIGH);
  digitalWrite(RELAY_LIGHTS,  HIGH);
  digitalWrite(RELAY_STIR,    HIGH);
  digitalWrite(PUMP1_IN1, LOW);  digitalWrite(PUMP1_IN2, LOW);
  digitalWrite(PUMP2_IN1, LOW);  digitalWrite(PUMP2_IN2, LOW);
  digitalWrite(IR_LED_PIN, LOW);

  SPI.begin();
  Serial.begin(115200);
}

void setRelay(uint8_t pin, bool on) {
  digitalWrite(pin, on ? LOW : HIGH);
}
void setPump(uint8_t in1, uint8_t in2, bool on) {
  digitalWrite(in1, on);
  digitalWrite(in2, LOW);
}

void loop() {
  // —— inbound JSON ——
  if (Serial.available()) {
    StaticJsonDocument<128> doc;
    if (!deserializeJson(doc, Serial)) {
      if (doc["cmd"] == F("set")) {
        if (doc.containsKey("heater"))  heater  = doc["heater"];
        if (doc.containsKey("aerator")) aerator = doc["aerator"];
        if (doc.containsKey("lights"))  lights  = doc["lights"];
        if (doc.containsKey("stir"))    stir    = doc["stir"];
        if (doc.containsKey("pump1"))   pump1   = doc["pump1"];
        if (doc.containsKey("pump2"))   pump2   = doc["pump2"];
        if (doc.containsKey("irled"))   irled   = doc["irled"];
      }
    }
  }

  // —— apply outputs ——
  setRelay(RELAY_HEATER,  heater);
  setRelay(RELAY_AERATOR, aerator);
  setRelay(RELAY_LIGHTS,  lights);
  setRelay(RELAY_STIR,    stir);
  setPump(PUMP1_IN1, PUMP1_IN2, pump1);
  setPump(PUMP2_IN1, PUMP2_IN2, pump2);
  digitalWrite(IR_LED_PIN, irled);

  // —— read sensors & send JSON ——
  float t1 = tc1.readCelsius();
  float t2 = tc2.readCelsius();

  // clamp photodiode floats: if out of [0–1023], zero it
  int raw1 = analogRead(PHOTO1_PIN);
  int raw2 = analogRead(PHOTO2_PIN);
  raw1 = (raw1 >= 0 && raw1 <= 1023) ? raw1 : 0;
  raw2 = (raw2 >= 0 && raw2 <= 1023) ? raw2 : 0;

  StaticJsonDocument<128> out;
  out["t1"]      = isnan(t1) ? nullptr : t1;
  out["t2"]      = isnan(t2) ? nullptr : t2;
  out["l1"]      = raw1;
  out["l2"]      = raw2;
  out["heater"]  = heater;
  out["aerator"] = aerator;
  out["lights"]  = lights;
  out["stir"]    = stir;
  out["pump1"]   = pump1;
  out["pump2"]   = pump2;
  out["irled"]   = irled;

  serializeJson(out, Serial);
  Serial.println();

  delay(200);  // 5 Hz
}
