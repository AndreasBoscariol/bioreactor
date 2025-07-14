 #include <ArduinoJson.h>
 #include <SPI.h>
 #include <Adafruit_MAX31855.h>
 
 /* ---- pin map ---- */
 const uint8_t PUMP1_IN1 = 2;
 const uint8_t PUMP1_IN2 = 3;
 const uint8_t PUMP2_IN1 = 4;
 const uint8_t PUMP2_IN2 = 5;
 
 const uint8_t RELAY_HEATER = 1;
 const uint8_t RELAY_STIR   = 2;
 const uint8_t RELAY_AERATOR = 4;
 const uint8_t RELAY_LIGHTS = 3;
 

 
 const uint8_t IR_LED_PIN = 10;
 
 const uint8_t PHOTO1_PIN = A0;
 const uint8_t PHOTO2_PIN = A1;
 
 /* ---- thermocouples on SPI ---- */
 const uint8_t TC1_CS = 11;
 const uint8_t TC2_CS = 12;
 Adafruit_MAX31855 tc1(TC1_CS);
 Adafruit_MAX31855 tc2(TC2_CS);
 
 /* ---- state ---- */
 bool heater, aerator, lights, stir;
 bool pump1, pump2, irled;
 
 void setup() {
   pinMode(RELAY_HEATER, OUTPUT);
   pinMode(RELAY_AERATOR, OUTPUT);
   pinMode(RELAY_LIGHTS, OUTPUT);
   pinMode(RELAY_STIR, OUTPUT);
 
   pinMode(PUMP1_IN1, OUTPUT); pinMode(PUMP1_IN2, OUTPUT);
   pinMode(PUMP2_IN1, OUTPUT); pinMode(PUMP2_IN2, OUTPUT);
 
   pinMode(IR_LED_PIN, OUTPUT);
 
   digitalWrite(RELAY_HEATER, HIGH);   // relays off (active-low board)
   digitalWrite(RELAY_AERATOR, HIGH);
   digitalWrite(RELAY_LIGHTS, HIGH);
   digitalWrite(RELAY_STIR, HIGH);
   digitalWrite(IR_LED_PIN, LOW);
 
   SPI.begin();
   Serial.begin(115200);
 }
 
 void setRelay(uint8_t pin, bool on) { digitalWrite(pin, on ? LOW : HIGH); }
 void setPump(uint8_t in1, uint8_t in2, bool on) {
   digitalWrite(in1, on); digitalWrite(in2, LOW);   // one-direction
 }
 
 void loop() {
   /* ---------- inbound ---------- */
   if (Serial.available()) {
     StaticJsonDocument<128> doc;
     DeserializationError err = deserializeJson(doc, Serial);
     if (!err && doc["cmd"] == "set") {
       heater  = doc["heater"]  | heater;
       aerator = doc["aerator"] | aerator;
       lights  = doc["lights"]  | lights;
       stir    = doc["stir"]    | stir;
       pump1   = doc["pump1"]   | pump1;
       pump2   = doc["pump2"]   | pump2;
       irled   = doc["irled"]   | irled;
     }
   }
 
   /* update outputs */
   setRelay(RELAY_HEATER, heater);
   setRelay(RELAY_AERATOR, aerator);
   setRelay(RELAY_LIGHTS, lights);
   setRelay(RELAY_STIR,   stir);
   setPump(PUMP1_IN1, PUMP1_IN2, pump1);
   setPump(PUMP2_IN1, PUMP2_IN2, pump2);
   digitalWrite(IR_LED_PIN, irled);
 
   /* ---------- outbound ---------- */
   StaticJsonDocument<128> out;
   out["t1"] = tc1.readCelsius();
   out["t2"] = tc2.readCelsius();
   out["l1"] = analogRead(PHOTO1_PIN);
   out["l2"] = analogRead(PHOTO2_PIN);
   out["heater"] = heater;
   out["aerator"] = aerator;
   out["lights"] = lights;
   out["stir"]   = stir;
   out["pump1"]  = pump1;
   out["pump2"]  = pump2;
   out["irled"]  = irled;
   serializeJson(out, Serial);
   Serial.println();
 
   delay(200);   // 5 Hz update
 }
 