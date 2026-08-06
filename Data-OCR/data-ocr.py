import time
from typing import Optional
from pathlib import Path
import json
import pyperclip
from PIL import Image
from google import genai
from google.genai import errors

# ⚠️ Replace this with your actual Gemini API key
REMOVED = "REMOVED"

def extract_and_process_sheets(image_path: Path, max_retries=5, initial_delay=4):
    client = genai.Client(api_key=REMOVED)

    try:
        print(f"Loading image to analyze: {image_path}...")
        target_img = Image.open(image_path)
    except Exception as e:
        print(f"Error loading image: {e}")
        return None

    # Comprehensive prompt ensuring the vision model groups visual logs cleanly
    prompt = (
        "Analyze this laboratory data sheet image. Extract all data into a single clean JSON object "
        "with three top-level keys: 'equipment_check', 'general_information', and 'ph_orp_do'.\n\n"
        "1. 'equipment_check': An array of objects representing rows in the table that is labelled equipment check(ST, P1, S1, S2, S3). "
        "Use exactly these keys: 'reactor', 'agitator_rpm', 'torque_nm', 'temp_c', 'level_ml', 'airflow_lmin', 'airflow_pressure_bar', 'waterflow_lmin'. "
        "Convert non-numeric entries like 'X' or dashes to null.\n\n"
        "2. 'general_information': An object extracting fields from the 'General information' section. "
        "Use keys: 'water_bath_temp_c', 'compressor_tank_pressure_bar', 'compressor_outlet_pressure_bar', "
        "'feedsplitter_cycles_completed', 'feed_splitter_extended_time_s', 'feed_splitter_retract_delay_s', 'feed_splitter_time_retracted_s', "
        "'feed_splitter_pump_rpm', 'feed_splitter_total_retraction_s', 'effluent_mass_out_kg', 'effluent_flow_rate_per_hr', 'ph_calibration_curve'.\n\n"
        "3. 'ph_orp_do': An array of objects representing rows in the table labelled pH adjustment, ORP, DO (P1, S1, S2, S3). "
        "Use exactly these keys: 'reactor', 'ph_initial', 'ph_final', 'mgco3_added_g', 'h2so4_added_ml', 'orp_mv', 'do_mgl'. "
        "Keep raw string text for entries containing formulas/times (e.g., '4+1.5' or '2:00')."
    )

    # ---------------------------------------------------------
    # API CALL WITH RETRY LOGIC
    # ---------------------------------------------------------
    delay = initial_delay
    raw_output = None

    for attempt in range(1, max_retries + 1):
        try:
            print(f"Sending image to Gemini (Attempt {attempt}/{max_retries})...")
            
            if (attempt < 3):
                response = client.models.generate_content(
                    model='gemini-2.5-flash',
                    contents=[target_img, prompt],
                    config={"response_mime_type": "application/json"}
                )
            elif (attempt < 4):
                response = client.models.generate_content(
                    model='gemini-3-flash-preview',
                    contents=[target_img, prompt],
                    config={"response_mime_type": "application/json"}
                )
            else:
                print("\033[31mTrying with a weaker model. Data will likely be less accurate!\033[0m")
                response = client.models.generate_content(
                    model='gemini-2.5-flash-lite',
                    contents=[target_img, prompt],
                    config={"response_mime_type": "application/json"}
                )
            
            if response.text:
                raw_output = response.text.strip()
                break  # Success
                
        except errors.APIError as e:
            if e.code in [429, 503] or (e.code and e.code >= 500):
                if attempt == max_retries:
                    print(f"\n❌ Failed due to API limits/overdemand after {max_retries} attempts.")
                    return None
                print(f"⚠️ Overdemand (Error {e.code}). Retrying in {delay} seconds...")
                time.sleep(delay)
                delay *= 2  
                delay = min(20, delay)
            else:
                print(f"\n❌ API Error: {e}")
                return None
        except Exception as e:
            print(f"\n❌ Unexpected error: {e}")
            return None

    if not raw_output:
        return None

    try:
        extracted_data = json.loads(raw_output)
    except json.JSONDecodeError:
        print("Failed to parse Gemini's response as valid JSON.")
        return None

    def safe_num(val):
        if val is None or str(val).lower() in ['x', '-', 'null']:
            return ""
        return val

    def parse_float(val):
        try:
            return float(str(val).replace('kg', '').strip())
        except (ValueError, TypeError):
            return 0.0

    def safe_float(val) -> float:
        try:
            return float(val)
        except (ValueError, TypeError):
            return 0.0
    # Extract sections safely
    eq_check = extracted_data.get("equipment_check", [])
    gen_info = extracted_data.get("general_information", {})
    ph_data = extracted_data.get("ph_orp_do", [])

    # Create lookups based on reactor IDs
    eq_lookup = {item.get("reactor"): item for item in eq_check if "reactor" in item}
    ph_lookup = {item.get("reactor"): item for item in ph_data if "reactor" in item}

    # --- BUILD STRUCTURE 1 ---
    headers_1 = [
        "pH_calibration_curve", "Stock_tank_level_mL", "Time_flow_on",
        "Time_flow_off", "Peristaltic_pump_rpm", "FeedSplitter_Ext_time_s",
        "FeedSplitter_Ret_time_s", "FeedSplitter_cycles_left", 
        "CompressedAirTank_level_bar", "CompressedAirTank_outP_bar",
        "Mass_out_g", "Effluent_mass_flow_gh", "Agitator_rpm",
        "Agitator_torque", "MFC_air_flow_rate_Lmin", "MFC_pressure_bar",
        "Waterbath_temp_C", "Circulating_water_flow_Lmin"
    ]
    # lines_1 = ["\t".join(headers_1)]
    lines_1 = []
    rows_target_1 = ["Stock", "P1", "S1", "S2", "S3", "General"]

    for row_name in rows_target_1:
        # Resolve visual ID variants (e.g., sheet says 'ST' for 'Stock')
        id = "ST" if row_name == "Stock" else row_name
        eq_item = eq_lookup.get(id, {})

        row_data = {k: "" for k in headers_1}

        if row_name in ["Stock", "P1", "S1", "S2", "S3"]:
            if row_name == "Stock":
                row_data["Stock_tank_level_mL"] = safe_num(eq_item.get("level_ml"))
            row_data["Agitator_rpm"] = safe_num(eq_item.get("agitator_rpm"))
            row_data["Agitator_torque"] = safe_num(eq_item.get("torque_nm"))
            row_data["MFC_air_flow_rate_Lmin"] = safe_num(eq_item.get("airflow_lmin"))
            row_data["MFC_pressure_bar"] = safe_num(eq_item.get("airflow_pressure_bar"))
            row_data["Circulating_water_flow_Lmin"] = safe_num(eq_item.get("waterflow_lmin"))

        elif row_name == "General":
            row_data["Peristaltic_pump_rpm"] = safe_num(gen_info.get("feed_splitter_pump_rpm"))
            row_data["FeedSplitter_Ext_time_s"] = safe_num(gen_info.get("feed_splitter_extended_time_s"))
            row_data["FeedSplitter_Ret_time_s"] = safe_num(gen_info.get("feed_splitter_total_retraction_s"))
            row_data["CompressedAirTank_level_bar"] = safe_num(gen_info.get("compressor_tank_pressure_bar"))
            row_data["CompressedAirTank_outP_bar"] = safe_num(gen_info.get("compressor_outlet_pressure_bar"))
            row_data["Waterbath_temp_C"] = safe_num(gen_info.get("water_bath_temp_c"))
            row_data["pH_calibration_curve"] = safe_num(gen_info.get("ph_calibration_curve"))
            row_data["FeedSplitter_cycles_left"] = safe_num(gen_info.get("feedsplitter_cycles_completed"))
            
            # Programmatic unit conversions (kg to grams)
            raw_mass_kg = parse_float(gen_info.get("effluent_mass_out_kg"))
            if raw_mass_kg < 30:
                raw_mass_kg = raw_mass_kg*1000
            row_data["Mass_out_g"] = f"{raw_mass_kg:g}" if raw_mass_kg > 0 else ""
            
            raw_flow_kg = parse_float(gen_info.get("effluent_flow_rate_per_hr"))
            row_data["Effluent_mass_flow_gh"] = f"{raw_flow_kg:g}" if raw_flow_kg > 0 else ""

        lines_1.append("\t".join([str(row_data[h]) for h in headers_1]))

    structure_1_tsv = "\n".join(lines_1)

    # --- BUILD STRUCTURE 2 ---
    headers_2 = [
        "pH_initial", "pH_adjusted", "ORP_mV", "DO_mgL", "Ferrous Raw Abs", 
        "FerroVer Raw Abs", "Sulfaver Raw Abs", "Ferrous_mgL", "Total_Fe_mgL", 
        "Ferric_mgL", "Sulfate_mgL", "Temperature_C", "SolidsLoading_wperc", 
        "Density_gmL", "OUR_slurry_volume_mL", "OUR_mgO2_L_h", "1N_H2SO4_added_mL", 
        "MgCO3_added_g", "Tank_level_mL", "Water_added_mL", "Sample_removed_mL"
    ]
    # lines_2 = ["\t".join(headers_2)]
    lines_2 = []
    rows_target_2 = ["P1", "S1", "S2", "S3"]

    for row_name in rows_target_2:
        eq_item = eq_lookup.get(row_name, {})
        ph_item = ph_lookup.get(row_name, {})

        row_data = {k: "" for k in headers_2}

        row_data["pH_initial"] = safe_num(ph_item.get("ph_initial"))
        row_data["pH_adjusted"] = safe_num(ph_item.get("ph_final"))
        row_data["ORP_mV"] = safe_num(ph_item.get("orp_mv"))
        row_data["DO_mgL"] = safe_num(ph_item.get("do_mgl"))
        row_data["Temperature_C"] = safe_num(eq_item.get("temp_c"))
        row_data["Tank_level_mL"] = safe_num(eq_item.get("level_ml"))
        row_data["1N_H2SO4_added_mL"] = safe_num(ph_item.get("h2so4_added_ml"))
        row_data["MgCO3_added_g"] = safe_num(ph_item.get("mgco3_added_g"))

        if isinstance(row_data["MgCO3_added_g"], str) and "+" in row_data["MgCO3_added_g"]:
            data = row_data["MgCO3_added_g"]
            values = [safe_float(val) for val in data.split('+')]
            value = sum(values)
            row_data["MgCO3_added_g"] = str(value)

        if isinstance(row_data["1N_H2SO4_added_mL"], str) and "+" in row_data["1N_H2SO4_added_mL"]:
            data = row_data["1N_H2SO4_added_mL"]
            values = [safe_float(val) for val in data.split('+')]
            value = sum(values)
            row_data["1N_H2SO4_added_mL"] = str(value)

        lines_2.append("\t".join([str(row_data[h]) for h in headers_2]))

    structure_2_tsv = "\n".join(lines_2)

    return structure_1_tsv, structure_2_tsv

