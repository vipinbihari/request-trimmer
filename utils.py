import requests
import time
from typing import Dict, List, Tuple, Any, Optional, Set
import logging
from urllib.parse import urlparse, parse_qs, urlencode, urlunparse
from abc import ABC, abstractmethod

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

def format_headers(headers: Dict[str, str]) -> List[str]:
    """Formats a dictionary of headers into a list of strings."""
    return [f"{k}: {v}" for k, v in headers.items()]

def format_cookies(cookies: Dict[str, str]) -> str:
    """Formats a dictionary of cookies into a single Cookie header string."""
    return '; '.join([f"{k}={v}" for k, v in cookies.items()])

def format_query_params(query_params: Dict[str, List[str]]) -> str:
    """Formats a dictionary of query parameters into a query string."""
    # Handles list values correctly
    return urlencode(query_params, doseq=True)

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

@log_function_call
def parse_request(raw_request: str) -> Tuple[str, str, Dict[str, str], str]:
    """
    Parse method, path, headers, and payload from raw HTTP request.
    
    Args:
        raw_request: The raw HTTP request as a string
        
    Returns:
        Tuple of (method, path, headers_dict, payload)
    """
    lines = raw_request.strip().split('\n')
    request_line = lines[0]
    
    # Extract method and path
    method, path_with_version = request_line.split(' ', 1)
    path = path_with_version.rsplit(' ', 1)[0] if ' ' in path_with_version else path_with_version
    
    headers_dict = {}
    payload = ""
    blank_line_found = False
    header_lines_ended = False

    for line in lines[1:]:
        stripped_line = line.strip()
        
        if not stripped_line and not header_lines_ended:
            # Blank line signifies end of headers
            header_lines_ended = True
            continue
        
        if not header_lines_ended:
            # Parse header lines
            if ':' in stripped_line:
                key, value = stripped_line.split(':', 1)
                headers_dict[key.strip()] = value.strip()
            else:
                # Handle potential malformed header line or continuation? 
                # For now, just skip it. Consider logging a warning if needed.
                logger.warning(f"Skipping potentially malformed header line: {stripped_line}")
        elif header_lines_ended:
             # Everything after the blank line is the payload
             # In HTTP, payload might span multiple lines, but often it's single for form data
             # For simplicity here, assume payload is the first non-empty line after headers
             # More robust parsing might be needed for complex payloads
             if stripped_line: # Only take the first non-empty line as payload for now
                 payload = stripped_line
                 break 
            
    logger.debug(f"Parsed request: method={method}, path={path}, headers_count={len(headers_dict)}, payload_length={len(payload)}")
    if payload:
        logger.debug(f"Payload: {payload[:100]}{'...' if len(payload) > 100 else ''}")
    
    return method, path, headers_dict, payload

