import requests
import re
import json
import time
from typing import Dict, List, Tuple, Any, Optional, Set
import logging
from difflib import SequenceMatcher
from urllib.parse import urlparse, parse_qs, urlencode

# Configure logging
logging.basicConfig(level=logging.WARNING, 
                   format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
                   handlers=[
                       logging.StreamHandler(),
                       logging.FileHandler('request_trimmer.log')
                   ])
logger = logging.getLogger(__name__)

# Default timeout for HTTP requests in seconds
DEFAULT_TIMEOUT = 10

# Global counter for HTTP requests
http_request_counter = 0

def reset_request_counter():
    """
    Reset the global HTTP request counter to zero.
    """
    global http_request_counter
    http_request_counter = 0

def increment_request_counter():
    """
    Increment the global HTTP request counter.
    """
    global http_request_counter
    http_request_counter += 1
    return http_request_counter

def get_request_counter():
    """
    Get the current value of the global HTTP request counter.
    """
    global http_request_counter
    return http_request_counter

def log_function_call(func):
    """
    Decorator to log function calls with timing information.
    """
    def wrapper(*args, **kwargs):
        func_name = func.__name__
        logger.debug(f"Starting {func_name}")
        start_time = time.time()
        result = func(*args, **kwargs)
        end_time = time.time()
        logger.debug(f"Finished {func_name} in {end_time - start_time:.2f} seconds")
        return result
    return wrapper

@log_function_call
def compare_responses(response1: requests.Response, response2: requests.Response, 
                     length_tolerance: int = 10) -> bool:
    """
    Compare two HTTP responses to determine if they are equivalent.
    Only checks status code and content length (within tolerance).
    
    Args:
        response1: First HTTP response
        response2: Second HTTP response
        length_tolerance: Maximum allowed difference in response length (in bytes)
        
    Returns:
        True if responses are equivalent, False otherwise
    """
    # First check: Status code must match exactly
    if response1.status_code != response2.status_code:
        logger.debug(f"Status code mismatch: {response1.status_code} vs {response2.status_code}")
        return False
    
    # Second check: Response length should be within tolerance
    # Get raw content length in bytes
    len1 = len(response1.content)
    len2 = len(response2.content)
    length_diff = abs(len1 - len2)
    
    logger.info(f"Response length comparison: baseline={len1} bytes, test={len2} bytes, difference={length_diff} bytes (tolerance: {length_tolerance} bytes)")
    
    if length_diff > length_tolerance:
        logger.info(f"Length difference exceeds tolerance: {len1} vs {len2} bytes (difference: {length_diff} bytes, tolerance: {length_tolerance} bytes)")
        return False
    
    logger.info(f"Responses match: same status code and length within tolerance ({length_diff} bytes difference)")
    return True

@log_function_call
def parse_headers(raw_request: str) -> Dict[str, str]:
    """
    Parse headers from raw HTTP request.
    
    Args:
        raw_request: The raw HTTP request as a string
        
    Returns:
        Dictionary of headers
    """
    headers = {}
    lines = raw_request.strip().split('\n')
    
    # Skip the first line (request line)
    for line in lines[1:]:
        if not line.strip() or line == 'PAYLOAD':
            break
            
        if ':' in line:
            key, value = line.split(':', 1)
            headers[key.strip()] = value.strip()
            
    return headers

@log_function_call
def parse_cookies(cookie_header: str) -> Dict[str, str]:
    """
    Parse cookies from Cookie header.
    
    Args:
        cookie_header: The Cookie header value
        
    Returns:
        Dictionary of cookies
    """
    cookies = {}
    if not cookie_header:
        return cookies
        
    cookie_pairs = cookie_header.split(';')
    for pair in cookie_pairs:
        if '=' in pair:
            key, value = pair.split('=', 1)
            cookies[key.strip()] = value.strip()
            
    return cookies

