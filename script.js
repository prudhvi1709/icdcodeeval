// Global variables
let pyodide;
let pythonCode;

// Initialize Pyodide
async function initPyodide() {
    pyodide = await loadPyodide();
    
    // First, load micropip
    await pyodide.loadPackage("micropip");
    
    // Now we can use micropip to install other packages
    await pyodide.runPythonAsync(`
import micropip
await micropip.install(['pandas', 'httpx', 'pytz', 'openpyxl'])
    `);
    
    document.getElementById('status').innerHTML = "Pyodide loaded. Ready to start evaluation.";
    document.getElementById('loading-spinner').style.display = 'none';
}

// Fetch the Python code
async function fetchPythonCode() {
    try {
        document.getElementById('loading-spinner').style.display = 'inline-block';
        document.getElementById('status').innerHTML = "Loading Pyodide environment...";
        
        const response = await fetch('icd_predictor.py');
        pythonCode = await response.text();
        
        await initPyodide();
        
        // Register the Python code as a module
        pyodide.runPython(`
import sys
from pathlib import Path

# Create module file in the virtual filesystem
module_name = "icd_predictor"
module_path = Path(f"{module_name}.py")

with open(module_path, "w") as f:
    f.write(${JSON.stringify(pythonCode)})

# Make sure the module can be imported
if module_name not in sys.modules:
    sys.path.insert(0, ".")
        `);
        
        // Verify the module can be imported
        pyodide.runPython(`
import icd_predictor
print("icd_predictor module successfully imported")
        `);
        
        document.getElementById('status').innerHTML = "Python module loaded. Ready to start evaluation.";
        
    } catch (error) {
        console.error("Error loading Python code:", error);
        document.getElementById('status').innerHTML = `Error loading Python code: ${error.message}`;
        document.getElementById('loading-spinner').style.display = 'none';
    }
}

// Read Excel file and convert to Python-readable format
async function readExcelFile(file) {
    return new Promise((resolve, reject) => {
        const reader = new FileReader();
        reader.onload = (event) => {
            const arrayBuffer = event.target.result;
            resolve(new Uint8Array(arrayBuffer));
        };
        reader.onerror = (error) => {
            reject(error);
        };
        reader.readAsArrayBuffer(file);
    });
}

// Start the evaluation process
async function startEvaluation() {
    const apiToken = document.getElementById('api-token').value;
    const fileInput = document.getElementById('csv-file');
    const sampleSize = parseInt(document.getElementById('sample-size').value);
    
    const useGpt4 = document.getElementById('use-gpt4').checked;
    const useClaude = document.getElementById('use-claude').checked;
    const useGemini = document.getElementById('use-gemini').checked;
    
    // Validation checks
    if (!apiToken) {
        alert("Please enter your LLM Foundry API token");
        return;
    }
    
    if (!fileInput.files.length) {
        alert("Please upload an Excel file with ICD-10 codes");
        return;
    }
    
    if (sampleSize < 1 || sampleSize > 100) {
        alert("Sample size must be between 1 and 100");
        return;
    }
    
    if (!useGpt4 && !useClaude && !useGemini) {
        alert("Please select at least one model to evaluate");
        return;
    }
    
    try {
        // UI updates
        document.getElementById('loading-spinner').style.display = 'inline-block';
        document.getElementById('status').innerHTML = "Processing data...";
        document.getElementById('start-evaluation').disabled = true;
        
        // Read the Excel file
        const file = fileInput.files[0];
        const fileData = await readExcelFile(file);
        
        // Store the file in Pyodide's virtual filesystem
        pyodide.FS.writeFile('icd-codes.xlsx', fileData);
        
        // Set API token and sample size in Python
        pyodide.globals.set('api_token', apiToken);
        pyodide.globals.set('sample_size', sampleSize);
        pyodide.globals.set('use_gpt4', useGpt4);
        pyodide.globals.set('use_claude', useClaude);
        pyodide.globals.set('use_gemini', useGemini);
        
        // Run the evaluation
        const result = await pyodide.runPythonAsync(`
            import icd_predictor
            icd_predictor.evaluate_models_browser(api_token, sample_size, use_gpt4, use_claude, use_gemini)
        `);
        
        // Process and display results
        const results = JSON.parse(result);
        displayResults(results);
        
        // UI updates
        document.getElementById('loading-spinner').style.display = 'none';
        document.getElementById('status').innerHTML = "Evaluation completed successfully!";
        document.getElementById('start-evaluation').disabled = false;
        document.getElementById('export-results').style.display = 'inline-block';
        
        // Show the results cards
        document.getElementById('summary-card').classList.remove('d-none');
        document.getElementById('results-card').classList.remove('d-none');
        
    } catch (error) {
        console.error("Error during evaluation:", error);
        document.getElementById('loading-spinner').style.display = 'none';
        document.getElementById('status').innerHTML = `Error during evaluation: ${error.message}`;
        document.getElementById('start-evaluation').disabled = false;
    }
}

