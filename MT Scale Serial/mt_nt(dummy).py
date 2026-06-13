from random import random
import serial
from statistics import mean
import time
from datetime import datetime
from pathlib import Path
import re
from textual.app import App, ComposeResult
from textual.widgets import (
    Label,
    Header,
    Button,
    Static,
    Digits,
    Sparkline
)

PORT = "COM11" # Windows COM Port. (Found from Device Manager)
BAUDRATE = 9600
INTERVAL = 5  # seconds


def get_valid_filename(filename) -> Path:
    n = 0
    _filename = "Mass-" + filename
    filename = _filename + ".csv"
    while Path(filename).exists():
        filename = f"{_filename}_{n}.csv"
        n += 1
    return Path(filename)


def read_weight(ser: serial.Serial) -> str:
    ser.write(b"SI\r\n")
    time.sleep(0.2)
    if ser.in_waiting > 0:
        response = ser.read(ser.in_waiting)
        return response.decode(errors="ignore")
    return ""


def get_stat(r: str) -> tuple[int, str]:
    match r:
        case "S":
            return (0, "Stable")
        case "D":
            return (0, "Unstable/Dynamic")
        case "I":
            return (-1, "Unable to get weight")
        case "+":
            return (-1, "Terminal in overload range")
        case "-":
            return (-1, "Terminal in underload range")


DATE = datetime.now().strftime("%Y-%m-%d")
OUT_FILE = get_valid_filename(DATE)
WEIGHT_RE = re.compile(r"(\d+\.\d+) kg")


class FlowRateApp(App):
    CSS_PATH = "mt.tcss"

    def __init__(self):
        super().__init__()
        self.outfile = None
        # self.ser = serial.Serial(
        #         PORT,
        #         BAUDRATE,
        #         timeout=2,
        #         bytesize=serial.EIGHTBITS,
        #         parity=serial.PARITY_NONE,
        #         stopbits=serial.STOPBITS_ONE,
        #         )
        self.last_weight = -1.0
        self.weights: list[float] = [0.0]
        self.n_measurements = 0

        self.dummy = 100.0

    def __del__(self):
        self.outfile.close()
        self.ser.close()
        super().__del__()

    def on_button_pressed(self, event: Button.Pressed) -> None:
        button = event.button
        if button.variant == "success":
            button.label = "Pause"
            button.variant = "warning"
            self.read_weight()
            self.update_weight.resume()
        else:
            button.label = "Start"
            button.variant = "success"
            self.update_weight.pause()

    def read_weight(self):
        if self.outfile is None:
            self.outfile = open(OUT_FILE, "w")
            self.outfile.write("Date & Time, Mass (kg), Flowrate (g/s)\n")
        response = f"S S      {self.dummy} kg"
        self.dummy += round((random() - 0.5) * 100, 2)
        # response = read_weight(self.ser)
        curr_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        if response == "":
            self.status_label.update("Scale did not respond!!")
        else:
            s, stat = get_stat(response[2])
            if s < 0:
                self.status_label.update(
                    f"Last Updated: {curr_time}\n"
                    + f"No. of Measurements: {self.n_measurements}\n"
                    + f"Status: {stat}"
                )
                return
            matches = WEIGHT_RE.search(response)
            weight = float(matches.groups()[0])
            flowrate = -100000
            if len(self.weights) > 1:
                flowrate = (weight - self.weights[-1]) / INTERVAL
            self.weights.append(weight)
            self.weight_display.update(f"{weight:.1f} kg")
            self.outfile.write(f"{curr_time},{weight},{flowrate}\n")
            curr_time = datetime.now().strftime("%H:%M:%S")
            self.n_measurements += 1
            self.status_label.update(
                f"Last Updated: {curr_time}\n"
                + f"No. of Measurements: {self.n_measurements}\n"
                + f"Status: {stat}"
            )
            if flowrate > -100000:
                self.flowrate_display.update(f"{flowrate:.1f} kg/s")
            self.spark.refresh()

    def compose(self) -> ComposeResult:
        self.update_weight = self.set_interval(INTERVAL, self.read_weight, pause=True)
        yield Header(show_clock=True, name="NiMBLE: Scale and Flow Rate Meter")
        self.weight_display = Digits("~.~ kg", id="weight")
        self.flowrate_display = Digits("~.~ kg/s", id="flow")
        yield Label("Last Weight: ")
        yield self.weight_display
        yield Label("Flowrate: ")
        yield self.flowrate_display
        yield Label("Weight History: ")
        self.spark = Sparkline(self.weights, summary_function=mean, id="spark")
        yield self.spark
        yield Static()
        yield Button("Start", name="toggle", variant="success")
        yield Static()
        self.status_label = Label("", id="status")
        yield self.status_label
        yield Label(
            f"Update Frequency: {INTERVAL}s; " + f"Outfile: {OUT_FILE}", id="details"
        )

    def on_mount(self) -> None:
        self.title = "NiMBLE: Scale and Flow Rate Meter"
        self.screen.styles.border = ("round", "yellow")


if __name__ == "__main__":
    flrapp = FlowRateApp()
    flrapp.run()

# def data_rw():
#
#     print(f"{PORT} {BAUDRATE}")
#     try:
#         with open(OUT_FILE, 'w') as outfile:
#             ser = serial.Serial(
#                 PORT,
#                 BAUDRATE,
#                 timeout=2,
#                 bytesize=serial.EIGHTBITS,
#                 parity=serial.PARITY_NONE,
#                 stopbits=serial.STOPBITS_ONE,
#             )
#             outfile.write("Date & Time, Mass (kg)\n")
#             print("Connected to Mettler-Toledo scale. Press Ctrl+C to stop")
#             while True:
#                 response = read_weight()
#                 curr_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
#                 if response == "":
#                     print("Got nothing back! Something may be wrong")
#                 else:
#                     print(response)
#                     matches = WEIGHT_RE.search(response)
#                     mass = float(matches.groups()[0])
#                     print(f"{curr_time}: {mass}\n")
#                     outfile.write(f"{curr_time},{mass}\n")
#                 time.sleep(5)
#     except serial.SerialException as e:
#         print(f"Could not open serial port {PORT}: {e}")
#     except KeyboardInterrupt:
#         print("\nShutting down...")
#     except Exception as exp:
#         print(f"Exception caught: {exp}")
#     finally:
#         if 'ser' in locals() and ser.is_open:
#             ser.close()
