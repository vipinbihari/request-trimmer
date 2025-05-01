import argparse
import sys
import logging
import time
from typing import Dict, List, Tuple, Any, Optional, Set
import requests
from .header_trimmer import HeaderTrimmer
from .cookie_trimmer import CookieTrimmer
from .query_trimmer import QueryTrimmer
from .utils import logger, derive_base_url, parse_headers, parse_cookies, parse_query_params, parse_request, log_function_call, reset_request_counter, get_request_counter, increment_request_counter

class RequestTrimmer:
    def __init__(self, raw_request: str, base_url: Optional[str] = None, length_tolerance: int = 10, 
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
    
    def generate_report(self, trimmed_request: str) -> Dict[str, Any]:
        """
        Generate a report of the trimming process.
        
        Args:
            trimmed_request: The trimmed HTTP request
            
        Returns:
            Dictionary containing the report
        """
        logger.info("Generating trimming report")
        
        # Parse headers from raw and trimmed requests
        raw_headers = parse_headers('\n'.join([line for line in self.raw_request.split('\n') 
                                              if ': ' in line and not line.startswith('PAYLOAD')]))
        trimmed_headers = parse_headers('\n'.join([line for line in trimmed_request.split('\n') 
                                                 if ': ' in line]))
        
        # Determine which headers were removed
        unnecessary_headers = set(raw_headers.keys()) - set(trimmed_headers.keys())
        
        # Parse cookies from raw and trimmed requests
        raw_cookies = parse_cookies(raw_headers.get('Cookie', ''))
        trimmed_cookies = parse_cookies(trimmed_headers.get('Cookie', ''))
        
        # Determine which cookies were removed
        unnecessary_cookies = set(raw_cookies.keys()) - set(trimmed_cookies.keys())
        necessary_cookies = set(trimmed_cookies.keys())
        
        # Parse query parameters from raw and trimmed requests
        method, raw_path, _ = parse_request(self.raw_request)
        _, trimmed_path, _ = parse_request(trimmed_request)
        
        raw_params = parse_query_params(raw_path)
        trimmed_params = parse_query_params(trimmed_path)
        
        # Determine which parameters were removed
        unnecessary_params = set(raw_params.keys()) - set(trimmed_params.keys())
        necessary_params = set(trimmed_params.keys())
        
        # Get the total number of HTTP requests made
        total_requests = get_request_counter()
        
        # Create report
        report = {
            "original": {
                "size": len(self.raw_request),
                "headers_count": len(raw_headers),
                "cookies_count": len(raw_cookies),
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
    parser = argparse.ArgumentParser(description='Trim HTTP requests by removing unnecessary headers, cookies, and query parameters')
    parser.add_argument('request_file', help='File containing the raw HTTP request')
    parser.add_argument('--output', '-o', help='Output file for the trimmed request')
    parser.add_argument('--base-url', help='Base URL for the request (optional)')
    parser.add_argument('--verbose', '-v', action='store_true', help='Enable verbose logging (DEBUG level)')
    parser.add_argument('--debug', '-d', action='store_true', help='Enable debug mode (INFO level logs)')
    parser.add_argument('--report', '-r', action='store_true', help='Generate a trimming report')
    parser.add_argument('--length-tolerance', '-lt', type=int, default=10, 
                        help='Maximum allowed difference in response length in bytes (default: 50)')
    parser.add_argument('--timeout', '-t', type=int, default=10,
                        help='Timeout for HTTP requests in seconds (default: 10)')
    parser.add_argument('--trim-headers', action='store_true', default=True,
                        help='Trim unnecessary headers (default: True)')
    parser.add_argument('--trim-cookies', action='store_true', default=True,
                        help='Trim unnecessary cookies (default: True)')
    parser.add_argument('--trim-query-params', action='store_true', default=True,
                        help='Trim unnecessary query parameters (default: True)')
    parser.add_argument('--headers-only', action='store_true', 
                        help='Only trim headers (shortcut for --trim-headers --no-trim-cookies --no-trim-query-params)')
    parser.add_argument('--cookies-only', action='store_true', 
                        help='Only trim cookies (shortcut for --no-trim-headers --trim-cookies --no-trim-query-params)')
    parser.add_argument('--query-params-only', action='store_true', 
                        help='Only trim query parameters (shortcut for --no-trim-headers --no-trim-cookies --trim-query-params)')
    parser.add_argument('--no-trim-headers', action='store_false', dest='trim_headers',
                        help='Do not trim headers')
    parser.add_argument('--no-trim-cookies', action='store_false', dest='trim_cookies',
                        help='Do not trim cookies')
    parser.add_argument('--no-trim-query-params', action='store_false', dest='trim_query_params',
                        help='Do not trim query parameters')
    
    args = parser.parse_args()
    
    # Configure logging
    if args.verbose:
        log_level = logging.DEBUG
    elif args.debug:
        log_level = logging.INFO
    else:
        log_level = logging.WARNING
    
    logging.basicConfig(
        level=log_level,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
        handlers=[
            logging.StreamHandler(sys.stdout),
            logging.FileHandler('request_trimmer.log')
        ]
    )
    logger.setLevel(log_level)
    logger.info(f"Starting request_trimmer with log level: {logging.getLevelName(log_level)}")
    logger.debug(f"Command line arguments: {args}")
    
    # Process shortcut arguments
    if args.headers_only:
        args.trim_headers = True
        args.trim_cookies = False
        args.trim_query_params = False
    elif args.cookies_only:
        args.trim_headers = False
        args.trim_cookies = True
        args.trim_query_params = False
    elif args.query_params_only:
        args.trim_headers = False
        args.trim_cookies = False
        args.trim_query_params = True
    
    # Read request file
    logger.info(f"Reading request file: {args.request_file}")
    try:
        with open(args.request_file, 'r') as f:
            raw_request = f.read()
        logger.debug(f"Read {len(raw_request)} characters from request file")
    except Exception as e:
        logger.error(f"Error reading request file: {str(e)}")
        sys.exit(1)
    
    # Create RequestTrimmer instance
    logger.info("Creating RequestTrimmer instance")
    try:
        trimmer = RequestTrimmer(
            raw_request=raw_request,
            base_url=args.base_url,
            length_tolerance=args.length_tolerance,
            timeout=args.timeout,
            trim_headers=args.trim_headers,
            trim_cookies=args.trim_cookies,
            trim_query_params=args.trim_query_params
        )
        
        # Trim request
        trimmed_request = trimmer.trim_request()
        
        # Output trimmed request
        if args.output:
            logger.info(f"Writing trimmed request to {args.output}")
            with open(args.output, 'w') as f:
                f.write(trimmed_request)
        else:
            print("\nTrimmed request:")
            print(trimmed_request)
        
        # Generate report if requested
        if args.report:
            logger.info("Generating report")
            report = trimmer.generate_report(trimmed_request)
            print("\nTrimming report:")
            print(json.dumps(report, indent=2))
            
        # Print summary
        total_requests = get_request_counter()
        print(f"\nTotal HTTP requests made: {total_requests}")
        
    except Exception as e:
        logger.error(f"Error trimming request: {str(e)}")
        import traceback
        logger.error(traceback.format_exc())
        sys.exit(1)

if __name__ == '__main__':
    main()
