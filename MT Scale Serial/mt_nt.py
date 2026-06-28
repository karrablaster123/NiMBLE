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

PORT = "COM11"
BAUDRATE = 9600
INTERVAL = 30*60 # 30*60 seconds (30 min)
FLOWRATE_FRAME = 24 # 24 * 30 minutes is 12 hours.

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
        case _:
            return(-100, f"Something went wrong! {r}")


DATE = datetime.now().strftime("%Y-%m-%d")
WEIGHT_RE = re.compile(r"(\d+\.\d+) kg")


class FlowRateApp(App):
    CSS_PATH = "mt.tcss"
    OUT_FILE = get_valid_filename(DATE)

    def __init__(self):
        super().__init__()
        self.outfile = None
        # Open a serial connection.
        # See Mettler-Toledo Documentation for the Terminal
        # for an explanation to bytesize, parity, and stopbits.
        self.ser = serial.Serial(
                PORT,
                BAUDRATE,
                timeout=2,
                bytesize=serial.EIGHTBITS,
                parity=serial.PARITY_NONE,
                stopbits=serial.STOPBITS_ONE,
                )
        self.weights = []
        self.flowrates = [[], []] # flowrates(12 hr), flowrates(2hr)
        self.n_measurements = 0

    def __del__(self):
        if self.outfile is not None:
            self.outfile.close()
        self.ser.close()

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
    
    def get_new_outfile(self):
        self.OUT_FILE = get_valid_filename(DATE)
        self.outfile = open(self.OUT_FILE, "w")
        self.outfile.write("Date & Time, Mass (g), Flowrate (g/hr), Flowrate(2hr) (g/hr), Note\n")
        

    def read_weight(self):
        if self.outfile is None:
            self.get_new_outfile()
        response = read_weight(self.ser)
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
            assert(matches is not None)
            weight = round(float(matches.groups()[0])*1000.0, 1) # kg to g
            flowrate = -100000
            flowrate_2 = -100000
            note = ""
            if len(self.weights) > 0 and weight - self.weights[-1] < -1000:
                self.weights.clear()
                note = "EFFCLEAR"
            if len(self.weights) >= 24:
                flowrate = (weight - self.weights[-FLOWRATE_FRAME]) / (INTERVAL * FLOWRATE_FRAME)
                flowrate = flowrate * 3600 # Conversion to g/hr
            if len(self.weights) >= 4:
                flowrate_2 = (weight - self.weights[-4]) / (INTERVAL * 4)
                flowrate_2 = flowrate_2 * 3600 # Conversion to g/hr
            self.weights.append(weight)
            self.weight_display.update(f"{weight:.1f} g")
            assert(self.outfile is not None)
            try:
                self.outfile.write(f"{curr_time},{weight},{flowrate},{flowrate_2},{note}\n")
            except PermissionError:
                self.get_new_outfile()
                self.outfile.write(f"{curr_time},{weight},{flowrate},{flowrate_2},{note}\n")
            curr_time = datetime.now().strftime("%H:%M:%S")
            self.n_measurements += 1
            self.status_label.update(
                f"Last Updated: {curr_time}\n"
                + f"No. of Measurements: {self.n_measurements}\n"
                + f"Status: {stat}"
            )
            if flowrate > -100000:
                self.flowrate_display.update(f"{flowrate:.1f} g/hr")
                self.flowrates[0].append(flowrate)
            else:
                self.flowrate_display.update("~.~ g/hr")
            if flowrate_2 > -100000:
                self.flowrate2_display.update(f"{flowrate_2:.1f} g/hr")
                self.flowrates[0].append(flowrate_2)
            else:
                self.flowrate2_display.update("~.~ g/hr")
            self.outfile.flush()

    def compose(self) -> ComposeResult:
        self.update_weight        = self.set_interval(INTERVAL, self.read_weight,
                                                      pause=True)
        self.weight_display       = Digits("~.~ g", id="weight")
        self.flowrate_display     = Digits("~.~ g/hr", id="flow")
        self.flowrate2_display    = Digits("~.~ g/hr", id="flow2")
        self.status_label         = Label("", id="status")
        yield Header(show_clock=True, name="NiMBLE: Scale and Flow Rate Meter")

        yield Label("Last Weight: ")
        yield self.weight_display

        yield Label("Flowrate (12 hr, 2 hr): ")
        yield self.flowrate_display
        yield self.flowrate2_display
        yield Label("Weight History: ")

        yield Static()
        yield Button("Start", name="toggle", variant="success")
        yield Static()

        yield self.status_label

        yield Label(
            f"Update Frequency: {INTERVAL}s; " + f"Outfile: {str(Path(self.OUT_FILE).absolute())}", id="details"
        )

    def on_mount(self) -> None:
        self.title                = "NiMBLE: Scale and Flow Rate Meter"
        self.screen.styles.border = ("round", "yellow")
        


if __name__ == "__main__":
    flrapp = FlowRateApp()
    flrapp.run()
