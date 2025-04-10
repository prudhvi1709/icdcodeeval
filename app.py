# /// script
# requires-python = ">=3.9"
# dependencies = [
#     "pandas",
#     "httpx",
#     "python-dotenv",
#     "openpyxl"    
# ]
# ///
import os
import pandas as pd
import httpx
from dotenv import load_dotenv
from datetime import datetime

# Load environment variables from .env file
load_dotenv()

# API Endpoints
GPT4O_ENDPOINT = "https://llmfoundry.straive.com/openai/v1/chat/completions"
CLAUDE_ENDPOINT = "https://llmfoundry.straive.com/anthropic/v1/messages"
GEMINI_ENDPOINT = "https://llmfoundry.straive.com/gemini/v1beta/models/gemini-2.0-flash:generateContent"

# Use a single API token for all services
LLMFOUNDRY_TOKEN = os.getenv("LLMFOUNDRY_TOKEN")

def query_llm(model_type, description):
    """Generic function to query any LLM model with the given medical description"""
    try:
        prompt = f"Given the following medical description, return the most appropriate ICD-10 code:\n\"{description}\"\nRespond with only the ICD-10 code."
        
        # Model-specific configurations
        configs = {
            "gpt4o": {
                "endpoint": GPT4O_ENDPOINT,
                "headers": {
                    "Content-Type": "application/json",
                    "Authorization": f"Bearer {LLMFOUNDRY_TOKEN}"
                },
                "payload": {
                    "model": "gpt-4o-mini",
                    "messages": [{"role": "user", "content": prompt}],
                    "temperature": 0
                },
                "response_parser": lambda resp: resp["choices"][0]["message"]["content"].strip()
            },
            "claude": {
                "endpoint": CLAUDE_ENDPOINT,
                "headers": {
                    "Content-Type": "application/json",
                    "x-api-key": LLMFOUNDRY_TOKEN,
                    "anthropic-version": "2023-06-01"
                },
                "payload": {
                    "model": "claude-3-7-sonnet-20250219",
                    "max_tokens": 100,
                    "messages": [{"role": "user", "content": prompt}],
                    "temperature": 0
                },
                "response_parser": lambda resp: resp["content"][0]["text"].strip()
            },
            "gemini": {
                "endpoint": GEMINI_ENDPOINT,
                "headers": {
                    "Content-Type": "application/json",
                    "Authorization": f"Bearer {LLMFOUNDRY_TOKEN}"
                },
                "payload": {
                    "contents": [{
                        "role": "user",
                        "parts": [{"text": prompt}]
                    }],
                    "generationConfig": {
                        "temperature": 0,
                        "maxOutputTokens": 100
                    }
                },
                "response_parser": lambda resp: resp["candidates"][0]["content"]["parts"][0]["text"].strip()
            }
        }
        
        if model_type not in configs:
            raise ValueError(f"Unsupported model type: {model_type}")
            
        config = configs[model_type]
        response = httpx.post(
            config["endpoint"], 
            headers=config["headers"], 
            json=config["payload"], 
            timeout=30.0
        )
        response.raise_for_status()
        return config["response_parser"](response.json())
        
    except Exception as e:
        print(f"Error querying {model_type}: {str(e)}")
        return "ERROR"

def query_gpt4o(description):
    """Query GPT-4o-mini with the given medical description"""
    return query_llm("gpt4o", description)

def query_claude(description):
    """Query Claude 3.7 Sonnet with the given medical description"""
    return query_llm("claude", description)

def query_gemini(description):
    """Query Gemini 2.0 Flash with the given medical description"""
    return query_llm("gemini", description)

def calculate_partial_score(predicted_code, actual_code):
    """Calculate partial score based on the provided hierarchical rules."""
    try:
        # Handle error cases or missing predictions immediately
        if predicted_code == "ERROR" or not predicted_code or not actual_code:
            return 0.0
            
        # Clean the codes: remove dots and take the primary code part if delimited
        pred_clean = predicted_code.strip().split()[0].replace('.', '')
        actual_clean = actual_code.strip().split()[0].replace('.', '')
        
        # Rule 1: Exact Match (Score = 1.0)
        if pred_clean == actual_clean:
            return 1.0
            
        # Rule 2: Parent Code (Score = 0.1)
        # Check if predicted code is a proper prefix of the actual code
        if len(pred_clean) < len(actual_clean) and actual_clean.startswith(pred_clean):
            return 0.1
            
        # Rule 3: Grandparent Code (Score = 0.01)
        # Check if the first 3 characters match (requires at least 3 chars)
        if len(pred_clean) >= 3 and len(actual_clean) >= 3:
            if pred_clean[:3] == actual_clean[:3]:
                # Ensure it wasn't already covered by Rule 1 or 2
                # (This check is implicitly handled by the 'if' sequence)
                return 0.01
                
        # Rule 4: Invalid / Not Related (Score = 0.0)
        # If none of the above conditions are met
        return 0.0
        
    except Exception as e:
        print(f"Error calculating partial score for '{predicted_code}' vs '{actual_code}': {str(e)}")
        return 0.0

