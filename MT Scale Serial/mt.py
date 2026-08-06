#ty: ignore[unresolved-attribute]
import serial
import csv
from datetime import timedelta
import time
import re
from datetime import datetime
from pathlib import Path

from textual.app import App, ComposeResult
from textual.containers import Horizontal
from textual.screen import Screen
from textual.binding import Binding
from textual.widgets import (
        Label,
        Header,
        Footer,
        Button,
        Static,
        Digits,
        )
from textual_plotext import PlotextPlot

# --- Configuration & Constants ---
PORT = "COM11"
BAUDRATE = 9600
INTERVAL = 30 * 60  # 30 minutes in seconds
FLOWRATE_24H_FRAME = 48 # 48 * 30 mins = 24 hours
FLOWRATE_2H_FRAME = 4    # 4 * 30 mins = 2 hours

INVALID_FLOWRATE = -100000.0
EFF_CLEAR_THRESHOLD = -1000.0
WEIGHT_RE = re.compile(r"(\d+\.\d+) kg")


def get_valid_filename() -> Path:
    """Generates a valid, non-colliding filename based on the current date."""
    date_str = datetime.now().strftime("%Y-%m-%d")
    base_name = f"Mass-{date_str}"
    filename = Path(f"{base_name}.csv")
    n = 0
    while filename.exists():
        filename = Path(f"{base_name}_{n}.csv")
        n += 1
    return filename


def init_csv(filepath: Path) -> None:
    """Initializes the CSV with headers if it is newly created."""
    with open(filepath, "w") as f:
        f.write("Date & Time, Mass (g), Flowrate 24 (g/hr), Flowrate 2hr (g/hr), Note\n")


def load_latest_data() -> tuple[Path, list, list, int]:
    """Finds the most recent file. Returns its data if < 1 day old, else returns a new file setup."""
    files = sorted(Path('.').glob("Mass-*.csv"), key=lambda p: p.stat().st_mtime)
    if not files:
        return get_valid_filename(), [], [[], []], 0

    latest_file = files[-1]
    weights, flowrates = [], [[], []]
    
    try:
        with open(latest_file, "r") as f:
            reader = csv.reader(f)
            next(reader, None)  # Skip header
            for row in reader:
                if len(row) >= 4:
                    dt, w, f24, f2 = row[0], float(row[1]), float(row[2]), float(row[3])
                    weights.append((dt, w))
                    if f24 > INVALID_FLOWRATE: 
                        flowrates[0].append((dt, f24))
                    if f2 > INVALID_FLOWRATE:  
                        flowrates[1].append((dt, f2))
        
        if weights:
            last_time = datetime.strptime(weights[-1][0], "%Y-%m-%d %H:%M:%S")
            if datetime.now() - last_time < timedelta(days=1):
                return latest_file, weights, flowrates, len(weights)
    except Exception as e:
        print(f"Warning: Failed to parse existing file ({e}). Starting fresh.")
        
    return get_valid_filename(), [], [[], []], 0


def read_weight_from_serial(ser: serial.Serial) -> str:
    """Sends command to scale and reads the response."""
    try:
        ser.write(b"SI\r\n")
        time.sleep(0.2)
        if ser.in_waiting > 0:
            response = ser.read(ser.in_waiting)
            return response.decode(errors="ignore")
    except serial.SerialException:
        return ""
    return ""


def get_stat(r: str) -> tuple[int, str]:
    """Parses scale status character."""
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
            return (-100, f"Something went wrong! {r}")


class MainScreen(Screen):
    """The primary screen for displaying current metrics."""

    def compose(self) -> ComposeResult:
        yield Header(show_clock=True, name="NiMBLE: Scale and Flow Rate Meter")

        yield Label("Last Weight: ")
        self.weight_display = Digits("~.~ g", id="weight")
        yield self.weight_display

        yield Label("Flowrate (24 hr, 2 hr): ")
        self.flowrate_display = Digits("~.~ g/hr", id="flow")
        self.flowrate2_display = Digits("~.~ g/hr", id="flow2")
        yield self.flowrate_display
        yield self.flowrate2_display

        yield Label("Controls: ")
        yield Button("Start", name="toggle", variant="success", id="toggle-btn")

        yield Static()
        self.status_label = Label("Status: Waiting to start...", id="status")
        yield self.status_label

        yield Label(id="details")
        yield Footer()

    def on_mount(self) -> None:
        # Link UI components to the App's state updater
        self.app.ui_status_label = self.status_label
        self.app.ui_weight_display = self.weight_display
        self.app.ui_flowrate_display = self.flowrate_display
        self.app.ui_flowrate2_display = self.flowrate2_display
        self.query_one("#details", Label).update(
                f"Update Frequency: {INTERVAL}s; Outfile: {self.app.outfile.absolute()}"
                )

    def on_button_pressed(self, event: Button.Pressed) -> None:
        button = event.button
        if button.id == "toggle-btn":
            if button.variant == "success":
                button.label = "Pause"
                button.variant = "warning"
                self.app.perform_measurement() # Immediate read
                self.app.update_timer.resume()
            else:
                button.label = "Start"
                button.variant = "success"
                self.app.update_timer.pause()

