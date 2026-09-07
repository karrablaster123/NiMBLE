#ty: ignore[unresolved-attribute]
import traceback
import bisect
from typing import Optional
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
        Digits,
        DataTable,
        )
from textual_plotext import PlotextPlot
import logging

# --- Configuration & Constants ---
PORT = "COM11"
BAUDRATE = 9_600
INTERVAL = 30 * 60  # 30 minutes in seconds

INVALID_FLOWRATE = -100_000.0
EFF_CLEAR_THRESHOLD = -1_000.0
WEIGHT_RE = re.compile(r"(\d+\.\d+) kg")

def setup_file_logger(name: str, log_file: str = "app.log"):
  logger = logging.getLogger(name)
  logger.setLevel(logging.DEBUG)

  # Prevent duplicate handlers if called multiple times
  if not logger.handlers:
    # File Handler only (no StreamHandler)
    fh = logging.FileHandler(log_file)
    fh.setLevel(logging.DEBUG)

    formatter = logging.Formatter(
        "%(asctime)s - %(name)s - %(levelname)s - %(message)s"
    )
    fh.setFormatter(formatter)

    logger.addHandler(fh)

  return logger

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
        # Added Raw Mass and Cumulative Mass columns
        f.write("Date & Time,Raw Mass (g),Cumulative Mass (g),Flowrate 24 (g/hr),Flowrate 2hr (g/hr),Note\n")

def load_latest_data(logger: logging.Logger) -> tuple[Path, list, list, int, float, Optional[float]]:
    """Finds the most recent file. Returns its data if < 1 day old, else returns a new file setup."""
    files = sorted(Path('.').glob("Mass-*.csv"), key=lambda p: p.stat().st_mtime)
    if not files:
        return get_valid_filename(), [], [[], []], 0, 0.0, None

    latest_file = files[-1]
    weights, flowrates = [], [[], []]
    
    tare_offset = 0.0
    last_raw_weight = None
    
    try:
        logger.info(f"Loaded {latest_file}")
        with open(latest_file, "r") as f:
            reader = csv.reader(f)
            next(reader, None)  # Skip header
            for row in reader:
                logger.info(row)
                if len(row) >= 5:
                    dt = row[0]
                    # Handle backwards compatibility with old 5-column files
                    if len(row) >= 6:
                        raw_w, cum_w = float(row[1]), float(row[2])
                        f24, f2 = float(row[3]), float(row[4])
                    else:
                        raw_w = float(row[1])
                        cum_w = raw_w  # No cumulative column existed yet
                        f24, f2 = float(row[2]), float(row[3])
                    logger.info(dt, cum_w, raw_w)
                    # Load CUMULATIVE weight into the array for flowrate logic
                    weights.append((dt, cum_w))
                    
                    # Track latest state so offset survives a program restart
                    last_raw_weight = raw_w
                    tare_offset = cum_w - raw_w

                    if f24 > INVALID_FLOWRATE: 
                        flowrates[0].append((dt, f24))
                    if f2 > INVALID_FLOWRATE:  
                        flowrates[1].append((dt, f2))
        if len(weights) > 1:
            last_time = datetime.strptime(weights[-1][0], "%Y-%m-%d %H:%M")
            logger.info("Testing old data recency.")
            logger.info(f"{datetime.now() - last_time}")
            if datetime.now() - last_time < timedelta(days=1):
                # Now returns 6 items to recover tare state
                return latest_file, weights, flowrates, len(weights), tare_offset, last_raw_weight
    except Exception as e:
        logger.info(f"Warning: Failed to parse existing file ({e}). Starting fresh.")

    return get_valid_filename(), [], [[], []], 0, 0.0, None

def find_weight(
    weights: list[tuple[str, float]],
    td: timedelta,
    search_dt: str | datetime,
) -> Optional[float]:
    if not weights:
        return None

    if isinstance(search_dt, str):
        search_dt = datetime.strptime(search_dt, "%Y-%m-%d %H:%M")

    target_dt = search_dt - td
    err_tol = timedelta(minutes=31)

    closest_weight = None
    closest_diff = timedelta.max

    for timestamp, weight in weights:
        dt = datetime.strptime(timestamp, "%Y-%m-%d %H:%M")
        diff = abs(dt - target_dt)

        if diff < closest_diff:
            closest_diff = diff
            closest_weight = weight

    return closest_weight if closest_diff <= err_tol else None