def evaluate_models():
    """Main function to evaluate the performance of LLMs on ICD-10 code prediction"""
    try:
        # Load the dataset
        print("Loading dataset...")
        df = pd.read_excel("icd-codes.xlsx")
        
        # Use a fixed random seed instead of timestamp
        fixed_seed = 42  # You can choose any integer value
        sample_df = df.sample(n=100, random_state=fixed_seed)
        print(f"Sampled 100 random entries from {len(df)} total entries")
        print(f"Using fixed random seed: {fixed_seed}")
        
        # Define model configurations
        models = [
            {"id": "gpt4o", "display_name": "GPT-4o-mini", "query_func": query_gpt4o},
            {"id": "claude", "display_name": "Claude 3.7 Sonnet", "query_func": query_claude},
            {"id": "gemini", "display_name": "Gemini 2.0 Flash", "query_func": query_gemini}
        ]
        
        # Initialize results dataframe columns
        result_columns = {"LONG DESCRIPTION": sample_df["LONG DESCRIPTION"], "ACTUAL CODE": sample_df["CODE"]}
        
        # Dynamically add columns for each model
        for model in models:
            display_name = model["display_name"]
            result_columns[f"{display_name} PREDICTION"] = ""
            result_columns[f"{display_name} CORRECT"] = False
            result_columns[f"{display_name} SCORE"] = 0.0
        
        results_df = pd.DataFrame(result_columns)
        
        # Process each description
        total_entries = len(sample_df)
        print(f"Processing {total_entries} entries...")
        
        for i, (idx, row) in enumerate(sample_df.iterrows()):
            description = row["LONG DESCRIPTION"]
            actual_code = row["CODE"]
            
            print(f"Processing entry {i+1}/{total_entries}: {description[:50]}...")
            
            # Process each model
            for model in models:
                display_name = model["display_name"]
                query_func = model["query_func"]
                
                # Get prediction
                prediction = query_func(description)
                results_df.at[idx, f"{display_name} PREDICTION"] = prediction
                
                # Check correctness
                actual_clean = actual_code.strip().split()[0].replace('.', '') if actual_code else ""
                pred_clean = prediction.strip().split()[0].replace('.', '') if prediction != "ERROR" and prediction else ""
                is_correct = (pred_clean == actual_clean) if pred_clean and actual_clean else False
                results_df.at[idx, f"{display_name} CORRECT"] = is_correct
                
                # Calculate score
                score = calculate_partial_score(prediction, actual_code)
                results_df.at[idx, f"{display_name} SCORE"] = score
        
        # Calculate summaries
        summary_data = {"Model": [], "Total Samples": [], "Exact Matches": [], "Total Score": []}
        
        print(f"\n===== EVALUATION SUMMARY (out of {total_entries} samples) =====")
        print("\n--- Exact Matches ---")
        
        for model in models:
            display_name = model["display_name"]
            correct_count = results_df[f"{display_name} CORRECT"].sum()
            total_score = results_df[f"{display_name} SCORE"].sum()
            
            print(f"{display_name}: {correct_count}")
            
            # Add to summary data
            summary_data["Model"].append(display_name)
            summary_data["Total Samples"].append(total_entries)
            summary_data["Exact Matches"].append(correct_count)
            summary_data["Total Score"].append(total_score)
        
        print("\n--- Total Score (with partial credit) ---")
        for model in models:
            display_name = model["display_name"]
            total_score = results_df[f"{display_name} SCORE"].sum()
            print(f"{display_name}: {total_score:.2f}")
        
        # Create summary dataframe
        summary_df = pd.DataFrame(summary_data)
        
        # Format the Total Score column
        summary_df["Total Score"] = summary_df["Total Score"].map('{:.2f}'.format)
        
        # Save results
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        output_file = f"icd_evaluation_results_{timestamp}.xlsx"
        
        # Save both sheets to Excel
        with pd.ExcelWriter(output_file) as writer:
            # Format score columns
            for model in models:
                display_name = model["display_name"]
                results_df[f"{display_name} SCORE"] = results_df[f"{display_name} SCORE"].map('{:.2f}'.format)
            
            results_df.to_excel(writer, sheet_name="Detailed Results", index=False)
            summary_df.to_excel(writer, sheet_name="Summary", index=False)
        
        print(f"\nResults saved to {output_file}")
        return output_file
        
    except Exception as e:
        print(f"Error in evaluation: {str(e)}")
        return None

if __name__ == "__main__":
    evaluate_models()
