# import os
from typing import Optional 
from pathlib import Path
import pyperclip
from PIL import Image
from google import genai
from google.genai import errors
import time
import json
from key import REMOVED

def extract_and_process_table(image_path: Path, max_retries=5, initial_delay=4):

    client = genai.Client(api_key=REMOVED)

    try:
        print(f"Loading image to analyze: {image_path}...")
        target_img = Image.open(image_path)
    except Exception as e:
        print(f"Error loading image: {e}")
        return None

    # We ask Gemini to output pure JSON. This guarantees no formatting issues
    # and allows Python to do precise mathematical calculations for Structure 2.
    prompt = (
        "Analyze this table image. Extract all rows into a JSON array of objects. "
        "Use EXACTLY these keys for each object: Sample, Fe2_DF, Fe2_mgL, Fe2_Abs, "
        "Total_Fe_DF, Total_Fe_mgL, Total_Fe_Abs, SO4_DF, SO4_mgL, SO4_Abs. "
        "For the DF (Dilution Factor) columns, extract ONLY the integer number (e.g., if it says '25 000x', output 25000). "
        "For all other numeric columns, extract the float values."
    )

    # ---------------------------------------------------------
    # API CALL WITH RETRY LOGIC
    # ---------------------------------------------------------
    delay = initial_delay
    raw_output = None

    for attempt in range(1, max_retries + 1):
        try:
            print(f"Sending image to Gemini (Attempt {attempt}/{max_retries})...")
            
            # Force Gemini to return valid JSON
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
            
            assert(isinstance(response.text, str))
            raw_output = response.text.strip()
            break  # Success

        except errors.APIError as e:
            if e.code in [429, 503] or (e.code and e.code >= 500):
                if attempt == max_retries:
                    print(f"\n❌ Failed due to overdemand after {max_retries} attempts.")
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

    # ---------------------------------------------------------
    # PROCESSING JSON INTO BOTH STRUCTURES
    # ---------------------------------------------------------
    try:
        data_rows = json.loads(raw_output)
    except json.JSONDecodeError:
        print("Failed to parse Gemini's response as JSON.")
        return None

    # --- BUILD STRUCTURE 1 (Raw Table) ---
    headers_1 = ["Sample", "Fe2+ DF", "Fe2+ mg/L", "Fe2+ Abs", "Total Fe DF", "Total Fe mg/L", "Total Fe Abs", "SO4 DF", "SO4 mg/L", "SO4 Abs"]
    lines_1 = ["\t".join(headers_1)]
    
    for r in data_rows:
        row_1 = [
            str(r.get("Sample", "")),
            f"{r.get('Fe2_DF', 0)}x",
            str(r.get("Fe2_mgL", 0)),
            str(r.get("Fe2_Abs", 0)),
            f"{r.get('Total_Fe_DF', 0)}x",
            str(r.get("Total_Fe_mgL", 0)),
            str(r.get("Total_Fe_Abs", 0)),
            f"{r.get('SO4_DF', 0)}x",
            str(r.get("SO4_mgL", 0)),
            str(r.get("SO4_Abs", 0))
        ]
        lines_1.append("\t".join(row_1))
    
    structure_1_tsv = "\n".join(lines_1)

    # --- BUILD STRUCTURE 2 (Calculated Final Values) ---
    # headers_2 = ["Ferrous Raw Abs", "FerroVer Raw Abs", "Sulfaver Raw Abs", "Ferrous_mgL", "Total_Fe_mgL", "Ferric_mgL", "Sulfate_mgL"]
    lines_2 = []
    # lines_2 = ["\t".join(headers_2)]

    for r in data_rows:
        # Perform the exact math: Concentration * Dilution Factor
        try:
            ferrous_mgl_calc = float(r.get("Fe2_mgL", 0)) * float(r.get("Fe2_DF", 1))
        except Exception:
            ferrous_mgl_calc = 0
        try:
            total_fe_mgl_calc = float(r.get("Total_Fe_mgL", 0)) * float(r.get("Total_Fe_DF", 1))
        except Exception:
            total_fe_mgl_calc = 0
        try:
            sulfate_mgl_calc = float(r.get("SO4_mgL", 0)) * float(r.get("SO4_DF", 1))
        except Exception:
            sulfate_mgl_calc = 0
        
        # Ferric is calculated as Total Iron minus Ferrous Iron
        ferric_mgl_calc = total_fe_mgl_calc - ferrous_mgl_calc

        row_2 = [
            str(r.get("Fe2_Abs", 0)),          # Ferrous Raw Abs
            str(r.get("Total_Fe_Abs", 0)),     # FerroVer Raw Abs
            str(r.get("SO4_Abs", 0)),          # Sulfaver Raw Abs
            f"{ferrous_mgl_calc:g}",           # Ferrous_mgL (calculated)
            f"{total_fe_mgl_calc:g}",          # Total_Fe_mgL (calculated)
            f"{ferric_mgl_calc:g}",            # Ferric_mgL (calculated)
            f"{sulfate_mgl_calc:g}"            # Sulfate_mgL (calculated)
        ]
        lines_2.append("\t".join(row_2))

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

    results = extract_and_process_table(IMAGE_FILE)

    if results:
        structure_1, structure_2 = results
        
        # Action 1: Copy Original Structure
        pyperclip.copy(structure_1)
        print("\n" + "="*50)
        print("✅ STRUCTURE 1 (Raw Data) successfully copied to clipboard!")
        print("Go paste this into your first sheet now.")
        print("="*50)
        
        # Wait for user
        input("\nPress ENTER when you have pasted Structure 1 and are ready to copy Structure 2... ")
        
        # Action 2: Copy Calculated Structure
        pyperclip.copy(structure_2)
        print("\n" + "="*50)
        print("✅ STRUCTURE 2 (Calculated Final Values) successfully copied to clipboard!")
        print("Go paste this into your second sheet now.")
        print("="*50 + "\n")