// Display results in HTML tables
function displayResults(results) {
    // Display summary results
    const summaryTable = document.getElementById('summary-table');
    const summaryBody = document.getElementById('summary-body');
    summaryBody.innerHTML = '';
    
    results.summary.forEach(row => {
        const tr = document.createElement('tr');
        tr.innerHTML = `
            <td>${row.Model}</td>
            <td>${row['Total Samples']}</td>
            <td>${row['Exact Matches']}</td>
            <td>${row['Total Score']}</td>
        `;
        summaryBody.appendChild(tr);
    });
    
    summaryTable.style.display = 'table';
    
    // Display detailed results
    const resultsTable = document.getElementById('results-table');
    const resultsHeader = document.getElementById('results-header');
    const resultsBody = document.getElementById('results-body');
    
    // Create header
    resultsHeader.innerHTML = '';
    const headerRow = document.createElement('tr');
    const columns = results.columns;
    
    columns.forEach(column => {
        const th = document.createElement('th');
        th.textContent = column;
        headerRow.appendChild(th);
    });
    
    resultsHeader.appendChild(headerRow);
    
    // Create body
    resultsBody.innerHTML = '';
    results.data.forEach(row => {
        const tr = document.createElement('tr');
        
        columns.forEach(column => {
            const td = document.createElement('td');
            
            // Special formatting for boolean values
            if (typeof row[column] === 'boolean') {
                td.innerHTML = row[column] ? 
                    '<span class="badge bg-success">Yes</span>' : 
                    '<span class="badge bg-danger">No</span>';
            } else {
                td.textContent = row[column];
            }
            
            tr.appendChild(td);
        });
        
        resultsBody.appendChild(tr);
    });
    
    resultsTable.style.display = 'table';
}

// Export results to CSV
function exportToCsv() {
    // Use Pyodide to generate CSV and download it
    pyodide.runPythonAsync(`
        import pandas as pd
        import js
        from pyodide.ffi import create_proxy
        
        # Create DataFrame from the results
        df = pd.DataFrame(results_df)
        
        # Convert to CSV
        csv_data = df.to_csv(index=False)
        
        # Create a JavaScript function to trigger download
        def download_csv(csv_data):
            # Create a Blob containing the data
            blob = js.Blob.new([csv_data], {type: 'text/csv'})
            
            # Create a link element
            link = js.document.createElement('a')
            url = js.URL.createObjectURL(blob)
            link.href = url
            link.download = 'icd_evaluation_results.csv'
            
            # Add to document, click and remove
            js.document.body.appendChild(link)
            link.click()
            js.document.body.removeChild(link)
        
        # Call the function
        download_csv(csv_data)
    `);
}

// Initialize event listeners
document.addEventListener('DOMContentLoaded', async () => {
    // Load Python code
    await fetchPythonCode();
    
    // Set up event listeners
    document.getElementById('start-evaluation').addEventListener('click', startEvaluation);
    document.getElementById('export-results').addEventListener('click', exportToCsv);
}); 