class HistoryScreen(Screen):
    """Screen for displaying plots of weight and flowrates over time."""

    def compose(self) -> ComposeResult:
        yield Header(show_clock=True, name="NiMBLE: History")
        with Horizontal():
            yield PlotextPlot(id="weight-plot")
            yield PlotextPlot(id="flowrate-plot")
        yield Footer()

    def on_screen_resume(self) -> None:
        """Refresh the plot every time the user navigates back to this screen."""
        self.update_plot()

    def set_time_ticks(self, plt, times: list[float]) -> None:
        """Helper to generate evenly spaced X-axis ticks formatted as HH:MM."""
        if not times:
            return
            
        n_ticks = min(5, len(times)) # Limit to 5 labels to prevent crowding
        if n_ticks <= 1:
            ticks = [times[0]]
        else:
            min_t, max_t = min(times), max(times)
            step = (max_t - min_t) / (n_ticks - 1)
            ticks = [min_t + i * step for i in range(n_ticks)]

        # Convert float timestamps back to a short string (HH:MM)
        labels = [datetime.fromtimestamp(t).strftime("%H:%M") for t in ticks]
        plt.xticks(ticks, labels)

    def update_plot(self) -> None:
        # --- Update Weight Plot ---
        weight_plot = self.query_one("#weight-plot", PlotextPlot)
        weight_plot.plt.clear_data() 
        weight_plot.plt.title("Mass History (g) - Last 30")
        
        recent_weights = self.app.weights[-30:]
        if recent_weights:
            # Bypass date_form; convert string dates to float timestamps explicitly
            w_times = [datetime.strptime(w[0], "%Y-%m-%d %H:%M:%S").timestamp() for w in recent_weights]
            w_vals = [w[1] for w in recent_weights]
            weight_plot.plt.plot(w_times, w_vals, marker="dot", color="blue")
            
            # Apply our safe, manual time ticks
            self.set_time_ticks(weight_plot.plt, w_times)
            
        weight_plot.refresh()
        
        # --- Update Flowrates Plot ---
        flow_plot = self.query_one("#flowrate-plot", PlotextPlot)
        flow_plot.plt.clear_data() 
        flow_plot.plt.title("Flowrate History (g/hr)")
        
        all_flow_times = []
        
        recent_24 = self.app.flowrates[0][-15:]
        if recent_24:
            f24_times = [datetime.strptime(f[0], "%Y-%m-%d %H:%M:%S").timestamp() for f in recent_24]
            f24_vals = [f[1] for f in recent_24]
            flow_plot.plt.plot(f24_times, f24_vals, label="12hr", marker="dot", color="green")
            all_flow_times.extend(f24_times)
            
        recent_2 = self.app.flowrates[1][-30:]
        if recent_2:
            f2_times = [datetime.strptime(f[0], "%Y-%m-%d %H:%M:%S").timestamp() for f in recent_2]
            f2_vals = [f[1] for f in recent_2]
            flow_plot.plt.plot(f2_times, f2_vals, label="2hr", marker="dot", color="red")
            all_flow_times.extend(f2_times)
            
        if all_flow_times:
            # Collect unique times across both flow plots to build a unified X-axis
            self.set_time_ticks(flow_plot.plt, sorted(list(set(all_flow_times))))
            
        flow_plot.refresh()

