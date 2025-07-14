import json, threading, time, queue
from pathlib import Path

import serial
from flask import Flask, Response, request, redirect, url_for, render_template_string

SERIAL_PORT = "/dev/ttyACM0"
BAUD = 115200

app = Flask(__name__)
latest = {}                # last packet from Arduino
out_q = queue.Queue()       # commands to send

HTML = """
<!doctype html><title>Bio-reactor Control</title><style>
body{font-family:sans-serif;max-width:640px;margin:auto;padding:1rem}
.card{border:1px solid #ccc;padding:1rem;margin:1rem 0;border-radius:8px}
button{margin:0.2rem;padding:0.4rem 0.8rem}
</style>
<h1>Bio-reactor Dashboard</h1>

<div class="card">
  <h3>Sensors</h3>
  <ul id="sensors">
    <li>Temp 1: <span id="t1">--</span> °C</li>
    <li>Temp 2: <span id="t2">--</span> °C</li>
    <li>Light 1: <span id="l1">--</span></li>
    <li>Light 2: <span id="l2">--</span></li>
  </ul>
</div>

<div class="card">
  <h3>Actuators</h3>
  <form method="post" action="/toggle">
    {% for key,label in buttons %}
      <button name="act" value="{{key}}">{{ label }}</button>
    {% endfor %}
  </form>
  <small>Status: <span id="status"></span></small>
</div>

<script>
const evt = new EventSource('/stream');
evt.onmessage = e => {
  const d = JSON.parse(e.data);
  ['t1','t2','l1','l2'].forEach(k=>{document.getElementById(k).textContent=d[k]});
  const status = Object.entries(d)
        .filter(([k,v])=>['heater','aerator','lights','stir','pump1','pump2','irled'].includes(k))
        .map(([k,v])=>k+'='+v).join(' ');
  document.getElementById('status').textContent = status;
};

const fmt = v => (v === null || v === undefined) ? '––' : v;
['t1','t2','l1','l2'].forEach(k=>{
  document.getElementById(k).textContent = fmt(d[k]);
});

</script>
"""

@app.route('/')
def index():
    btns = [
        ('heater',  'Heater'),
        ('aerator', 'Aerator'),
        ('lights',  'Lights'),
        ('stir',    'Stir'),
        ('pump1',   'Pump 1'),
        ('pump2',   'Pump 2'),
        ('irled',   'IR LED'),
    ]
    return render_template_string(HTML, buttons=btns)

@app.route('/toggle', methods=['POST'])
def toggle():
    act = request.form['act']
    # flip the current value
    new_val = 0 if latest.get(act) else 1
    out_q.put({ "cmd":"set", act:new_val })
    time.sleep(0.1)      # allow background thread to push update
    return redirect(url_for('index'))

@app.route('/stream')
def stream():
    def gen():
        while True:
            time.sleep(0.2)
            yield f"data:{json.dumps(latest)}\n\n"
    return Response(gen(), mimetype='text/event-stream')

def serial_worker():
    with serial.Serial(SERIAL_PORT, BAUD, timeout=1) as ser:
        while True:
            # outbound commands
            try:
                cmd = out_q.get_nowait()
                ser.write((json.dumps(cmd) + "\n").encode())
            except queue.Empty:
                pass
            # inbound packets
            line = ser.readline().decode().strip()
            if line:
                try:
                    latest.update(json.loads(line))
                except json.JSONDecodeError:
                    print("Bad line:", line)

if __name__ == '__main__':
    threading.Thread(target=serial_worker, daemon=True).start()
    print("Flask running on http://<pi-ip>:5000")
    app.run(host='0.0.0.0', port=5000, debug=False)
