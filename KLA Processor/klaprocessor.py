#!/usr/bin/python
# Needs pandas. 
# `pip install pandas`

import pandas as pd
import numpy as np
import os

time_col_name = "Time (s)"
o2_col_name = "[O2] (mg/L)"
calc_col_name = "-LN(([O2]*-[O2])/([O2]*-[O2,t=0]))"
O2_STAR = 7.48

def sanitise_input(inp: str, limits: tuple[int, int]) -> tuple[bool, int]:
    retval = -1
    retbool = False
    try:
        inp_int = int(inp.strip())
        assert(inp_int >= limits[0] and inp_int <= limits[1])
        retval = inp_int
        retbool = True
    except Exception as e:
        print("Invalid input, just enter the number of selection and ensure such a" +
              " selection is available.")
    return (retbool, retval)


files: list[str] = []

for file in os.scandir():
    if file.is_file():
        if file.name.split('.')[-1] == "xlsx":
            files.append(file.path)

if len(files) > 20:
    print("Too many excel files (>20) in this folder.")
    exit(-1)

print("Select your file:")
min = 21
max = -1
for (i, fn) in enumerate(files):
    # Adjust to 1 indexing basis.
    i += 1
    if i < min:
        min = i
    if i > max:
        max = i
    print(f"{i}: {fn}")

valid_input = False
while not valid_input:
    (valid_input, ret) = sanitise_input(input("Number: "),
                                        (min, max))

ret -= 1 # Adjust to 0 indexing basis.
sel_file = files[ret]
print(f"\nSelected File: {sel_file[2:]}\n")

df = pd.read_excel(sel_file)
df["Sample ID"] = df["Sample ID"].str.rsplit(" ", n=1).str[0]

print("Select the sample:")
min = 32
max = -1
for (i, id) in enumerate(df["Sample ID"].unique()):
    # Adjust to 1 indexing basis.
    i += 1
    if i < min:
        min = i
    if i > max:
        max = i
    print(f"{i}: {id}")

valid_input = False
while not valid_input:
    (valid_input, ret) = sanitise_input(input("Number: "),
                                        (min, max))
ret -= 1 # Adjust to 0 indexing basis.
sel_sample = df["Sample ID"].unique()[ret]
print(f"\nSelected Sample: {sel_sample}\n")

new_df = pd.DataFrame()

new_df[time_col_name] = pd.to_timedelta(df[df["Sample ID"] == sel_sample]["Time"]
                                 .astype(str))
new_df[o2_col_name] = df[df["Sample ID"] == sel_sample]["Primary Reading Value"]

min_idx = new_df[o2_col_name].idxmin()

drop_condition = (new_df.index > min_idx) & (new_df[o2_col_name] > new_df[o2_col_name].min())

new_df = new_df[~drop_condition].copy()
last_value = new_df[o2_col_name].iloc[-1]

not_matching_last = new_df[o2_col_name] != last_value

last_different_index = not_matching_last[::-1].idxmax()
new_df = new_df.loc[:last_different_index + 1]
new_df = new_df[new_df[o2_col_name] < O2_STAR]
new_df[time_col_name] = (new_df[time_col_name] -
                      new_df[time_col_name].min()).dt.total_seconds().astype(int)
with pd.option_context('display.max_rows', None, 'display.max_columns', None, 'display.max_colwidth', None):
    print(new_df)

input("Press Enter to continue if data looks correct:")

do_t0 = new_df[o2_col_name].min()
new_df[calc_col_name] = -np.log((O2_STAR - new_df[o2_col_name])/(O2_STAR - do_t0))
sample_name: str = ""
for thing in sel_sample.split(' '):
    sample_name += sel_sample
try:
    rpm, rem = sample_name.split('R')
    if rem.startswith('0'):
        val = np.float64()
        order = 1
        for char in rem:
            if char == 'L':
                break
            val += order * int(char)
            order /= 10
    else:
        val = int(rem.split('L')[0])
except Exception:
    val = 0.0
    rpm = 0

print(f"Detected Parameters: Airflow rate: {val} LPM; RPM: {rpm}")
file_name = f"./{rpm}RPM-{val}LPM.xlsx"
new_df.to_excel(file_name)
print(f"Output results to {file_name}")
