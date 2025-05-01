import argparse
import sys
import logging
import time
from typing import Dict, List, Tuple, Any, Optional, Set
from urllib.parse import urlparse
from .header_trimmer import HeaderTrimmer
from .cookie_trimmer import CookieTrimmer
from .query_trimmer import QueryTrimmer
from .utils import logger, derive_base_url, parse_headers, parse_cookies, parse_query_params, parse_request, log_function_call, reset_request_counter, get_request_counter

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
    def trim_request(self) -> str:
        """
        Trim the HTTP request by removing unnecessary headers, cookies, and query parameters.
        
        Returns:
            Trimmed raw HTTP request as a string
        """
        logger.info("Starting request trimming process")
        
        # Reset the request counter before starting
        reset_request_counter()
        
        # Step 1: Trim headers
        unnecessary_headers = set()
        header_trimmer = None
        
        if self.trim_headers:
            logger.info("Step 1: Trimming headers...")
            header_trimmer = HeaderTrimmer(
                self.base_url, 
                self.raw_request, 
                None, 
                self.length_tolerance, 
                self.timeout
            )
            baseline_response = header_trimmer._get_baseline_response()
            unnecessary_headers = header_trimmer.find_unnecessary_headers(baseline_response)
            logger.info(f"Found {len(unnecessary_headers)} unnecessary headers: {', '.join(unnecessary_headers) if unnecessary_headers else 'None'}")
        else:
            logger.info("Skipping header trimming as requested")
            header_trimmer = HeaderTrimmer(
                self.base_url, 
                self.raw_request, 
                None, 
                self.length_tolerance, 
                self.timeout
            )
            baseline_response = header_trimmer._get_baseline_response()
        
        # Step 2: Trim cookies
        unnecessary_cookies = set()
        necessary_cookies = set()
        
        if self.trim_cookies:
            logger.info("Step 2: Trimming cookies...")
            cookie_trimmer = CookieTrimmer(
                self.base_url, 
                self.raw_request, 
                baseline_response, 
                self.length_tolerance, 
                self.timeout
            )
            unnecessary_cookies = cookie_trimmer.find_unnecessary_cookies(baseline_response)
            necessary_cookies = set(cookie_trimmer.cookies.keys()) - unnecessary_cookies
            logger.info(f"Found {len(unnecessary_cookies)} unnecessary cookies: {', '.join(unnecessary_cookies) if unnecessary_cookies else 'None'}")
        else:
            logger.info("Skipping cookie trimming as requested")
            # Get all cookies from the request
            necessary_cookies = set(parse_cookies(parse_headers(self.raw_request).get('Cookie', '')).keys())
        
        # Step 3: Trim query parameters
        unnecessary_params = set()
        necessary_params = set()
        
        if self.trim_query_params:
            logger.info("Step 3: Trimming query parameters...")
            query_trimmer = QueryTrimmer(
                self.base_url, 
                self.raw_request, 
                baseline_response, 
                self.length_tolerance, 
                self.timeout
            )
            unnecessary_params = query_trimmer.find_unnecessary_params(baseline_response)
            necessary_params = set(query_trimmer.query_params.keys()) - unnecessary_params
            logger.info(f"Found {len(unnecessary_params)} unnecessary query parameters: {', '.join(unnecessary_params) if unnecessary_params else 'None'}")
        else:
            logger.info("Skipping query parameter trimming as requested")
            # Get all query parameters from the request
            method, path, _ = parse_request(self.raw_request)
            necessary_params = set(parse_query_params(path).keys())
        
        # Construct trimmed request
        logger.info("Constructing trimmed request")
        request_lines = []
        
        # Add request line (method + path)
        method, path, _ = header_trimmer.method, header_trimmer.path, header_trimmer.payload
        
        # Modify path if we trimmed query parameters
        if self.trim_query_params and unnecessary_params:
            from urllib.parse import urlparse, parse_qs, urlencode
            parsed_url = urlparse(path)
            query_params = parse_qs(parsed_url.query)
            
            # Remove unnecessary parameters
            for param in unnecessary_params:
                if param in query_params:
                    del query_params[param]
            
            # Reconstruct path
            if query_params:
                query_string = urlencode(query_params, doseq=True)
                path = f"{parsed_url.path}?{query_string}"
            else:
                path = parsed_url.path
        
        request_lines.append(f"{method} {path} HTTP/1.1")
        
        # Add headers (excluding unnecessary ones)
        for header, value in header_trimmer.headers.items():
            if header not in unnecessary_headers:
                if header == 'Cookie' and self.trim_cookies and unnecessary_cookies:
                    # Modify Cookie header to only include necessary cookies
                    cookies = parse_cookies(value)
                    necessary_cookie_dict = {k: v for k, v in cookies.items() if k in necessary_cookies}
                    if necessary_cookie_dict:
                        cookie_str = '; '.join([f"{k}={v}" for k, v in necessary_cookie_dict.items()])
                        request_lines.append(f"{header}: {cookie_str}")
                else:
                    request_lines.append(f"{header}: {value}")
            
        if header_trimmer.payload:
            request_lines.append("")
            request_lines.append(header_trimmer.payload)
        
        trimmed_request = '\n'.join(request_lines)
        
        # Get the total number of HTTP requests made
        total_requests = get_request_counter()
        logger.info(f"Request trimming completed. Total HTTP requests made: {total_requests}")
        
        return trimmed_request
    
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
