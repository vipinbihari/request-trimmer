import requests
import time
import logging
from urllib.parse import urlparse, urlunparse, parse_qs, urlencode
from typing import Dict, Set, Tuple, List, Optional

from utils import BaseTrimmer, format_query_params, log_function_call, increment_request_counter, parse_query_params, format_headers

logger = logging.getLogger(__name__)

class QueryTrimmer(BaseTrimmer):
    def __init__(self, base_url: str, raw_request: str, baseline_response: requests.Response,
                 length_tolerance: int = 10, timeout: int = 10):
        """
        Initialize the QueryTrimmer.
        
        Args:
            base_url: Base URL for the request
            raw_request: Raw HTTP request
            baseline_response: The baseline response to compare against
            length_tolerance: Maximum allowed difference in response length (in bytes)
            timeout: Timeout for HTTP requests in seconds
        """
        super().__init__(base_url, raw_request, baseline_response, length_tolerance, timeout)
        
        # Parse query parameters from the initial path
        parsed_uri = urlparse(self.path)
        self.query_params = parse_query_params(self.path) # Use the function for consistency
        self.base_path = parsed_uri.path # Path without query string
        logger.debug(f"Parsed {len(self.query_params)} query parameters from path.")
    
    def _build_path_with_params(self, query_params: Dict[str, List[str]]) -> str:
        """
        Build the path string (e.g., /search?q=test) with given query parameters.
        
        Args:
            query_params: Dictionary of query parameters
            
        Returns:
            Path string including query parameters
        """
        # Convert query parameters to URL-encoded string
        query_string = format_query_params(query_params) if query_params else ''
        
        # Build URL
        path = self.base_path
        if query_string:
            path += f"?{query_string}"
            
        return path
    
    @log_function_call
    def _send_request(self, params_to_include: Dict[str, List[str]]) -> requests.Response:
        """
        Send HTTP request with given query parameters.
        
        Args:
            params_to_include: Dictionary of query parameters to include in the request
            
        Returns:
            Response object
        """
        # Build the full URL using the base_url and the path constructed with specific params
        path_with_params = self._build_path_with_params(params_to_include)
        url = f"{self.base_url}{path_with_params}"

        logger.debug(f"Sending {self.method} request to {url} with headers: {list(self.headers.keys())}")
        if self.payload:
            logger.debug(f"Payload length: {len(self.payload)} bytes")
        start_time = time.time()
        
        try:
            # Increment the global request counter
            increment_request_counter()
            
            # Use requests.request for generic method handling
            response = requests.request(
                method=self.method,
                url=url, 
                headers=self.headers, # Use original headers from the request
                data=self.payload, 
                timeout=self.timeout,
                allow_redirects=False # Important for consistent comparison
            )
            
            end_time = time.time()
            logger.debug(f"Request completed in {end_time - start_time:.2f} seconds with status code {response.status_code}")
            logger.debug(f"Response length: {len(response.content)} bytes")
            return response
        except requests.exceptions.Timeout:
            logger.error(f"Request timed out after {self.timeout} seconds")
            raise
        except requests.exceptions.RequestException as e:
            logger.error(f"Request failed: {str(e)}")
            raise

    def _get_all_items(self) -> Dict[str, List[str]]:
        """Returns the dictionary of all original query parameters."""
        return self.query_params

    # Override reconstruct_request for query parameters
    @log_function_call
    def reconstruct_request(self, unnecessary_items: Set[str]) -> str:
        """
        Reconstructs the raw HTTP request string removing unnecessary query parameters.
        """
        item_type = self.__class__.__name__.replace('Trimmer', '').lower()
        logger.info(f"Reconstructing request, removing {len(unnecessary_items)} unnecessary {item_type}(s): {unnecessary_items}")

        original_params = self.query_params
        necessary_params = {k: v for k, v in original_params.items() if k not in unnecessary_items}

        # Rebuild path with only necessary parameters
        final_path = self._build_path_with_params(necessary_params)
        logger.debug(f"Rebuilt path: {final_path}")

        # Reconstruct the request lines using the new path and original headers/payload
        request_lines = []
        request_lines.append(f"{self.method} {final_path} HTTP/1.1")
        # Use original headers (cookies/other headers are handled by previous/other trimmers)
        request_lines.extend(format_headers(self.headers))

        if self.payload:
            request_lines.append("")
            request_lines.append(self.payload)

        reconstructed_request = '\n'.join(request_lines)
        logger.debug(f"Reconstructed request length: {len(reconstructed_request)} chars after query param trimming")
        return reconstructed_request

    # Implement find_unnecessary_items
    @log_function_call
    def find_unnecessary_items(self) -> str:
        """
        Find unnecessary query parameters using divide and conquer and return the trimmed request string.

        Returns:
            Trimmed raw HTTP request string with unnecessary query parameters removed.
        """
        if not self.query_params:
            logger.info("No query parameters found in the request path. Skipping query param trimming.")
            return self.raw_request # Return the input request unchanged

        all_param_keys = set(self.query_params.keys())
        unnecessary_params = set()

        logger.info(f"Testing {len(all_param_keys)} query parameters using divide and conquer")

        # Use the inherited divide and conquer method
        self._divide_and_conquer(all_param_keys, unnecessary_params)

        logger.info(f"Found {len(unnecessary_params)} unnecessary query parameters: {unnecessary_params}")

        # Reconstruct the request using the overridden reconstruct_request
        trimmed_request = self.reconstruct_request(unnecessary_params)
        return trimmed_request
