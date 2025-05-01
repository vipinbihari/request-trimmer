import requests
import time
import logging
import argparse
import os
import sys
from typing import Optional, Tuple, Dict

from utils import (
    parse_request, derive_base_url, 
    get_request_counter, increment_request_counter, log_function_call, 
    reset_request_counter
)
from header_trimmer import HeaderTrimmer
from cookie_trimmer import CookieTrimmer
from query_trimmer import QueryTrimmer

# Configure logging at the module level
logger = logging.getLogger(__name__)


class RequestTrimmer:
    def __init__(self, raw_request: str, base_url: Optional[str] = None, length_tolerance: int = 50, 
                 timeout: int = 10, trim_headers: bool = True,
                 trim_cookies: bool = True, trim_query_params: bool = True):
        """
        Initialize the RequestTrimmer.
        
        Args:
            raw_request: Raw HTTP request
            base_url: Base URL for the request (optional, will be derived if not provided)
            length_tolerance: Maximum allowed difference in response length (in bytes)
            timeout: Timeout for HTTP requests in seconds
            trim_headers: Whether to trim headers
            trim_cookies: Whether to trim cookies
            trim_query_params: Whether to trim query parameters
        """
        logger.info("Initializing RequestTrimmer")
        self.raw_request = raw_request
        logger.debug(f"Raw request length: {len(raw_request)} characters")
        
        # Derive base URL if not provided
        if not base_url:
            logger.debug("Deriving base URL from request")
            self.base_url = derive_base_url(raw_request)
            logger.info(f"Derived base URL: {self.base_url}")
        else:
            self.base_url = base_url
            logger.info(f"Using provided base URL: {self.base_url}")
            
        self.length_tolerance = length_tolerance
        self.timeout = timeout
        self.trim_headers = trim_headers
        self.trim_cookies = trim_cookies
        self.trim_query_params = trim_query_params
        
        logger.debug(f"Parameters: length_tolerance={length_tolerance}, timeout={timeout}")
        logger.debug(f"Modules: trim_headers={trim_headers}, trim_cookies={trim_cookies}, trim_query_params={trim_query_params}")
    
    @log_function_call
    def _get_initial_baseline_response(self) -> requests.Response:
        """
        Sends the initial raw request to establish the baseline response.
        """
        logger.info("Establishing initial baseline response...")
        method, path, headers, payload = parse_request(self.raw_request)
        url = f"{self.base_url}{path}"

        logger.debug(f"Sending baseline request: {method} {url}")
        start_time = time.time()
        try:
            increment_request_counter() # Count this baseline request
            response = requests.request(
                method=method,
                url=url,
                headers=headers,
                data=payload,
                timeout=self.timeout,
                allow_redirects=False
            )
            end_time = time.time()
            logger.debug(f"Baseline request completed in {end_time - start_time:.2f} seconds with status code {response.status_code}")
            logger.debug(f"Baseline response length: {len(response.content)} bytes")
            # Perform a basic check on the baseline response
            if response.status_code >= 400:
                 logger.warning(f"Baseline request resulted in status code {response.status_code}. Trimming results may be unreliable.")
            return response
        except requests.exceptions.Timeout:
            logger.error(f"Baseline request timed out after {self.timeout} seconds. Cannot proceed with trimming.")
            raise
        except requests.exceptions.RequestException as e:
            logger.error(f"Baseline request failed: {str(e)}. Cannot proceed with trimming.")
            raise

    @log_function_call
    def trim_request(self) -> str:
        """
        Trim the HTTP request by removing unnecessary headers, cookies, and query parameters sequentially.

        Returns:
            Trimmed raw HTTP request as a string
        """
        logger.info("Starting sequential request trimming process")
        reset_request_counter() # Reset counter at the start of the process

        # --- Step 0: Establish Baseline ---
        try:
            baseline_response = self._get_initial_baseline_response()
        except Exception as e:
             logger.error(f"Failed to get baseline response: {e}. Aborting trim.")
             # Return the original request if baseline fails, maybe add an option?
             return self.raw_request

        # Initialize the request to be modified
        current_request = self.raw_request
        logger.debug(f"Initial request length: {len(current_request)}")

        # --- Step 1: Trim Headers ---
        if self.trim_headers:
            logger.info("Step 1: Trimming headers...")
            try:
                header_trimmer = HeaderTrimmer(
                    self.base_url,
                    current_request, # Start with the current request
                    baseline_response, # Pass the single baseline response
                    self.length_tolerance,
                    self.timeout
                )
                # find_unnecessary_items returns the *new* trimmed request string
                current_request = header_trimmer.find_unnecessary_items()
                logger.info("Header trimming completed.")
                logger.debug(f"Request after header trim length: {len(current_request)}")
            except Exception as e:
                logger.error(f"Error during header trimming: {e}. Skipping header trimming.")
        else:
            logger.info("Skipping header trimming as requested.")

        # --- Step 2: Trim Cookies ---
        # Pass the request *after* header trimming (if done)
        if self.trim_cookies:
            logger.info("Step 2: Trimming cookies...")
            try:
                cookie_trimmer = CookieTrimmer(
                    self.base_url,
                    current_request, # Use request potentially modified by header trimmer
                    baseline_response,
                    self.length_tolerance,
                    self.timeout
                )
                current_request = cookie_trimmer.find_unnecessary_items()
                logger.info("Cookie trimming completed.")
                logger.debug(f"Request after cookie trim length: {len(current_request)}")
            except Exception as e:
                 logger.error(f"Error during cookie trimming: {e}. Skipping cookie trimming.")
        else:
            logger.info("Skipping cookie trimming as requested.")

        # --- Step 3: Trim Query Parameters ---
        # Pass the request *after* header and cookie trimming (if done)
        if self.trim_query_params:
            logger.info("Step 3: Trimming query parameters...")
            try:
                query_trimmer = QueryTrimmer(
                    self.base_url,
                    current_request, # Use request potentially modified by previous steps
                    baseline_response,
                    self.length_tolerance,
                    self.timeout
                )
                current_request = query_trimmer.find_unnecessary_items()
                logger.info("Query parameter trimming completed.")
                logger.debug(f"Request after query param trim length: {len(current_request)}")
            except Exception as e:
                 logger.error(f"Error during query parameter trimming: {e}. Skipping query parameter trimming.")

        else:
            logger.info("Skipping query parameter trimming as requested.")

        # --- Finalization ---
        final_trimmed_request = current_request
        total_requests = get_request_counter()
        logger.info(f"Sequential request trimming completed. Final request length: {len(final_trimmed_request)}")
        logger.info(f"Total HTTP requests made (including baseline): {total_requests}")

        return final_trimmed_request
    
    def generate_report(self, trimmed_request: str) -> Dict[str, Dict[str, int]]:
        """
        Generate a report of the trimming process.
        
        Args:
            trimmed_request: The trimmed HTTP request
            
        Returns:
            Dictionary containing the report
        """
        logger.info("Generating trimming report")
        
        # Parse headers from raw and trimmed requests
        raw_headers = parse_request(self.raw_request)[2]
        trimmed_headers = parse_request(trimmed_request)[2]
        
        # Determine which headers were removed
        unnecessary_headers = set(raw_headers.keys()) - set(trimmed_headers.keys())
        
        # Parse cookies from raw and trimmed requests
        raw_cookies = raw_headers.get('Cookie', '')
        trimmed_cookies = trimmed_headers.get('Cookie', '')
        
        # Determine which cookies were removed
        unnecessary_cookies = set(raw_cookies.split('; ')) - set(trimmed_cookies.split('; '))
        necessary_cookies = set(trimmed_cookies.split('; '))
        
        # Parse query parameters from raw and trimmed requests
        _, raw_path, _ = parse_request(self.raw_request)
        _, trimmed_path, _ = parse_request(trimmed_request)
        
        raw_params = raw_path.split('?')[1].split('&') if '?' in raw_path else []
        trimmed_params = trimmed_path.split('?')[1].split('&') if '?' in trimmed_path else []
        
        # Determine which parameters were removed
        unnecessary_params = set(raw_params) - set(trimmed_params)
        necessary_params = set(trimmed_params)
        
        # Get the total number of HTTP requests made
        total_requests = get_request_counter()
        
        # Create report
        report = {
            "original": {
                "size": len(self.raw_request),
                "headers_count": len(raw_headers),
                "cookies_count": len(raw_cookies.split('; ')),
                "query_params_count": len(raw_params)
            },
            "trimmed": {
                "size": len(trimmed_request),
                "headers_count": len(trimmed_headers),
                "cookies_count": len(necessary_cookies),
                "query_params_count": len(necessary_params)
            },
            "unnecessary": {
                "headers": list(unnecessary_headers),
                "cookies": list(unnecessary_cookies),
                "query_params": list(unnecessary_params)
            },
            "performance": {
                "total_http_requests": total_requests
            }
        }
        logger.debug(f"Report generated: {report}")
        return report