def read_weight_from_serial(ser: serial.Serial, logger: Optional[logging.Logger]) -> str:
    """Sends command to scale and reads the response."""
    try:
        ser.write(b"SI\r\n")
        time.sleep(0.2)
        if ser.in_waiting > 0:
            response = ser.read(ser.in_waiting)
            return response.decode(errors="ignore")
    except serial.SerialException as e:
        if logger:
            logger.info("Unable to connect to serial port")
            logger.info(e)
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

        # 1. Row 1: Weights (Embedded Titles)
        self.raw_weight_display = Digits("~.~ g", id="raw-weight")
        self.raw_weight_display.border_title = "Raw Weight"
        yield self.raw_weight_display

        self.weight_display = Digits("~.~ g", id="weight")
        self.weight_display.border_title = "Cumulative Weight"
        yield self.weight_display

        # 2. Row 2: Flowrates (Embedded Titles)
        self.flowrate_24hr_display = Digits("~.~ g/hr", id="flow")
        self.flowrate_24hr_display.border_title = "Flowrate (24 hr)"
        yield self.flowrate_24hr_display

        self.flowrate_2hr_display = Digits("~.~ g/hr", id="flow2")
        self.flowrate_2hr_display.border_title = "Flowrate (2 hr)"
        yield self.flowrate_2hr_display

        # 3. Row 3: Buttons
        yield Button("Start", name="toggle", variant="success", id="toggle-btn")
        yield Button("Eff Bucket Replaced", name="tare", variant="primary", id="tare-btn")

        # 4. Row 4: Status and Footer
        self.status_label = Label("Status: Waiting to start...", id="status")
        yield self.status_label

        yield Label(id="details")
        yield Footer()

    def on_mount(self) -> None:
        # Link UI components to the App's state updater
        self.app.ui_status_label = self.status_label
        self.app.ui_weight_display = self.weight_display
        self.app.ui_raw_weight_display = self.raw_weight_display
        # Fix: Added `self.app.` to properly link these to FlowRateApp
        self.app.ui_flowrate_24hr_display = self.flowrate_24hr_display 
        self.app.ui_flowrate_2hr_display = self.flowrate_2hr_display 
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
        elif button.id == "tare-btn":
            # 2. Trigger manual tare condition
            self.app.manual_tare_requested = True
            self.app.perform_measurement() # Execute immediately

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
            w_times = [datetime.strptime(w[0], "%Y-%m-%d %H:%M").timestamp() for w in recent_weights]
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
        
        recent_24 = self.app.flowrates[0][-30:]
        if recent_24:
            f24_times = [datetime.strptime(f[0], "%Y-%m-%d %H:%M").timestamp() for f in recent_24]
            f24_vals = [f[1] for f in recent_24]
            flow_plot.plt.plot(f24_times, f24_vals, label="12hr", marker="dot", color="green")
            all_flow_times.extend(f24_times)
            
        recent_2 = self.app.flowrates[1][-30:]
        if recent_2:
            f2_times = [datetime.strptime(f[0], "%Y-%m-%d %H:%M").timestamp() for f in recent_2]
            f2_vals = [f[1] for f in recent_2]
            flow_plot.plt.plot(f2_times, f2_vals, label="2hr", marker="dot", color="red")
            all_flow_times.extend(f2_times)
            
        if all_flow_times:
            # Collect unique times across both flow plots to build a unified X-axis
            self.set_time_ticks(flow_plot.plt, sorted(list(set(all_flow_times))))
            
        flow_plot.refresh()

class DataScreen(Screen):
    """Screen for displaying tabular historical data directly from the CSV."""

    def compose(self) -> ComposeResult:
        yield Header(show_clock=True, name="NiMBLE: Data Table")
        yield DataTable(id="data-table")
        yield Footer()

    def on_screen_resume(self) -> None:
        """Read directly from the CSV so all rows/columns are exactly matched."""
        table = self.query_one("#data-table", DataTable)
        table.clear(columns=True)
        table.cursor_type = "row"
        table.zebra_stripes = True

        try:
            with open(self.app.outfile, "r") as f:
                reader = csv.reader(f)
                header = next(reader, None)
                if header:
                    # Dynamically add all headers directly from the CSV
                    table.add_columns(*header)
                    for row in reader:
                        # Clean up INVALID_FLOWRATE so it reads nicely in the UI
                        clean_row = ["N/A" if item == str(INVALID_FLOWRATE) else item for item in row]
                        table.add_row(*clean_row)
                
                # Scroll table to the bottom row to show the most recent entry
                if table.row_count > 0:
                    table.move_cursor(row=table.row_count - 1)

        except Exception as e:
            self.app.logger.info(f"Failed to load data for DataScreen: {e}")