class BaseTrimmer(ABC):
    """
    Base class for all trimmer classes with common functionality.
    """
    def __init__(self, base_url: str, raw_request: str, baseline_response: requests.Response,
                 length_tolerance: int = 10, timeout: int = DEFAULT_TIMEOUT):
        """
        Initialize the BaseTrimmer with a raw HTTP request and the baseline response.
        
        Args:
            base_url: The base URL for the request
            raw_request: The raw HTTP request as a string
            baseline_response: The baseline response to compare against (fetched once externally)
            length_tolerance: Maximum allowed difference in response length
            timeout: Timeout for HTTP requests in seconds
        """
        logger.info(f"Initializing {self.__class__.__name__} with base_url={base_url}, timeout={timeout}")
        self.base_url = base_url
        self.raw_request = raw_request
        self.method, self.path, self.headers, self.payload = parse_request(raw_request)
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
    
    @abstractmethod
    def _get_all_items(self) -> Dict[str, Any]:
        """
        Return the full dictionary of items being trimmed (e.g., headers, cookies, params).
        This method must be implemented by subclasses.

        Returns:
            Dictionary of all original items.
        """
        pass

    @abstractmethod
    def _send_request(self, items_to_include: Dict[str, Any]) -> requests.Response:
        """
        Send HTTP request including only the specified items.
        Subclasses must implement this to handle their specific item type (headers, cookies, params).
        
        Args:
            items_to_include: Dictionary of items (and their values) to include in this request.

        Returns:
            Response object
        """
        pass
    
    @log_function_call
    def reconstruct_request(self, unnecessary_items: Set[str]) -> str:
        """
        Reconstructs the raw HTTP request string after removing unnecessary items.
        This method should be called *after* the unnecessary items have been identified.
        Subclasses might need to override parts or provide specific implementations
        for how items map to request components (headers, cookies, query params).
        """
        item_type = self.__class__.__name__.replace('Trimmer', '').lower()
        logger.info(f"Reconstructing request, removing {len(unnecessary_items)} unnecessary {item_type}(s): {unnecessary_items}")

        # Default reconstruction logic - assumes items are headers
        # Subclasses for Cookies and Query Params will need to override or specialize

        current_headers = self.headers.copy()
        current_path = self.path
        current_payload = self.payload
        current_method = self.method

        # Base implementation assumes items are header keys
        # This part will be specialized in subclasses or overridden
        final_headers = {k: v for k, v in current_headers.items() if k not in unnecessary_items}

        request_lines = []
        request_lines.append(f"{current_method} {current_path} HTTP/1.1") # Path might change in QueryParamTrimmer
        request_lines.extend(format_headers(final_headers)) # Headers might change in Header/CookieTrimmer

        if current_payload:
            request_lines.append("")
            request_lines.append(current_payload)

        reconstructed_request = '\n'.join(request_lines)
        logger.debug(f"Reconstructed request length: {len(reconstructed_request)} chars")
        # logger.debug(f"Reconstructed request content:\n{reconstructed_request}") # Optional: Debug logging
        return reconstructed_request

    @log_function_call
    def _divide_and_conquer(self, item_keys_to_test: Set[str], 
                           unnecessary_item_keys: Set[str]) -> None:
        """
        Recursively apply divide and conquer to find unnecessary items (generic implementation).
        
        Args:
            item_keys_to_test: Set of item keys (e.g., header names, cookie names) to test
            unnecessary_item_keys: Set to store unnecessary item keys (modified in-place)
        """
        item_type = self.__class__.__name__.replace('Trimmer', '').lower() # e.g., 'header', 'cookie'
        all_items = self._get_all_items() # Get the full dict from subclass

        if not item_keys_to_test:
            return
            
        # First, remove any items that have already been confirmed as unnecessary
        item_keys_to_test = item_keys_to_test - unnecessary_item_keys
        if not item_keys_to_test:
            return
            
        if len(item_keys_to_test) == 1:
            # Base case: test a single item
            item_key = next(iter(item_keys_to_test))
            # Include all original items except the one being tested and those already known to be unnecessary
            test_items = {k: v for k, v in all_items.items() 
                           if k != item_key and k not in unnecessary_item_keys}
            
            logger.info(f"Testing if {item_type} '{item_key}' is necessary by removing it")
            try:
                test_response = self._send_request(test_items)
                baseline_length = len(self.baseline_response.content)
                test_length = len(test_response.content)
                length_diff = abs(baseline_length - test_length)
                
                logger.info(f"{item_type.capitalize()} '{item_key}' test - Baseline: {baseline_length} bytes, Without {item_type}: {test_length} bytes, Diff: {length_diff} bytes")
                
                if self._compare_responses(self.baseline_response, test_response):
                    unnecessary_item_keys.add(item_key)
                    logger.info(f"{item_type.capitalize()} '{item_key}' is unnecessary (response works without it)")
                else:
                    logger.info(f"{item_type.capitalize()} '{item_key}' is necessary (response changed without it)")
            except Exception as e:
                logger.error(f"Error testing {item_type} '{item_key}': {e}")
            return
            
        if len(item_keys_to_test) == 2:
            # Special case for exactly 2 items: use logical inference
            keys_list = list(item_keys_to_test)
            key1, key2 = keys_list[0], keys_list[1]
            
            # Test removing both items
            test_items = {k: v for k, v in all_items.items() 
                           if k not in item_keys_to_test and k not in unnecessary_item_keys}
            logger.info(f"Testing if group of {item_type}s are necessary by removing them all: {item_keys_to_test}")
            try:
                test_response_group = self._send_request(test_items)
                group_works = self._compare_responses(self.baseline_response, test_response_group)
                
                if group_works:
                    # Both items are unnecessary
                    unnecessary_item_keys.update(item_keys_to_test)
                    logger.info(f"All {item_type}s in the group are unnecessary: {item_keys_to_test}")
                    return
                else:
                    logger.info(f"Group contains at least one necessary {item_type}, testing individually")
                    
                    # Test removing only key1
                    test_items_key1_removed = {k: v for k, v in all_items.items() 
                                            if k != key1 and k not in unnecessary_item_keys}
                    logger.info(f"Testing {item_type} '{key1}' by removing it")
                    try:
                        test_response_key1_removed = self._send_request(test_items_key1_removed)
                        key1_unnecessary = self._compare_responses(self.baseline_response, test_response_key1_removed)
                        
                        if key1_unnecessary:
                            unnecessary_item_keys.add(key1)
                            logger.info(f"{item_type.capitalize()} '{key1}' is unnecessary.")
                            logger.info(f"{item_type.capitalize()} '{key2}' is necessary (deduced).")
                        else:
                            logger.info(f"{item_type.capitalize()} '{key1}' is necessary.")
                            # Since removing both failed, but removing key1 alone failed,
                            # we still need to check key2 independently.
                            test_items_key2_removed = {k: v for k, v in all_items.items() 
                                                    if k != key2 and k not in unnecessary_item_keys}
                            logger.info(f"Testing {item_type} '{key2}' by removing it")
                            try:
                                test_response_key2_removed = self._send_request(test_items_key2_removed)
                                key2_unnecessary = self._compare_responses(self.baseline_response, test_response_key2_removed)
                                if key2_unnecessary:
                                    unnecessary_item_keys.add(key2)
                                    logger.info(f"{item_type.capitalize()} '{key2}' is unnecessary.")
                                else:
                                    logger.info(f"{item_type.capitalize()} '{key2}' is necessary.")
                            except Exception as e:
                                logger.error(f"Error testing {item_type} '{key2}': {e}")
                    except Exception as e:
                        logger.error(f"Error testing {item_type} '{key1}': {e}")
                        # If testing key1 fails, try testing key2 anyway
                        self._divide_and_conquer({key2}, unnecessary_item_keys)

            except Exception as e:
                logger.error(f"Error testing {item_type} group {item_keys_to_test}: {e}")
                # If group test fails, test individually
                self._divide_and_conquer({key1}, unnecessary_item_keys)
                self._divide_and_conquer({key2}, unnecessary_item_keys)
            return
            
        # Recursive step: Divide items into two groups
        mid = len(item_keys_to_test) // 2
        group1_keys = set(list(item_keys_to_test)[:mid])
        group2_keys = item_keys_to_test - group1_keys
        
        logger.info(f"Dividing {len(item_keys_to_test)} {item_type}s into Group 1 ({len(group1_keys)}) and Group 2 ({len(group2_keys)})")
        
        # Skip redundant group test for single-key group1
        if len(group1_keys) == 1:
            self._divide_and_conquer(group1_keys, unnecessary_item_keys)
        else:
            # Test removing group1
            test_items_group1_removed = {k: v for k, v in all_items.items() 
                                        if k not in group1_keys and k not in unnecessary_item_keys}
            logger.info(f"Testing Group 1 {item_type}s by removing: {group1_keys}")
            try:
                test_response_group1 = self._send_request(test_items_group1_removed)
                group1_unnecessary = self._compare_responses(self.baseline_response, test_response_group1)
                
                if group1_unnecessary:
                    unnecessary_item_keys.update(group1_keys)
                    logger.info(f"All {item_type}s in Group 1 are unnecessary: {group1_keys}")
                else:
                    logger.info(f"Group 1 contains necessary {item_type}s, recursing...")
                    self._divide_and_conquer(group1_keys, unnecessary_item_keys)
            except Exception as e:
                logger.error(f"Error testing Group 1 {item_type}s: {e}. Testing individually.")
                self._divide_and_conquer(group1_keys, unnecessary_item_keys)
        
        group2_keys_to_test = group2_keys - unnecessary_item_keys
        if not group2_keys_to_test:
            logger.info("Skipping Group 2 testing as all its items were found unnecessary during Group 1 test or previously.")
            return
        
        # Skip redundant group test for single-key group2
        if len(group2_keys_to_test) == 1:
            self._divide_and_conquer(group2_keys_to_test, unnecessary_item_keys)
            return
        
        # Test removing group2 (excluding any newly found unnecessary items)
        test_items_group2_removed = {k: v for k, v in all_items.items() 
                                    if k not in group2_keys_to_test and k not in unnecessary_item_keys}
        logger.info(f"Testing Group 2 {item_type}s by removing: {group2_keys_to_test}")
        try:
            test_response_group2 = self._send_request(test_items_group2_removed)
            group2_unnecessary = self._compare_responses(self.baseline_response, test_response_group2)
            
            if group2_unnecessary:
                unnecessary_item_keys.update(group2_keys_to_test)
                logger.info(f"All {item_type}s in Group 2 are unnecessary: {group2_keys_to_test}")
            else:
                logger.info(f"Group 2 contains necessary {item_type}s, recursing...")
                self._divide_and_conquer(group2_keys_to_test, unnecessary_item_keys)
        except Exception as e:
            logger.error(f"Error testing Group 2 {item_type}s: {e}. Testing individually.")
            self._divide_and_conquer(group2_keys_to_test, unnecessary_item_keys)

    # Add abstract find_unnecessary_items method
    @abstractmethod
    def find_unnecessary_items(self) -> str:
         """
         Identifies unnecessary items and returns the trimmed raw request string.
         Subclasses must implement this.

         Returns:
             The raw request string with unnecessary items removed.
         """
         pass


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
