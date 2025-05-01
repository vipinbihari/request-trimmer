import requests
import logging
import time
from typing import Dict, List, Tuple, Any, Optional, Set
from .utils import logger, BaseTrimmer, log_function_call, increment_request_counter

class HeaderTrimmer(BaseTrimmer):
    def __init__(self, base_url: str, raw_request: str, baseline_response: requests.Response,
                 length_tolerance: int = 10, timeout: int = 10):
        """
        Initialize the HeaderTrimmer.
        
        Args:
            base_url: Base URL for the request
            raw_request: Raw HTTP request
            baseline_response: The baseline response to compare against
            length_tolerance: Maximum allowed difference in response length (in bytes)
            timeout: Timeout for HTTP requests in seconds
        """
        super().__init__(base_url, raw_request, baseline_response, length_tolerance, timeout)
    
    @log_function_call
    def _send_request(self, headers_to_include: Dict[str, str]) -> requests.Response:
        """
        Send HTTP request with given headers.
        
        Args:
            headers_to_include: Dictionary of headers to include in the request
            
        Returns:
            Response object
        """
        increment_request_counter()
        # Use only the headers passed to this function
        headers = headers_to_include.copy()
        
        logger.debug(f"Sending {self.method} request to {self.base_url}{self.path} with headers: {list(headers.keys())}")
        if self.payload:
            logger.debug(f"Payload length: {len(self.payload)} bytes")
        start_time = time.time()
        
        try:
            response = requests.request(
                method=self.method,
                url=f"{self.base_url}{self.path}",
                headers=headers,
                data=self.payload,
                timeout=self.timeout,
                allow_redirects=False
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

    def _get_all_items(self) -> Dict[str, str]:
        """Returns the dictionary of all original headers."""
        return self.headers

    @log_function_call
    def find_unnecessary_items(self) -> str:
        """
        Find unnecessary headers using divide and conquer and return the trimmed request string.

        Returns:
            Trimmed raw HTTP request string with unnecessary headers removed.
        """
        # Filter out Host and Content-Length as they are often essential and auto-managed
        # Also filter potentially sensitive headers like Authorization
        # Convert keys to lowercase for case-insensitive comparison
        essential_headers_lower = {'host', 'authorization', 'user-agent'} # Added User-Agent as potentially essential
        all_header_keys = {k for k in self.headers.keys() if k.lower() not in essential_headers_lower}
        unnecessary_headers = set()

        if not all_header_keys:
             logger.info("No non-essential headers found to test.")
             return self.raw_request # Return original request if nothing to test

        logger.info(f"Testing {len(all_header_keys)} headers using divide and conquer (excluding essential: {essential_headers_lower})")

        # Use the inherited divide and conquer method - baseline response is now self.baseline_response
        # The unnecessary_headers set is modified in-place
        self._divide_and_conquer(all_header_keys, unnecessary_headers)

        logger.info(f"Found {len(unnecessary_headers)} unnecessary headers: {unnecessary_headers}")

        # Reconstruct the request using the identified unnecessary headers
        # This uses the base class reconstruct_request which works for headers
        trimmed_request = self.reconstruct_request(unnecessary_headers)
        return trimmed_request
