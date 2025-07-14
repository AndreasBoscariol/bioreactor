/*
 * Bio‑reactor control firmware
 * – 2 × DS18B20 on 1‑Wire bus (pin 8)  → t1 / t2
 * – 2 × photodiodes on A0 / A1        → l1 / l2
 * – 4 × relays (heater, stir, lights, aerator)
 * – 2 × pumps, 1 × IR LED
 * JSON over Serial @115 200 baud
 *
 * Wire both DS18B20 data pins to D8 with a 4.7 kΩ pull‑up to 5 V (or 3 V).
 */

 #include <ArduinoJson.h>
 #include <OneWire.h>
 #include <DallasTemperature.h>
 
 /* ── pin map ───────────────────────────────────────── */
 const uint8_t ONE_WIRE_PIN = 8;     // DS18B20 data (shared bus)
 const uint8_t PUMP1_IN1    = 2;
 const uint8_t PUMP1_IN2    = 3;
 const uint8_t PUMP2_IN1    = 4;
 const uint8_t PUMP2_IN2    = 5;
 
 // relays (active‑low)
 const uint8_t RELAY_HEATER  = 10;   // R1
 const uint8_t RELAY_STIR    = 11;   // R2
 const uint8_t RELAY_LIGHTS  = 12;   // R3
 const uint8_t RELAY_AERATOR = 13;   // R4
 
 const uint8_t IR_LED_PIN  = A2;
 const uint8_t PHOTO1_PIN  = A0;
 const uint8_t PHOTO2_PIN  = A1;
 
 /* ── DS18B20 setup ────────────────────────────────── */
 OneWire        oneWire(ONE_WIRE_PIN);
 DallasTemperature sensors(&oneWire);
 
 /* ── state ─────────────────────────────────────────── */
 bool heater=false, aerator=false, lights=false, stir=false;
 bool pump1=false,  pump2=false,   irled=false;
 
 void setup() {
   /* outputs */
   pinMode(RELAY_HEATER,  OUTPUT);
   pinMode(RELAY_STIR,    OUTPUT);
   pinMode(RELAY_LIGHTS,  OUTPUT);
   pinMode(RELAY_AERATOR, OUTPUT);
 
   pinMode(PUMP1_IN1, OUTPUT);  pinMode(PUMP1_IN2, OUTPUT);
   pinMode(PUMP2_IN1, OUTPUT);  pinMode(PUMP2_IN2, OUTPUT);
   pinMode(IR_LED_PIN, OUTPUT);
 
   /* default OFF (relays are active‑LOW) */
   digitalWrite(RELAY_HEATER,  HIGH);
   digitalWrite(RELAY_STIR,    HIGH);
   digitalWrite(RELAY_LIGHTS,  HIGH);
   digitalWrite(RELAY_AERATOR, HIGH);
   digitalWrite(IR_LED_PIN,    LOW);
 
   /* sensors */
   sensors.begin();            // start DS18B20 bus
   Serial.begin(115200);
 }
 
 inline void setRelay(uint8_t pin, bool on)  { digitalWrite(pin, on ? LOW : HIGH); }
 inline void setPump (uint8_t in1,uint8_t in2,bool on){ digitalWrite(in1,on); digitalWrite(in2,LOW); }
 
 void loop() {
   /* ── inbound commands ── */
   if (Serial.available()) {
     StaticJsonDocument<128> doc;
     if (!deserializeJson(doc, Serial) && doc["cmd"] == "set") {
       if (doc.containsKey("heater"))  heater  = doc["heater"];
       if (doc.containsKey("stir"))    stir    = doc["stir"];
       if (doc.containsKey("lights"))  lights  = doc["lights"];
       if (doc.containsKey("aerator")) aerator = doc["aerator"];
       if (doc.containsKey("pump1"))   pump1   = doc["pump1"];
       if (doc.containsKey("pump2"))   pump2   = doc["pump2"];
       if (doc.containsKey("irled"))   irled   = doc["irled"];
     }
   }
 
   /* ── apply outputs ── */
   setRelay(RELAY_HEATER,  heater);
   setRelay(RELAY_STIR,    stir);
   setRelay(RELAY_LIGHTS,  lights);
   setRelay(RELAY_AERATOR, aerator);
   setPump (PUMP1_IN1, PUMP1_IN2, pump1);
   setPump (PUMP2_IN1, PUMP2_IN2, pump2);
   digitalWrite(IR_LED_PIN, irled);
 
   /* ── read sensors ── */
   sensors.requestTemperatures();           // non‑blocking for small sensor count
   float t1 = sensors.getTempCByIndex(0);
   float t2 = sensors.getTempCByIndex(1);
 
   int l1 = analogRead(PHOTO1_PIN);
   int l2 = analogRead(PHOTO2_PIN);
 
   /* ── JSON back to Pi ── */
   StaticJsonDocument<128> out;
   out["t1"]      = (t1 == DEVICE_DISCONNECTED_C) ? nullptr : t1;
   out["t2"]      = (t2 == DEVICE_DISCONNECTED_C) ? nullptr : t2;
   out["l1"]      = l1;
   out["l2"]      = l2;
   out["heater"]  = heater;
   out["stir"]    = stir;
   out["lights"]  = lights;
   out["aerator"] = aerator;
   out["pump1"]   = pump1;
   out["pump2"]   = pump2;
   out["irled"]   = irled;
 
   serializeJson(out, Serial);
   Serial.println();
 
   delay(200);      // 5 Hz update rate
 }
 