class FlowRateApp(App):
    CSS_PATH = "mt.tcss"
    BINDINGS = [
            Binding("m", "switch_mode('main')", "Main Screen", priority=True),
            Binding("h", "switch_mode('history')", "History Plot", priority=True),
            Binding("d", "switch_mode('data')", "Data Table", priority=True), # <-- ADD THIS
            Binding("q", "quit", "Quit", priority=True),
            ]

    MODES = {
            "main": MainScreen,
            "history": HistoryScreen,
            "data": DataScreen,
            }

    def __init__(self):
        self.logger = setup_file_logger(__name__)
        self.logger.info("Logging started!")
        super().__init__()
        # Data storage and File setup
        (self.outfile, 
         self.weights, 
         self.flowrates, 
         self.n_measurements, 
         self.tare_offset, 
         self.last_raw_weight) = load_latest_data(self.logger)
        self.manual_tare_requested = False

        if not self.outfile.exists():
            init_csv(self.outfile)

        # UI References (populated by MainScreen)
        self.ui_status_label = None
        self.ui_weight_display = None
        self.ui_raw_weight_display = None
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
            self.logger.info("Unable to connect to serial port")
            self.logger.info(e)

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
        curr_time_full = curr_datetime.strftime("%Y-%m-%d %H:%M")
        curr_time_short = curr_datetime.strftime("%H:%M:%S")

        response = read_weight_from_serial(self.ser, self.logger)

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
        raw_weight = round(float(matches.groups()[0]) * 1000.0, 1)  # kg to g
        note = ""

        if self.last_raw_weight is None:
            self.last_raw_weight = raw_weight

        # 1 & 2. Handle automatic drops and manual button presses
        if (raw_weight - self.last_raw_weight) < EFF_CLEAR_THRESHOLD or self.manual_tare_requested:
            # Shift the offset up by the exact amount the scale dropped
            # This makes the transition completely seamless for cumulative tracking
            self.tare_offset += (self.last_raw_weight - raw_weight)
            note = "EFFCLEAR-Manual" if self.manual_tare_requested else "EFFCLEAR-Auto"
            self.manual_tare_requested = False

        # 3. Calculate Cumulative Weight
        cumulative_weight = raw_weight + self.tare_offset
        self.last_raw_weight = raw_weight

        # 4. Calculate Flowrates using cumulative_weight
        flowrate_24 = INVALID_FLOWRATE
        flowrate_2 = INVALID_FLOWRATE

        past_weight_24 = find_weight(
            self.weights, timedelta(hours=24), curr_datetime
        )
        self.logger.info(past_weight_24)
        if past_weight_24 is not None:
            flowrate_24 = (cumulative_weight - past_weight_24) / 24.0  # g/hr

        past_weight_2 = find_weight(
            self.weights, timedelta(hours=2), curr_datetime
        )
        self.logger.info(past_weight_2)
        if past_weight_2 is not None:
            flowrate_2 = (cumulative_weight - past_weight_2) / 2.0  # g/hr

        # State updates: Store as (Timestamp, Cumulative Value) tuples!
        # By storing cumulative weight in `self.weights`, `find_weight` computes rates properly across tares
        self.weights.append((curr_time_full, cumulative_weight))
        self.n_measurements += 1

        # File output (atomic append)
        # Note: Added raw_weight column!
        row_data = f"{curr_time_full},{raw_weight},{cumulative_weight},{flowrate_24},{flowrate_2},{note}\n"
        try:
            with open(self.outfile, "a") as f:
                f.write(row_data)
        except PermissionError:
            # Fallback if file is locked
            self.outfile = get_valid_filename()
            init_csv(self.outfile)
            with open(self.outfile, "a") as f:
                f.write(row_data)

        # UI Updates
        if self.ui_raw_weight_display:
            self.ui_raw_weight_display.update(f"{raw_weight:.1f} g")

        if self.ui_weight_display:
            self.ui_weight_display.update(f"{cumulative_weight:.1f} g")

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
    try:
        app = FlowRateApp()
        app.run()
    except Exception as e:
        with open("crash.log", "a") as f:
            f.write(traceback.format_exc())
