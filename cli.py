#!/usr/bin/env python3

import argparse
import sys
import logging
import time
from typing import Dict, List, Tuple, Any, Optional, Set
from urllib.parse import urlparse
from request_trimmer.main import RequestTrimmer
from request_trimmer.utils import logger, derive_base_url, reset_request_counter, get_request_counter

def main():
    parser = argparse.ArgumentParser(description='Trim HTTP requests by removing unnecessary headers, cookies, and query parameters')
    parser.add_argument('request_file', help='File containing the raw HTTP request')
    parser.add_argument('--output', '-o', help='Output file for the trimmed request')
    parser.add_argument('--base-url', help='Base URL for the request (optional)')
    parser.add_argument('--verbose', '-v', action='store_true', help='Enable verbose logging (DEBUG level)')
    parser.add_argument('--debug', '-d', action='store_true', help='Enable debug mode (INFO level logs)')
    parser.add_argument('--report', '-r', action='store_true', help='Generate a trimming report')
    parser.add_argument('--length-tolerance', '-lt', type=int, default=10, 
                        help='Maximum allowed difference in response length in bytes (default: 10)')
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
        logger.debug("Using --headers-only shortcut")
    elif args.cookies_only:
        args.trim_headers = False
        args.trim_cookies = True
        args.trim_query_params = False
        logger.debug("Using --cookies-only shortcut")
    elif args.query_params_only:
        args.trim_headers = False
        args.trim_cookies = False
        args.trim_query_params = True
        logger.debug("Using --query-params-only shortcut")
    
    # Read raw request from file
    try:
        with open(args.request_file, 'r') as f:
            raw_request = f.read()
            logger.debug(f"Read {len(raw_request)} bytes from {args.request_file}")
    except Exception as e:
        logger.error(f"Error reading request file: {e}")
        sys.exit(1)
    
    # Reset request counter
    reset_request_counter()
    start_time = time.time()
    
    # Create RequestTrimmer instance and trim the request
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
        
        trimmed_request = trimmer.trim_request()
        elapsed_time = time.time() - start_time
        total_requests = get_request_counter()
        
        logger.info(f"Request trimming completed in {elapsed_time:.2f} seconds with {total_requests} HTTP requests")
        
        # Output the trimmed request
        if args.output:
            with open(args.output, 'w') as f:
                f.write(trimmed_request)
                logger.info(f"Trimmed request written to {args.output}")
        else:
            print("\n=== Trimmed Request ===\n")
            print(trimmed_request)
        
        # Generate and output the report if requested
        if args.report:
            report = trimmer.get_trimming_report()
            print("\n=== Trimming Report ===\n")
            print(report)
            
    except Exception as e:
        logger.error(f"Error trimming request: {e}")
        import traceback
        logger.debug(traceback.format_exc())
        sys.exit(1)

if __name__ == '__main__':
    main()
