#!/usr/bin/env python3
# pi_controller.py

import json
import time
import datetime
import threading

from flask import (
    Flask, Response, request, redirect,
    url_for, render_template, send_file, jsonify # Import jsonify
)
from bioreactor_controller import BioreactorController
from config import LOG_DIR

app = Flask(__name__)
controller = BioreactorController()
controller.start()

@app.route('/')
def index():
    return render_template('index.html', setpoints=controller.setpoints)

# --- NEW ROUTE ---
@app.route('/history')
def history():
    """Provides the entire chart history for the current session."""
    return jsonify(controller.history)

@app.route('/toggle', methods=['POST'])
def toggle():
    # ... (this route is unchanged)
    actuator = request.form['act']
    new_state = 0 if controller.latest_readings.get(actuator, 0) else 1
    controller.set_manual_override(actuator, new_state)
    time.sleep(0.1)
    return redirect(url_for('index'))

@app.route('/set_automation', methods=['POST'])
def set_automation():
    # ... (this route is unchanged)
    controller.set_temperature_setpoint(request.form.get('temp_setpoint'))
    controller.set_light_cycle(request.form.get('light_cycle_hours'))
    controller.set_dilution_rate(request.form.get('dilution_percent'))
    controller.set_od_interval(request.form.get('od_interval_hours'))
    controller.set_aerator_interval(request.form.get('aerator_interval_hours')) # Added this line
    controller.resume_all_automation()
    return redirect(url_for('index'))

@app.route('/trigger_od', methods=['POST'])
def trigger_od():
    # ... (this route is unchanged)
    threading.Thread(target=controller.trigger_od_reading_sequence).start()
    return redirect(url_for('index'))

@app.route('/stream')
def stream():
    # ... (this route is unchanged)
    def gen():
        while True:
            yield f"data:{json.dumps(controller.latest_readings)}\n\n"
            time.sleep(0.2)
    return Response(gen(), mimetype='text/event-stream')

@app.route('/download')
def download():
    # ... (this route is unchanged)
    csv_path = LOG_DIR / f"{datetime.date.today()}.csv"
    if csv_path.exists():
        return send_file(csv_path, as_attachment=True)
    return "Log file not found for today.", 404

if __name__ == '__main__':
    print(f"Dashboard -> http://0.b.0.0:5000")
    app.run(host='0.0.0.0', port=5000, debug=False)