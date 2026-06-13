import os, termios
import time

# 1. Open the device
fd = os.open("/dev/ttyUSB0", os.O_RDWR | os.O_NOCTTY)

# 2. Configure (8N1, 9600 baud)
attrs = termios.tcgetattr(fd)
attrs[2] = termios.CS8 | termios.CLOCAL | termios.CREAD
attrs[4] = termios.B9600 # Input speed
attrs[5] = termios.B9600 # Output speed
termios.tcsetattr(fd, termios.TCSANOW, attrs)

def read_weight() -> str:
    os.write(fd, b"SI\r\n")

    time.sleep(0.1)

    # 4. Read response
    response = os.read(fd, 512)
    return response.decode()

try:
    while True:
        response = read_weight()
        print(response)
        time.sleep(5)
except KeyboardInterrupt:
    print("Shutting down...")
except Exception as exp:
    print(f"Exception caught {exp}")
finally:
    os.close(fd)