def main():
    parser = argparse.ArgumentParser(description='Trims unnecessary headers, cookies, and query parameters from a raw HTTP request.')
    parser.add_argument('request_file', help='Path to the raw HTTP request file.')
    parser.add_argument('-o', '--output', help='Path to save the trimmed request file.')
    parser.add_argument('--base-url', help='Base URL (e.g., https://example.com) if not inferrable from Host header.')
    parser.add_argument('-v', '--verbose', action='store_true', help='Enable verbose logging (INFO level).')
    parser.add_argument('-d', '--debug', action='store_true', help='Enable debug logging (DEBUG level).')
    parser.add_argument('--report', action='store_true', help='Print a summary report of trimmed items.')
    parser.add_argument('--length-tolerance', type=int, default=50, help='Byte tolerance for response length comparison.')
    parser.add_argument('--timeout', type=int, default=10, help='Request timeout in seconds.')
    parser.add_argument('--no-trim-headers', dest='trim_headers', action='store_false', help='Disable header trimming.')
    parser.add_argument('--no-trim-cookies', dest='trim_cookies', action='store_false', help='Disable cookie trimming.')
    parser.add_argument('--no-trim-query-params', dest='trim_query_params', action='store_false', help='Disable query parameter trimming.')
    # Options to trim only specific parts (can be combined)
    parser.add_argument('--headers-only', action='store_true', help='Only trim headers.')
    parser.add_argument('--cookies-only', action='store_true', help='Only trim cookies.')
    parser.add_argument('--query-params-only', action='store_true', help='Only trim query parameters.')

    args = parser.parse_args()

    # --- Logging Setup ---
    log_level = logging.WARNING  # Default level
    if args.debug:
        log_level = logging.DEBUG
    elif args.verbose: # Debug implies verbose
        log_level = logging.INFO

    # Get the root logger and set its level
    # This affects all loggers unless they have their own level set
    logging.getLogger().setLevel(log_level) 
    # Alternatively, set level only for this specific module's logger:
    # logger.setLevel(log_level)

    logger.info(f"Starting request_trimmer with log level: {logging.getLevelName(log_level)}")
    logger.debug(f"Command line arguments: {args}")

    # --- Determine which parts to trim --- 
    trim_headers_flag = args.trim_headers
    trim_cookies_flag = args.trim_cookies
    trim_query_params_flag = args.trim_query_params

    # Handle mutually exclusive flags if only one type is requested
    only_flags_set = args.headers_only or args.cookies_only or args.query_params_only
    if only_flags_set:
        trim_headers_flag = args.headers_only
        trim_cookies_flag = args.cookies_only
        trim_query_params_flag = args.query_params_only
        logger.info(f"Running in specific mode: Headers={trim_headers_flag}, Cookies={trim_cookies_flag}, QueryParams={trim_query_params_flag}")


    # --- Read Request File ---
    logger.info(f"Reading request file: {args.request_file}")
    try:
        with open(args.request_file, 'r', encoding='utf-8') as f:
            raw_request = f.read()
        logger.debug(f"Read {len(raw_request)} characters from request file")
    except FileNotFoundError:
        logger.error(f"Error: Request file not found at {args.request_file}")
        sys.exit(1)
    except Exception as e:
        logger.error(f"Error reading request file: {e}")
        sys.exit(1)

    # --- Initialize and Run Trimmer ---
    logger.info("Creating RequestTrimmer instance")
    reset_request_counter() # Reset counter for this run
    try:
        trimmer = RequestTrimmer(
            raw_request=raw_request,
            base_url=args.base_url,
            length_tolerance=args.length_tolerance,
            timeout=args.timeout,
            trim_headers=trim_headers_flag,
            trim_cookies=trim_cookies_flag,
            trim_query_params=trim_query_params_flag
        )
        
        trimmed_request = trimmer.trim_request()

        print("\nTrimmed request:")
        print(trimmed_request)

        if args.output:
            logger.info(f"Saving trimmed request to: {args.output}")
            try:
                with open(args.output, 'w', encoding='utf-8') as f:
                    f.write(trimmed_request)
            except Exception as e:
                logger.error(f"Error writing output file: {e}")
        
        if args.report:
             # Placeholder for report generation if needed later
             logger.info("Report generation requested (feature placeholder).")

    except Exception as e:
        # Catch potential errors during trimming initialization or process
        logger.error(f"An error occurred during trimming: {e}", exc_info=args.debug) # Show traceback if debug
        sys.exit(1)
    finally:
        # Always report the number of requests made
        logger.info(f"Total HTTP requests made: {get_request_counter()}")

if __name__ == "__main__":
    main()
