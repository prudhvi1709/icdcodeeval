# ICD-10 Code Prediction using LLMs

## Overview
This project utilizes various Large Language Models (LLMs) to predict ICD-10 codes based on medical descriptions. The script `app.py` implements a framework to query different LLMs, evaluate their performance, and save the results in an Excel file.

## Requirements
- Python 3.9 or higher
- Required Python packages:
  - pandas
  - httpx
  - python-dotenv
  - openpyxl

## Installation
1. Clone the repository:
   ```bash
   git clone <repository-url>
   cd <repository-directory>
   ```

2. Run the file:
   ```bash
   uv run app.py
   ```

3. Create a `.env` file in the root directory and add your API token:
   ```plaintext
   LLMFOUNDRY_TOKEN=your_api_token_here
   ```

The script will load a dataset of medical descriptions, query the LLMs, and output the results to an Excel file.

## Functions
- `query_llm(model_type, description)`: Queries the specified LLM with a medical description and returns the predicted ICD-10 code.
- `query_gpt4o(description)`: Queries the GPT-4o-mini model.
- `query_claude(description)`: Queries the Claude 3.7 Sonnet model.
- `query_gemini(description)`: Queries the Gemini 2.0 Flash model.
- `calculate_partial_score(predicted_code, actual_code)`: Calculates a score based on the accuracy of the predicted ICD-10 code.
- `evaluate_models()`: Main function that orchestrates the evaluation of the models and saves the results.

## Output
The results will be saved in an Excel file named `icd_evaluation_results_<timestamp>.xlsx`, containing detailed results and a summary of the model performances.

