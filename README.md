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
git clone https://github.com/yourusername/request_trimmer.git
cd request_trimmer

# Install the package
pip install -e .
```

Alternatively, you can use the tool without installation:

```bash
# Run directly using the wrapper script
python trim_request.py request.txt
```

## Usage

### Command Line Interface

```bash
# Basic usage
request-trimmer request.txt

# Save output to a file
request-trimmer request.txt -o trimmed_request.txt

# Generate a trimming report
request-trimmer request.txt --report

# Enable INFO level logging
request-trimmer request.txt --debug

# Enable verbose (DEBUG level) logging
request-trimmer request.txt --verbose

# Specify a base URL (if not present in the request)
request-trimmer request.txt --base-url https://example.com

# Set length tolerance (in bytes) for response comparison
request-trimmer request.txt --length-tolerance 50

# Only trim specific components
request-trimmer request.txt --headers-only
request-trimmer request.txt --cookies-only
request-trimmer request.txt --query-params-only
```

### Python API

```python
from request_trimmer.main import RequestTrimmer

# Read raw request from file
with open('request.txt', 'r') as f:
    raw_request = f.read()

# Create a RequestTrimmer instance
trimmer = RequestTrimmer(
    raw_request,
    length_tolerance=10,  # Maximum allowed difference in response length (in bytes)
    timeout=10,  # Timeout for HTTP requests in seconds
    trim_headers=True,  # Whether to trim headers
    trim_cookies=True,  # Whether to trim cookies
    trim_query_params=True  # Whether to trim query parameters
)

# Trim the request
trimmed_request = trimmer.trim_request()

# Get a report of the trimming process
report = trimmer.get_trimming_report()

# Print the trimmed request
print(trimmed_request)
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