def get_file() -> Optional[Path]:
    folder = Path(".")
    
    if not folder.exists() or not folder.is_dir():
        raise ValueError(f"Directory not found: {folder}")

    valid_extensions = {".jpg", ".jpeg", ".png", ".webp"}

    images = [
        file for file in folder.iterdir()
        if file.is_file() and file.suffix.lower() in valid_extensions
    ]

    if not images:
        return None

    return max(images, key=lambda f: f.stat().st_mtime)

if __name__ == "__main__":
    IMAGE_FILE = get_file()
    if IMAGE_FILE is None:
        print("No image found in the folder!")
        exit(-1)
    
    results = extract_and_process_sheets(IMAGE_FILE)
    
    if results:
        structure_1, structure_2 = results
        
        # Clipboard Processing Sequence
        pyperclip.copy(structure_1)
        print("\n" + "="*65)
        print("✅ STRUCTURE 1 (Equipment Function) copied to clipboard!")
        print("Go paste this into your first Excel Sheet.")
        print("="*65)
        
        input("\nPress ENTER when you have pasted Structure 1 and are ready to copy Structure 2... ")
        
        pyperclip.copy(structure_2)
        print("\n" + "="*65)
        print("✅ STRUCTURE 2 (DailyInput) copied to clipboard!")
        print("Go paste this into your second Excel Sheet.")
        print("="*65 + "\n")