class FlowRateApp(App):
    CSS_PATH = "mt.tcss"

    BINDINGS = [
            Binding("m", "switch_mode('main')", "Main Screen", priority=True),
            Binding("h", "switch_mode('history')", "History Plot", priority=True),
            Binding("q", "quit", "Quit", priority=True),
            ]

    MODES = {
            "main": MainScreen,
            "history": HistoryScreen,
            }

    def __init__(self):
        super().__init__()
        # Data storage and File setup
        self.outfile, self.weights, self.flowrates, self.n_measurements = load_latest_data()
        
        if not self.outfile.exists():
            init_csv(self.outfile)

        # UI References (populated by MainScreen)
        self.ui_status_label = None
        self.ui_weight_display = None
        self.ui_flowrate_24hr_display = None
        self.ui_flowrate_2hr_display = None

        try:
            self.ser = serial.Serial(
                    PORT, BAUDRATE, timeout=2,
                    bytesize=serial.EIGHTBITS,
                    parity=serial.PARITY_NONE,
                    stopbits=serial.STOPBITS_ONE,
                    )
        except serial.SerialException as e:
            self.ser = None
            print(f"Warning: Could not open serial port {PORT}. {e}")

    def on_mount(self) -> None:
        self.title = "NiMBLE: Scale and Flow Rate Meter"
        self.screen.styles.border = ("round", "yellow")
        self.update_timer = self.set_interval(INTERVAL, self.perform_measurement, pause=True)
        self.switch_mode("main")

    def __del__(self):
        if hasattr(self, 'ser') and self.ser and self.ser.is_open:
            self.ser.close()

    def perform_measurement(self) -> None:
        """Core logic to read scale, calculate flowrates, and update state."""
        if not self.ser:
            self.update_status("Error: Serial port not connected.")
            return

        curr_datetime = datetime.now()
        curr_time_full = curr_datetime.strftime("%Y-%m-%d %H:%M:%S")
        curr_time_short = curr_datetime.strftime("%H:%M:%S")
        
        response = read_weight_from_serial(self.ser)

        if not response:
            self.update_status("Scale did not respond!!")
            return

        # Check response validity
        s, stat = get_stat(response[2])
        if s < 0:
            self.update_status(
                f"Last Updated: {curr_time_short}\n"
                f"No. of Measurements: {self.n_measurements}\n"
                f"Status: {stat}"
            )
            return

        matches = WEIGHT_RE.search(response)
        if not matches:
            self.update_status(f"Regex mismatch on response: {response}")
            return

        # Parse Weight
        weight = round(float(matches.groups()[0]) * 1000.0, 1)  # kg to g
        note = ""

        # Handle massive drops in weight (Note: index [1] grabs the weight from the tuple)
        if self.weights and (weight - self.weights[-1][1]) < EFF_CLEAR_THRESHOLD:
            self.weights.clear()
            note = "EFFCLEAR"

        # Calculate Flowrates
        flowrate_24 = INVALID_FLOWRATE
        flowrate_2 = INVALID_FLOWRATE

        if len(self.weights) >= FLOWRATE_24H_FRAME:
            flowrate_24 = (weight - self.weights[-FLOWRATE_24H_FRAME][1]) / (INTERVAL * FLOWRATE_24H_FRAME)
            flowrate_24 *= 3600  # Conversion to g/hr

        if len(self.weights) >= FLOWRATE_2H_FRAME:
            flowrate_2 = (weight - self.weights[-FLOWRATE_2H_FRAME][1]) / (INTERVAL * FLOWRATE_2H_FRAME)
            flowrate_2 *= 3600  # Conversion to g/hr

        # State updates: Store as (Timestamp, Value) tuples!
        self.weights.append((curr_time_full, weight))
        self.n_measurements += 1

        # File output (atomic append)
        try:
            with open(self.outfile, "a") as f:
                f.write(f"{curr_time_full},{weight},{flowrate_24},{flowrate_2},{note}\n")
        except PermissionError:
            # Fallback if file is locked
            self.outfile = get_valid_filename()
            init_csv(self.outfile)
            with open(self.outfile, "a") as f:
                f.write(f"{curr_time_full},{weight},{flowrate_24},{flowrate_2},{note}\n")

        # UI Updates
        if self.ui_weight_display:
            self.ui_weight_display.update(f"{weight:.1f} g")

        if flowrate_24 > INVALID_FLOWRATE:
            self.flowrates[0].append((curr_time_full, flowrate_24))
            if self.ui_flowrate_24hr_display:
                self.ui_flowrate_24hr_display.update(f"{flowrate_24:.1f} g/hr")
        elif self.ui_flowrate_24hr_display:
            self.ui_flowrate_24hr_display.update("~.~ g/hr")

        if flowrate_2 > INVALID_FLOWRATE:
            self.flowrates[1].append((curr_time_full, flowrate_2))
            if self.ui_flowrate_2hr_display:
                self.ui_flowrate_2hr_display.update(f"{flowrate_2:.1f} g/hr")
        elif self.ui_flowrate_2hr_display:
            self.ui_flowrate_2hr_display.update("~.~ g/hr")

        self.update_status(
            f"Last Updated: {curr_time_short}\n"
            f"No. of Measurements: {self.n_measurements}\n"
            f"Status: {stat}"
        )

    def update_status(self, msg: str) -> None:
        """Helper to safely update the status label if it exists."""
        if self.ui_status_label:
            self.ui_status_label.update(msg)


if __name__ == "__main__":
    app = FlowRateApp()
    app.run()
