# bioreactor_controller.py

import json
import time
import queue
import datetime
import threading
import math
import csv
import pathlib

import serial
from config import *

def _format_seconds_to_hm(seconds):
    if seconds is None or seconds < 0: return "--"
    hours = int(seconds // 3600); minutes = int((seconds % 3600) // 60)
    return f"{hours}h {minutes}m"

class BioreactorController(threading.Thread):
    def __init__(self):
        super().__init__(daemon=True)
        try:
            self._serial_lock = threading.Lock()
            self.ser = serial.Serial(SERIAL_PORT, BAUD, timeout=2)
        except serial.SerialException as e:
            print(f"FATAL: Could not open serial port {SERIAL_PORT}: {e}"); exit(1)
        
        self.out_q = queue.Queue(); self._csv_lock = threading.Lock()
        self.automation_lock = threading.Lock(); LOG_DIR.mkdir(exist_ok=True)

        self.HISTORY_MAX_LENGTH = 2000
        self.history = { "t1": [], "t2": [], "od": [] }

        self.latest_readings = {
            "t1": None, "t2": None, "l1": None, "l2": None, "od": None,
            "od_for_graph": None, "heater": 0, "stir": 0, "lights": 0, "aerator": 0,
            "pump1": 0, "pump2": 0, "irled": 0, "light_cycle_status": "--",
            "dilution_status": "--", "od_status": "--", "aerator_status": "--",
            "od_sequence_step": None, "last_od_reading_ago": "No measurements taken yet"
        }
        self.setpoints = {
            'temperature': 25.0, 'light_cycle_hours': 12, 'dilution_percent': 15.0,
            'od_interval_hours': 4.0, 'aerator_interval_hours': 2.0
        }
        self.manual_overrides = {k: False for k in self.latest_readings}
        now = time.time()
        initial_od_interval_seconds = self.setpoints['od_interval_hours'] * 3600
        initial_aerator_interval_seconds = self.setpoints['aerator_interval_hours'] * 3600
        self.schedule = {
            'next_od_reading_time': now + initial_od_interval_seconds,
            'next_aeration_time': now + initial_aerator_interval_seconds,
            'light_cycle_start_time': now, 'last_od_reading_timestamp': None,
            'last_dilution_time': now # Tracks the last time a dilution was run
        }

    def _init_csv(self, path):
        # ... (This method is unchanged)
        if not path.exists():
            with path.open("w", newline="") as f:
                csv.writer(f).writerow(["timestamp_utc", "t1", "t2", "l1", "l2", "od"])

    def run(self):
        print("Bioreactor Controller thread started.")
        while True:
            with self._serial_lock: self._process_serial_inbound()
            self._process_serial_outbound()
            self._handle_temperature_control(); self._handle_light_cycle()
            self._handle_dilution_schedule(); self._handle_od_schedule()
            self._handle_aerator_schedule(); self._update_status_strings()
            time.sleep(0.1)

    def _is_light_cycle_on(self):
        """Helper function to determine if the light cycle is currently active."""
        cycle_duration = self.setpoints['light_cycle_hours'] * 3600
        if cycle_duration <= 0: return False
        if cycle_duration >= 86400: return True
        time_in_day = (time.time() - self.schedule['light_cycle_start_time']) % 86400
        return 0 < time_in_day < cycle_duration

    def _update_status_strings(self):
        now = time.time()
        # --- Dilution Status Update ---
        dilution_rate = self.setpoints['dilution_percent']
        if dilution_rate <= 0:
            self.latest_readings['dilution_status'] = "pumping is disabled"
        elif not self._is_light_cycle_on():
            self.latest_readings['dilution_status'] = f"Paused until light cycle begins"
        else:
            light_cycle_sec = self.setpoints['light_cycle_hours'] * 3600
            interval_sec = light_cycle_sec / DILUTIONS_PER_DAY if DILUTIONS_PER_DAY > 0 else 0
            time_since_last = now - self.schedule['last_dilution_time']
            time_to_next = interval_sec - time_since_last
            self.latest_readings['dilution_status'] = f"{DILUTIONS_PER_DAY} dilutions per light cycle. Next in {_format_seconds_to_hm(time_to_next)}"

        # ... (The rest of this method is unchanged)
        cycle_duration = self.setpoints['light_cycle_hours'] * 3600
        if cycle_duration <= 0: self.latest_readings['light_cycle_status'] = "lights are off"
        elif cycle_duration >= 86400: self.latest_readings['light_cycle_status'] = "lights are on"
        else:
            time_in_day = (now - self.schedule['light_cycle_start_time']) % 86400
            if time_in_day < cycle_duration: self.latest_readings['light_cycle_status'] = f"off in {_format_seconds_to_hm(cycle_duration - time_in_day)}"
            else: self.latest_readings['light_cycle_status'] = f"on in {_format_seconds_to_hm(86400 - time_in_day)}"
        time_to_next_od = self.schedule['next_od_reading_time'] - now
        self.latest_readings['od_status'] = f"measuring again in {_format_seconds_to_hm(time_to_next_od)}" if self.setpoints['od_interval_hours'] > 0 else "automatic measurement off"
        time_to_next_aeration = self.schedule['next_aeration_time'] - now
        self.latest_readings['aerator_status'] = f"aerating again in {_format_seconds_to_hm(time_to_next_aeration)}" if self.setpoints['aerator_interval_hours'] > 0 else "automatic aeration off"
        if self.schedule['last_od_reading_timestamp']:
            seconds_ago = now - self.schedule['last_od_reading_timestamp']
            self.latest_readings['last_od_reading_ago'] = f"Last measured {_format_seconds_to_hm(seconds_ago)} ago"
        else: self.latest_readings['last_od_reading_ago'] = "No measurements taken yet"

    # --- NEW: Dilution Logic ---
    def _handle_dilution_schedule(self):
        # 1. Check if dilution is enabled and the light cycle is currently ON
        if self.setpoints['dilution_percent'] <= 0: return
        if not self._is_light_cycle_on(): return
        
        # 2. Calculate the interval between dilutions within the light cycle
        light_cycle_duration_sec = self.setpoints['light_cycle_hours'] * 3600
        if light_cycle_duration_sec <= 0 or DILUTIONS_PER_DAY <= 0: return
        
        interval_seconds = light_cycle_duration_sec / DILUTIONS_PER_DAY
        
        # 3. Check if it's time for the next dilution
        if time.time() > self.schedule['last_dilution_time'] + interval_seconds:
            threading.Thread(target=self._run_waste_then_feed_sequence).start()
            self.schedule['last_dilution_time'] = time.time()

    def _run_waste_then_feed_sequence(self):
        if not self.automation_lock.acquire(blocking=False):
            print("Dilution skipped: another automated process is running.")
            return
        try:
            # Calculate the volume for a single dilution event
            daily_volume_L = (self.setpoints['dilution_percent'] / 100.0) * CONTAINER_VOLUME_L
            volume_per_event_L = daily_volume_L / DILUTIONS_PER_DAY
            
            if volume_per_event_L > 0:
                pump_on_time_sec = (volume_per_event_L * 1000) / (PUMP_FLOW_RATE_ML_MIN / 60)
                print(f"Starting dilution event ({pump_on_time_sec:.1f}s per pump)...")
                
                # Waste pump (pump2)
                if not self.manual_overrides['pump2']: self._set_actuator('pump2', 1)
                time.sleep(pump_on_time_sec)
                if not self.manual_overrides['pump2']: self._set_actuator('pump2', 0)
                
                time.sleep(PUMP_INTER_DELAY_SECONDS) # Pause between pumps
                
                # Feed pump (pump1)
                if not self.manual_overrides['pump1']: self._set_actuator('pump1', 1)
                time.sleep(pump_on_time_sec)
                if not self.manual_overrides['pump1']: self._set_actuator('pump1', 0)
                print("Dilution event finished.")
        finally:
            self.automation_lock.release()

    # --- OLD DILUTION LOGIC (REMOVED) ---
    # def _handle_dilution_schedule(self): ...
    # def _run_pump_sequence(self): ...

    # --- Setters (with updates to reset scheduling) ---
    def set_light_cycle(self, hours):
        try:
            self.setpoints['light_cycle_hours'] = float(hours)
            # Reset the dilution timer when light cycle changes to prevent weird scheduling
            self.schedule['last_dilution_time'] = time.time()
        except (ValueError, TypeError): pass

    def set_dilution_rate(self, percent):
        try:
            self.setpoints['dilution_percent'] = float(percent)
            # Also reset timer here so changes are reflected quickly
            self.schedule['last_dilution_time'] = time.time()
        except (ValueError, TypeError): pass

    # ... The rest of the file (init, serial processing, OD sequence, etc.) is unchanged ...
    def _process_serial_inbound(self):
        line = self.ser.readline().decode(errors='ignore').strip()
        if not line: return
        try:
            pkt = json.loads(line)
            ts_ms = int(time.time() * 1000)
            pkt.pop('l1', None); pkt.pop('l2', None)
            self.latest_readings.update(pkt)
            if self.latest_readings['t1'] is not None:
                self.history['t1'].append({'x': ts_ms, 'y': self.latest_readings['t1']})
                if len(self.history['t1']) > self.HISTORY_MAX_LENGTH: self.history['t1'].pop(0)
            if self.latest_readings['t2'] is not None:
                self.history['t2'].append({'x': ts_ms, 'y': self.latest_readings['t2']})
                if len(self.history['t2']) > self.HISTORY_MAX_LENGTH: self.history['t2'].pop(0)
            csv_path = LOG_DIR / f"{datetime.date.today()}.csv"; self._init_csv(csv_path)
            with self._csv_lock, csv_path.open("a", newline="") as f:
                csv.writer(f).writerow([
                    datetime.datetime.utcnow().isoformat(timespec="seconds"),
                    self.latest_readings.get('t1'), self.latest_readings.get('t2'),
                    self.latest_readings.get('l1'), self.latest_readings.get('l2'),
                    self.latest_readings.get('od_for_graph')
                ])
            self.latest_readings['od_for_graph'] = None
        except json.JSONDecodeError: pass
    def _process_serial_outbound(self):
        try:
            cmd = self.out_q.get_nowait()
            with self._serial_lock: self.ser.write((json.dumps(cmd) + "\n").encode())
            for key, value in cmd.items():
                if key in self.latest_readings: self.latest_readings[key] = value
        except queue.Empty: pass
    def _set_actuator(self, name, state): self.out_q.put({"cmd": "set", name: int(state)})
    def trigger_od_reading_sequence(self):
        if not self.automation_lock.acquire(blocking=False):
            print("OD sequence skipped: Dilution in progress."); return
        initial_lights = self.latest_readings['lights']; initial_aerator = self.latest_readings['aerator']
        l1, l2 = None, None
        try:
            print("Starting OD reading sequence.")
            self._set_actuator('stir', 1)
            for i in range(OD_STIR_DURATION, 0, -1):
                self.latest_readings['od_sequence_step'] = f"Stirring... {i}s"; time.sleep(1)
            self._set_actuator('stir', 0)
            self._set_actuator('lights', 0); self._set_actuator('aerator', 0)
            for i in range(OD_SETTLE_DURATION, 0, -1):
                self.latest_readings['od_sequence_step'] = f"Settling... {i}s"; time.sleep(1)
            self.latest_readings['od_sequence_step'] = "Taking measurement..."
            with self._serial_lock:
                self.ser.write((json.dumps({"cmd": "set", "irled": 1}) + "\n").encode())
                self.latest_readings['irled'] = 1
                line = self.ser.readline().decode(errors='ignore').strip()
                if line:
                    try: pkt = json.loads(line); l1 = pkt.get('l1'); l2 = pkt.get('l2')
                    except json.JSONDecodeError: print(f"OD Reading: Received bad JSON from Arduino: {line}")
            recorded_od = None
            if l1 and l2 and l1 > 0 and l2 > 0:
                recorded_od = round(-math.log10(l2 / l1), 4)
                self.latest_readings['od'] = recorded_od; self.latest_readings['l1'] = l1; self.latest_readings['l2'] = l2
                self.schedule['last_od_reading_timestamp'] = time.time()
                self.history['od'].append({'x': int(time.time() * 1000), 'y': recorded_od})
                if len(self.history['od']) > self.HISTORY_MAX_LENGTH: self.history['od'].pop(0)
                print(f"OD Reading taken: {recorded_od} (l1={l1}, l2={l2})")
            else: print(f"OD Reading failed: Did not receive valid sensor data from serial read. Got: l1={l1}, l2={l2}")
            self.latest_readings['od_for_graph'] = recorded_od
            self.latest_readings['od_sequence_step'] = "Finalizing..."
        finally:
            self._set_actuator('irled', 0)
            if not self.manual_overrides['lights']: self._set_actuator('lights', initial_lights)
            if not self.manual_overrides['aerator']: self._set_actuator('aerator', initial_aerator)
            self.latest_readings['od_sequence_step'] = None
            self.automation_lock.release()
    def _handle_temperature_control(self):
        if self.manual_overrides['heater']: return
        internal_temp, element_temp = self.latest_readings.get('t1'), self.latest_readings.get('t2')
        setpoint = self.setpoints['temperature']
        if element_temp and element_temp >= HEATER_ELEMENT_MAX_TEMP:
            if self.latest_readings['heater'] == 1: self._set_actuator('heater', 0)
        elif internal_temp:
            if internal_temp < setpoint - TEMP_HYSTERESIS / 2:
                if self.latest_readings['heater'] == 0: self._set_actuator('heater', 1)
            elif internal_temp > setpoint + TEMP_HYSTERESIS / 2:
                if self.latest_readings['heater'] == 1: self._set_actuator('heater', 0)
    def _handle_light_cycle(self):
        if self.manual_overrides['lights']: return
        should_be_on = self._is_light_cycle_on()
        if self.latest_readings['lights'] != should_be_on: self._set_actuator('lights', int(should_be_on))
    def _handle_od_schedule(self):
        interval_sec = self.setpoints['od_interval_hours'] * 3600
        if interval_sec <= 0: return
        if time.time() > self.schedule['next_od_reading_time']:
            threading.Thread(target=self.trigger_od_reading_sequence).start()
            self.schedule['next_od_reading_time'] = time.time() + interval_sec
    def _run_aeration_cycle(self):
        if not self.automation_lock.acquire(blocking=False):
            print("Aeration skipped: another process is running."); return
        try:
            print(f"Starting aeration cycle for {AERATOR_ON_DURATION_SECONDS}s...")
            if not self.manual_overrides['aerator']: self._set_actuator('aerator', 1)
            time.sleep(AERATOR_ON_DURATION_SECONDS)
            if not self.manual_overrides['aerator']: self._set_actuator('aerator', 0)
        finally: self.automation_lock.release()
    def _handle_aerator_schedule(self):
        interval_sec = self.setpoints['aerator_interval_hours'] * 3600
        if interval_sec <= 0: return
        if time.time() > self.schedule['next_aeration_time']:
            threading.Thread(target=self._run_aeration_cycle).start()
            self.schedule['next_aeration_time'] = time.time() + interval_sec
    def set_manual_override(self, actuator, state):
        self.manual_overrides[actuator] = True
        self._set_actuator(actuator, state)
    def set_temperature_setpoint(self, temp):
        try: self.setpoints['temperature'] = float(temp)
        except (ValueError, TypeError): pass
    def set_od_interval(self, hours):
        try:
            new_interval_hours = float(hours)
            self.setpoints['od_interval_hours'] = new_interval_hours; new_interval_seconds = new_interval_hours * 3600
            if new_interval_seconds <= 0: return
            if self.schedule['last_od_reading_timestamp']: self.schedule['next_od_reading_time'] = self.schedule['last_od_reading_timestamp'] + new_interval_seconds
            else: self.schedule['next_od_reading_time'] = time.time() + new_interval_seconds
        except (ValueError, TypeError): pass
    def set_aerator_interval(self, hours):
        try:
            new_interval_hours = float(hours)
            self.setpoints['aerator_interval_hours'] = new_interval_hours; new_interval_seconds = new_interval_hours * 3600
            if new_interval_seconds > 0: self.schedule['next_aeration_time'] = time.time() + new_interval_seconds
        except (ValueError, TypeError): pass
    def resume_all_automation(self):
        print("Resuming all automation routines.")
        for key in self.manual_overrides: self.manual_overrides[key] = False