@log_function_call
def parse_request(raw_request: str) -> Tuple[str, str, str]:
    """
    Parse method, path and payload from raw HTTP request.
    
    Args:
        raw_request: The raw HTTP request as a string
        
    Returns:
        Tuple of (method, path, payload)
    """
    lines = raw_request.strip().split('\n')
    request_line = lines[0]
    
    # Extract method and path
    method, path_with_version = request_line.split(' ', 1)
    path = path_with_version.rsplit(' ', 1)[0] if ' ' in path_with_version else path_with_version
    
    # Extract payload
    payload = ""
    blank_line_found = False
    
    for line in lines[1:]:
        if not line.strip():
            blank_line_found = True
            continue
        
        if blank_line_found:
            # Everything after the blank line is the payload
            payload = line.strip()
            break
            
    logger.debug(f"Parsed request: method={method}, path={path}, payload_length={len(payload)}")
    if payload:
        logger.debug(f"Payload: {payload[:100]}{'...' if len(payload) > 100 else ''}")
    
    return method, path, payload

@log_function_call
def parse_query_params(path: str) -> Dict[str, List[str]]:
    """
    Parse query parameters from path.
    
    Args:
        path: The request path with query string
        
    Returns:
        Dictionary of query parameters
    """
    from urllib.parse import urlparse, parse_qs
    parsed_url = urlparse(path)
    query_params = parse_qs(parsed_url.query)
    
    logger.debug(f"Parsed query parameters: {len(query_params)} parameters found")
    return query_params

class BaseTrimmer:
    """
    Base class for all trimmer classes with common functionality.
    """
    def __init__(self, base_url: str, raw_request: str, baseline_response: Optional[requests.Response] = None,
                 length_tolerance: int = 10, timeout: int = DEFAULT_TIMEOUT):
        """
        Initialize the BaseTrimmer with a raw HTTP request and optional baseline response.
        
        Args:
            base_url: The base URL for the request
            raw_request: The raw HTTP request as a string
            baseline_response: Optional pre-existing baseline response to compare against
            length_tolerance: Maximum allowed difference in response length
            timeout: Timeout for HTTP requests in seconds
        """
        logger.info(f"Initializing {self.__class__.__name__} with base_url={base_url}, timeout={timeout}")
        self.base_url = base_url
        self.raw_request = raw_request
        self.headers = parse_headers(raw_request)
        self.method, self.path, self.payload = parse_request(raw_request)
        self.baseline_response = baseline_response
        self.length_tolerance = length_tolerance
        self.timeout = timeout
        logger.debug(f"Parsed headers: {len(self.headers)} headers found")
        logger.debug(f"Request method: {self.method}, path: {self.path}")
    
    def _compare_responses(self, response1: requests.Response, response2: requests.Response) -> bool:
        """
        Compare two HTTP responses to check if they are equivalent.
        
        Args:
            response1: First response object
            response2: Second response object
            
        Returns:
            True if responses are equivalent, False otherwise
        """
        return compare_responses(response1, response2, self.length_tolerance)
    
    def _get_baseline_response(self) -> requests.Response:
        """
        Get baseline response with all parameters.
        This method should be overridden by subclasses.
        
        Returns:
            Baseline response object
        """
        raise NotImplementedError("Subclasses must implement _get_baseline_response()")
    
    def _send_request(self, **kwargs) -> requests.Response:
        """
        Send HTTP request with given parameters.
        This method should be overridden by subclasses.
        
        Returns:
            Response object
        """
        raise NotImplementedError("Subclasses must implement _send_request()")
    
    def _divide_and_conquer(self, items_to_test: Set[str], baseline_response: requests.Response, 
                           unnecessary_items: Set[str]) -> None:
        """
        Recursively apply divide and conquer to find unnecessary items.
        This method should be overridden by subclasses.
        """
        raise NotImplementedError("Subclasses must implement _divide_and_conquer()")

@log_function_call
def derive_base_url(raw_request: str) -> str:
    """
    Derive base URL from raw HTTP request.
    
    Args:
        raw_request: The raw HTTP request as a string
        
    Returns:
        Base URL string
    """
    lines = raw_request.strip().split('\n')
    host = None
    
    # Find Host header
    for line in lines[1:]:  # Skip the first line (request line)
        if not line.strip() or line == 'PAYLOAD':
            break
            
        if line.lower().startswith('host:'):
            host = line.split(':', 1)[1].strip()
            break
            
    if not host:
        raise ValueError("Host header not found in request")
        
    # Determine scheme (http or https)
    scheme = "https"
    if any(line.lower().startswith('referer:') for line in lines):
        for line in lines:
            if line.lower().startswith('referer:'):
                referer = line.split(':', 1)[1].strip()
                parsed_referer = urlparse(referer)
                scheme = parsed_referer.scheme
                break
    
    return f"{scheme}://{host}"
