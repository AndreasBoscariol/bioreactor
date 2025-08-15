#!/usr/bin/env python3
# arduino_simulator.py

import os
import pty
import time
import json
import threading
import random
import termios

# -- Simulation State --
actuator_state = {
    "heater": 0, "stir": 0, "lights": 0, "aerator": 0,
    "pump1": 0, "pump2": 0, "irled": 0
}
# Sensor values
internal_temp = 22.0
heater_temp = 22.0
# Represents the turbidity of the culture, from 0.0 (clear) to 1.0 (opaque)
culture_density = 0.05

# -- Simulation Parameters --
AMBIENT_TEMP = 20.0
HEATING_RATE = 2.5
COOLING_RATE = 0.05
# The ideal, max reading of the source photodiode (l1)
L1_INTENSITY = 950.0
# How much culture_density increases per second. Adjust to make growth faster/slower.
CULTURE_GROWTH_RATE = 0.00002

def update_simulation_state():
    """Calculates the new sensor values based on actuator states."""
    global internal_temp, heater_temp, culture_density

    # --- Temperature Simulation --- (unchanged)
    if actuator_state['heater']:
        heater_temp += HEATING_RATE * random.uniform(0.9, 1.1)
    heater_temp -= (heater_temp - internal_temp) * COOLING_RATE
    internal_temp -= (internal_temp - AMBIENT_TEMP) * (COOLING_RATE / 5)
    if heater_temp > internal_temp:
        transfer = (heater_temp - internal_temp) * 0.1
        heater_temp -= transfer
        internal_temp += transfer
    heater_temp = min(heater_temp, 90.0)

    # --- Culture Growth Simulation ---
    # Culture density slowly increases over time, simulating cell growth.
    # This directly impacts the optical density reading.
    culture_density += CULTURE_GROWTH_RATE
    culture_density = min(culture_density, 0.95) # Cap at 95% opaque

def generate_sensor_packet():
    """Generates a JSON packet with realistic sensor data."""
    
    # --- Photodiode Simulation ---
    l1, l2 = None, None # Start with no readings by default.

    # 1. Readings are ONLY possible if the IR LED is on.
    # This tests that your controller correctly turns the IRLED on.
    if actuator_state['irled']:
        
        # 2. Simulate the source photodiode (l1). It should be stable and high.
        l1 = L1_INTENSITY + random.uniform(-5, 5)

        # 3. Check for interference from main lights.
        # This tests that your controller correctly turns the main lights off.
        if actuator_state['lights']:
            # If main lights are on, the sensor is saturated and the reading is useless.
            l2 = 980.0 + random.uniform(-5, 5)
        else:
            # 4. If no interference, calculate l2 based on the Beer-Lambert law.
            # Transmitted light (l2) = Incident light (l1) * (1 - opacity)
            # This directly simulates the OD of the culture.
            l2 = l1 * (1 - culture_density)

            # 5. Check for interference from stirring.
            # This tests that your controller waits for the culture to settle.
            if actuator_state['stir']:
                # If stirring, bubbles and unevenness add significant noise.
                l2 += random.uniform(-20, 20)
    
    packet = {
        "t1": round(internal_temp + random.uniform(-0.05, 0.05), 2),
        "t2": round(heater_temp + random.uniform(-0.05, 0.05), 2),
        "l1": int(l1) if l1 is not None else None,
        "l2": int(l2) if l2 is not None else None,
        **actuator_state
    }
    return json.dumps(packet) + "\n"

def listen_for_commands(master_fd):
    # ... (This function is unchanged)
    while True:
        try:
            data = os.read(master_fd, 1024).decode().strip()
            if not data: continue
            for line in data.split('\n'):
                if not line: continue
                try:
                    cmd = json.loads(line)
                    if cmd.get("cmd") == "set":
                        for key, value in cmd.items():
                            if key in actuator_state:
                                actuator_state[key] = value
                                print(f"SIM: Received command -> {key} = {value}")
                except json.JSONDecodeError:
                    print(f"SIM: Received non-JSON data: {line}")
        except OSError:
            print("SIM: Error reading from serial, closing.")
            break
        time.sleep(0.05)

def main():
    # ... (This function is unchanged from the previous corrected version)
    master, slave = pty.openpty()
    slave_name = os.ttyname(slave)
    attrs = termios.tcgetattr(master)
    attrs[3] &= ~termios.ICANON
    attrs[3] &= ~termios.ECHO
    termios.tcsetattr(master, termios.TCSANOW, attrs)
    
    print("Arduino simulator started.")
    print(f"Connect your application to: {slave_name}")

    listener_thread = threading.Thread(target=listen_for_commands, args=(master,), daemon=True)
    listener_thread.start()

    try:
        while True:
            update_simulation_state()
            packet = generate_sensor_packet()
            os.write(master, packet.encode())
            time.sleep(1)
    except Exception as e:
        print(f"SIM: An error occurred: {e}")
    finally:
        os.close(master); os.close(slave)
        print("SIM: Shutting down.")

if __name__ == "__main__":
    main()