# config.py

import pathlib

# -- File System --
LOG_DIR = pathlib.Path("./logs")

# -- Serial Communication
SERIAL_PORT = "/dev/pts/6" # <-- EDIT THIS LINE
#SERIAL_PORT = "/dev/ttyACM0"
BAUD        = 115_200

# -- Physical System Parameters
CONTAINER_VOLUME_L = 1.0
PUMP_FLOW_RATE_ML_MIN = 80.0

# -- Control Logic Parameters
TEMP_HYSTERESIS = 0.5
HEATER_ELEMENT_MAX_TEMP = 60.0

# -- Scheduling
# The number of times to run the dilution sequence during a single light cycle.
# The total daily volume is divided evenly between these events.
DILUTIONS_PER_DAY = 4 

# The delay between the waste pump turning off and the feed pump turning on.
PUMP_INTER_DELAY_SECONDS = 2.0

AERATOR_ON_DURATION_SECONDS = 300    # Run aerator for 5 minutes during its cycle

# -- OD Sequence Timings (in seconds)
OD_STIR_DURATION = 5
OD_SETTLE_DURATION = 5