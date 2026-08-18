import io
import pandas as pd
from PIL import Image
from google import genai

# =====================================================================
# CONFIGURATION
# =====================================================================
# ⚠️ Paste your Gemini API key from Google AI Studio here:

def extract_table_as_dataframe(image_path):
    # 1. Initialize the Gemini Client
    client = genai.Client(api_key=REMOVED)

    # 2. Load the image
    try:
        img = Image.open(image_path)
    except Exception as e:
        print(f"Error loading image: {e}")
        return None

    # 3. Prompt Gemini to output Tab-Separated Values (TSV)
    # This prevents parsing issues with commas or formatting characters
    prompt = (
        "Analyze this image of a table. Extract all the data and format it "
        "strictly as Tab-Separated Values (TSV). Include the header row if present. "
        "Do not include any Markdown blocks, conversational text, introduction, or triple backticks (```)."
    )

    print("Sending image to Gemini (using gemini-2.5-flash)...")
    
    try:
        response = client.models.generate_content(
            model='gemini-2.5-flash-lite',
            contents=[img, prompt]
        )
        
        assert(isinstance(response.text, str))
        raw_tsv_text = response.text.strip()
        
        if not raw_tsv_text:
            print("Gemini returned an empty response.")
            return None

        # 4. Convert the raw text string into a Pandas DataFrame
        # io.StringIO tricks pandas into reading the string like a CSV/TSV file
        df = pd.read_csv(io.StringIO(raw_tsv_text), sep='\t')
        
        return df

    except Exception as e:
        print(f"An error occurred: {e}")
        return None

if __name__ == "__main__":
    IMAGE_FILE = "./test.jpeg" # Replace with your image
    
    # Run the function
    df = extract_table_as_dataframe(IMAGE_FILE)
    
    if df is not None:
        print("\n--- Data successfully loaded into Pandas DataFrame ---")
        print(f"Object Type: {type(df)}")
        print(f"Shape: {df.shape[0]} rows x {df.shape[1]} columns\n")
        
        # Display the DataFrame
        print(df.to_string())
        
        # You can now manipulate the data using standard Pandas commands, e.g.:
        # df.to_excel("output.xlsx", index=False)
        # print(df.describe())
