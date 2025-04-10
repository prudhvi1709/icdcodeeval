import pandas as pd
import json
from datetime import datetime
import js

# API Endpoints
GPT4O_ENDPOINT = "https://llmfoundry.straive.com/openai/v1/chat/completions"
CLAUDE_ENDPOINT = "https://llmfoundry.straive.com/anthropic/v1/messages"
GEMINI_ENDPOINT = "https://llmfoundry.straive.com/gemini/v1beta/models/gemini-2.0-flash:generateContent"

# Global variables to store results
results_df = None
summary_df = None

async def query_llm(model_type, description, api_token):
    """Generic function to query any LLM model with the given medical description"""
    try:
        prompt = f"Given the following medical description, return the most appropriate ICD-10 code:\n\"{description}\"\nRespond with only the ICD-10 code."
        
        # Model-specific configurations
        configs = {
            "gpt4o": {
                "endpoint": GPT4O_ENDPOINT,
                "headers": {
                    "Content-Type": "application/json",
                    "Authorization": f"Bearer {api_token}"
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
                    "x-api-key": api_token,
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
                    "Authorization": f"Bearer {api_token}"
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
        
        # In browser, we use the fetch API instead of httpx
        import pyodide.http
        response = await pyodide.http.pyfetch(
            config["endpoint"],
            method="POST",
            headers=config["headers"],
            body=json.dumps(config["payload"])
        )
        
        # Check status
        if response.status != 200:
            error_text = await response.text()
            js.console.error(f"Error querying {model_type}: {error_text}")
            return "ERROR"
            
        # Parse response
        json_response = await response.json()
        return config["response_parser"](json_response)
        
    except Exception as e:
        js.console.error(f"Error querying {model_type}: {str(e)}")
        return "ERROR"

async def query_gpt4o(description, api_token):
    """Query GPT-4o-mini with the given medical description"""
    return await query_llm("gpt4o", description, api_token)

async def query_claude(description, api_token):
    """Query Claude 3.7 Sonnet with the given medical description"""
    return await query_llm("claude", description, api_token)

async def query_gemini(description, api_token):
    """Query Gemini 2.0 Flash with the given medical description"""
    return await query_llm("gemini", description, api_token)

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
        js.console.error(f"Error calculating partial score for '{predicted_code}' vs '{actual_code}': {str(e)}")
        return 0.0

def update_status(message):
    """Update the status message in the browser"""
    js.document.getElementById('status').innerHTML = message

async def evaluate_models_browser(api_token, sample_size, use_gpt4, use_claude, use_gemini):
    """Main function to evaluate the performance of LLMs on ICD-10 code prediction in browser"""
    global results_df, summary_df
    
    try:
        # Load the dataset
        update_status("Loading dataset...")
        df = pd.read_excel("icd-codes.xlsx")
        
        # Use a fixed random seed instead of timestamp
        fixed_seed = 42
        sample_df = df.sample(n=sample_size, random_state=fixed_seed)
        update_status(f"Sampled {sample_size} random entries from {len(df)} total entries")
        
        # Define model configurations
        models = []
        if use_gpt4:
            models.append({"id": "gpt4o", "display_name": "GPT-4o-mini", "query_func": query_gpt4o})
        if use_claude:
            models.append({"id": "claude", "display_name": "Claude 3.7 Sonnet", "query_func": query_claude})
        if use_gemini:
            models.append({"id": "gemini", "display_name": "Gemini 2.0 Flash", "query_func": query_gemini})
        
        # Initialize results dataframe columns
        result_columns = {"LONG DESCRIPTION": sample_df["LONG DESCRIPTION"].tolist(), "ACTUAL CODE": sample_df["CODE"].tolist()}
        
        # Dynamically add columns for each model
        for model in models:
            display_name = model["display_name"]
            result_columns[f"{display_name} PREDICTION"] = [""] * len(sample_df)
            result_columns[f"{display_name} CORRECT"] = [False] * len(sample_df)
            result_columns[f"{display_name} SCORE"] = [0.0] * len(sample_df)
        
        results_df = pd.DataFrame(result_columns)
        
        # Process each description
        total_entries = len(sample_df)
        update_status(f"Processing {total_entries} entries...")
        
        for i, (idx, row) in enumerate(sample_df.iterrows()):
            description = row["LONG DESCRIPTION"]
            actual_code = row["CODE"]
            
            row_index = i  # For storing in results_df
            status_msg = f"Processing entry {i+1}/{total_entries}: {description[:50]}..."
            update_status(status_msg)
            
            # Process each model
            for model in models:
                display_name = model["display_name"]
                query_func = model["query_func"]
                
                # Get prediction
                prediction = await query_func(description, api_token)
                results_df.at[row_index, f"{display_name} PREDICTION"] = prediction
                
                # Check correctness
                actual_clean = actual_code.strip().split()[0].replace('.', '') if actual_code else ""
                pred_clean = prediction.strip().split()[0].replace('.', '') if prediction != "ERROR" and prediction else ""
                is_correct = (pred_clean == actual_clean) if pred_clean and actual_clean else False
                results_df.at[row_index, f"{display_name} CORRECT"] = is_correct
                
                # Calculate score
                score = calculate_partial_score(prediction, actual_code)
                results_df.at[row_index, f"{display_name} SCORE"] = score
        
        # Calculate summaries
        summary_data = {"Model": [], "Total Samples": [], "Exact Matches": [], "Total Score": []}
        
        update_status(f"Evaluation complete. Processing results...")
        
        for model in models:
            display_name = model["display_name"]
            correct_count = results_df[f"{display_name} CORRECT"].sum()
            total_score = results_df[f"{display_name} SCORE"].sum()
            
            # Add to summary data
            summary_data["Model"].append(display_name)
            summary_data["Total Samples"].append(total_entries)
            summary_data["Exact Matches"].append(int(correct_count))
            summary_data["Total Score"].append(f"{total_score:.2f}")
        
        # Create summary dataframe
        summary_df = pd.DataFrame(summary_data)
        
        # Prepare data for display in JavaScript
        # Create a clean dictionary for JSON serialization
        detailed_results = results_df.to_dict(orient='records')
        columns = results_df.columns.tolist()
        
        # Return the results as a JSON string
        return json.dumps({
            "data": detailed_results,
            "columns": columns,
            "summary": summary_df.to_dict(orient='records')
        })
        
    except Exception as e:
        error_message = f"Error in evaluation: {str(e)}"
        js.console.error(error_message)
        update_status(error_message)
        return json.dumps({"error": error_message}) 