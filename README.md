# Request Trimmer

Request Trimmer is a Python tool that automatically identifies and removes unnecessary headers, cookies, and query parameters from HTTP requests. It uses a divide and conquer approach to efficiently test multiple parameters at once, making it much faster than testing each parameter individually.

## Features

- Automatically identifies unnecessary HTTP headers
- Automatically identifies unnecessary cookies
- Automatically identifies unnecessary query parameters
- Uses divide and conquer algorithm for efficient testing
- Optimized to avoid redundant HTTP requests
- Logical inference for pairs of items to reduce HTTP requests
- Detailed logging for debugging and auditing
- Generates detailed reports of trimming results

## Installation

```bash
# Clone the repository
git clone https://github.com/your-username/request-trimmer.git # Replace with actual URL
cd request-trimmer

# (Optional but recommended) Create and activate a virtual environment
python3 -m venv venv
source venv/bin/activate # On Windows use `venv\Scripts\activate`

# Install dependencies
pip install -r requirements.txt
```

## Usage

Run the tool from the project's root directory using the `run_trimmer.py` script:

```bash
python3 run_trimmer.py <request_file_path> [options]
```

Alternatively, you can run `main.py` directly:

```bash
python3 main.py <request_file_path> [options]
```

### Arguments and Options

*   `request_file` (Required): Path to the file containing the raw HTTP request.
*   `-o`, `--output`: Path to save the trimmed request file. If omitted, the trimmed request is printed to standard output.
*   `--base-url`: Specify the base URL (e.g., `https://example.com`) if it cannot be reliably inferred from the `Host` header in the request file.
*   `-v`, `--verbose`: Enable verbose logging (INFO level). Shows major steps and decisions.
*   `-d`, `--debug`: Enable debug logging (DEBUG level). Shows detailed internal operations, including timings and individual request outcomes. Implies verbose.
*   `--report`: Print a summary report of trimmed items after processing (currently a placeholder).
*   `--length-tolerance <bytes>`: Set the tolerance (in bytes) for comparing response lengths. Responses are considered equivalent if their lengths differ by this amount or less. Default: `50`.
*   `--timeout <seconds>`: Set the timeout for individual HTTP requests during trimming. Default: `10`.
*   `--no-trim-headers`: Disable the header trimming step.
*   `--no-trim-cookies`: Disable the cookie trimming step.
*   `--no-trim-query-params`: Disable the query parameter trimming step.
*   `--headers-only`: Shortcut to only trim headers (equivalent to `--no-trim-cookies --no-trim-query-params`).
*   `--cookies-only`: Shortcut to only trim cookies (equivalent to `--no-trim-headers --no-trim-query-params`).
*   `--query-params-only`: Shortcut to only trim query parameters (equivalent to `--no-trim-headers --no-trim-cookies`).

### Examples

1.  **Basic trimming (Headers, Cookies, Query Params) and print to console:**

    ```bash
    python3 run_trimmer.py /path/to/your/request.txt
    ```

2.  **Trim and save the result to a file:**

    ```bash
    python3 run_trimmer.py request.txt -o trimmed_request.txt
    ```

3.  **Trim with verbose logging and increased length tolerance:**

    ```bash
    python3 run_trimmer.py request.txt -v --length-tolerance 100
    ```

4.  **Trim only Headers:**

    ```bash
    python3 run_trimmer.py request.txt --headers-only
    ```

5.  **Trim only Query Parameters and Cookies (disable Header trimming):**

    ```bash
    python3 run_trimmer.py request.txt --no-trim-headers
    ```

6.  **Trim with debug logging and specify a base URL:**

    ```bash
    python3 run_trimmer.py request_no_host.txt --base-url https://api.example.com -d
    ```

7.  **Trim Query Parameters only and save output:**

    ```bash
    python3 run_trimmer.py request.txt --query-params-only -o trimmed_query_only.txt
    ```

## How It Works

The Request Trimmer uses a divide and conquer approach to efficiently identify unnecessary elements:

1. It first sends the original request to establish a baseline response.
2. It then divides the headers/cookies/query parameters into groups and tests removing each group.
3. If removing a group doesn't change the response, all elements in that group are unnecessary.
4. If removing a group does change the response, it recursively tests smaller subgroups.
5. For groups of exactly two items, it uses logical inference to avoid redundant requests:
   - If removing both items breaks the response, but removing one does not, the other item is automatically inferred as necessary.
6. Once an item is identified as unnecessary, it is excluded from all subsequent test requests.
7. This approach is much more efficient than testing each element individually.

## Response Comparison

Requests are considered equivalent if:
- They have the same HTTP status code
- Their response content length is within the specified tolerance (default: 10 bytes)

## Example

Original request:
```
POST /api/endpoint?param1=value1&param2=value2&unnecessary=value HTTP/2
Host: example.com
Cookie: necessary=value; unnecessary=value
Content-Length: 100
User-Agent: Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/135.0.0.0 Safari/537.36
Content-Type: application/json
Unnecessary-Header: value

{"data": "payload"}
```

Trimmed request:
```
POST /api/endpoint?param1=value1&param2=value2 HTTP/2
Host: example.com
Cookie: necessary=value
Content-Length: 100
User-Agent: Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/135.0.0.0 Safari/537.36
Content-Type: application/json

{"data": "payload"}
```

## Requirements

- Python 3.6 or higher
- requests library

## Logging

The tool provides three levels of logging:
- Default: Only warnings and errors are shown
- `--debug`: Shows INFO level logs (useful for understanding what's happening)
- `--verbose`: Shows DEBUG level logs (very detailed, useful for troubleshooting)

All logs are also written to `request_trimmer.log` regardless of the console output level.

## License

MIT
