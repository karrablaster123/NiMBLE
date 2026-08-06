from pathlib import Path
import glob
import pprint
import pandas as pd

files = sorted(glob.glob("*.csv"))
assert(len(files) > 0)

print("Concatenating the following files:\n"
      f"{pprint.pformat(files)}")

data: list[pd.DataFrame] = []

for file in files:
    df = pd.read_csv(file)
    if df.shape[0] > 1:
        data.append(df)

data: pd.DataFrame = pd.concat(data)

assert(data["Date & Time"].is_monotonic_increasing)
data.set_index("Date & Time", inplace=True)

def get_unused_filename() -> Path:

    name = "Concatenated Weight & Flowrate Data.xlsx"
    number = 1
    path = Path( name ) 
    while path.exists():
        path = Path( name + str ( number ) )
        number += 1
    return path

data.to_excel(get_unused_filename())
