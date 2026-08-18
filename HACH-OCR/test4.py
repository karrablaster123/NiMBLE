import base64
import io
import sys
import pandas as pd
from PIL import Image
from openai import OpenAI

# =====================================================================
# CONFIGURATION
# =====================================================================
# LM Studio Local Server Configuration
LM_STUDIO_URL = "http://localhost:1234/v1"
IMAGE_FILE = "test2.jpeg"  # Replace with your image file

def encode_image_to_base64(image_path):
    """Convert a local image file into a Base64 string for the local API."""
    try:
        with open(image_path, "rb") as image_file:
            return base64.b64encode(image_file.read()).decode('utf-8')
    except FileNotFoundError:
        print(f"Error: The file '{image_path}' could not be found.")
        sys.exit(1)
    except Exception as e:
        print(f"Error reading image: {e}")
        sys.exit(1)

def extract_table_with_local_lm_studio(image_path):
    # 1. Initialize the OpenAI client pointing to your local LM Studio server
    # LM Studio doesn't require a real API key, but a placeholder string is needed.
    client = OpenAI(
        base_url=LM_STUDIO_URL,
        api_key="lm-studio" 
    )

    # 2. Encode the image
    print(f"Encoding image: {image_path}...")
    base64_image = encode_image_to_base64(image_path)

    # 3. Formulate the prompt
    # prompt = (
    #     "Analyze this image of a table. Extract all the data and format it "
    #     "strictly as Tab-Separated Values (TSV). Include the header row if present. "
    #     "Do not include any Markdown blocks, conversational text, introduction, or triple backticks (```)."
    # )
    prompt = (
        "Analyze this image of a table. Extract all the data and format it "
        "strictly as Tab-Separated Values (TSV). Use a literal tab character to separate columns. "
        "Do not include any conversational text, introductions, or explanations before or after the data. "
        "Do not wrap the output in markdown code blocks."
    )

    print("Sending image to local LM Studio server...")
    
    try:
        # 4. Request completion using standard OpenAI vision payload format
        # Note: model="meta-llama-3.2-3b-instruct" or similar. 
        # LM Studio usually defaults to whatever model you currently have loaded active, 
        # but passing a string is required by the API.
        response = client.chat.completions.create(
            model="local-model", 
            messages=[
                {
                    "role": "user",
                    "content": [
                        {"type": "text", "text": prompt},
                        {
                            "type": "image_url",
                            "image_url": {
                                "url": f"data:image/png;base64,{base64_image}"
                            }
                        }
                    ]
                }
            ],
            temperature=0.1 # Low temperature for strict structural data adherence
        )
        assert(isinstance(response.choices[0].message.content, str))
        raw_tsv_text = response.choices[0].message.content.strip()
        
        if not raw_tsv_text:
            print("The local model returned an empty response.")
            return None

        # 5. Convert the raw TSV string into a Pandas DataFrame
        df = pd.read_csv(io.StringIO(raw_tsv_text), sep='\t')
        return df

    except Exception as e:
        print(f"An error occurred during communication with LM Studio: {e}")
        print("Please check that your local server is on and a Vision model is fully loaded.")
        return None

if __name__ == "__main__":
    
    # Execute extraction
    df = extract_table_with_local_lm_studio(IMAGE_FILE)
    
    if df is not None:
        print("\n--- Data successfully loaded into Pandas DataFrame via LM Studio ---")
        print(f"Shape: {df.shape[0]} rows x {df.shape[1]} columns\n")
        
        # Display the resulting DataFrame
        print(df.to_string())
        try:
            import pyperclip

            # Convert the dataframe to a clean TSV string explicitly
            tsv_string = df.to_csv(sep='\t', index=False)

            # Force copy the string to the clipboard via pyperclip
            pyperclip.copy(tsv_string)
            print("\n📋 Dataframe successfully forced to clipboard via Pyperclip!")
            print("Try pasting (Ctrl+V or Cmd+V) directly into Excel/Google Sheets now.")

        except Exception as e:
            print(f"\n❌ Clipboard copy failed: {e}")
            print("Please ensure you have xclip/xsel installed if you are on Linux.")
