import requests
import logging
from typing import Dict, List, Tuple, Any, Optional, Set
from .utils import logger, BaseTrimmer, parse_cookies, log_function_call, increment_request_counter, format_cookies, format_headers
import time
from functools import wraps

class CookieTrimmer(BaseTrimmer):
    def __init__(self, base_url: str, raw_request: str, baseline_response: requests.Response,
                 length_tolerance: int = 10, timeout: int = 10):
        """
        Initialize the CookieTrimmer.
        
        Args:
            base_url: Base URL for the request
            raw_request: Raw HTTP request
            baseline_response: The baseline response to compare against
            length_tolerance: Maximum allowed difference in response length (in bytes)
            timeout: Timeout for HTTP requests in seconds
        """
        super().__init__(base_url, raw_request, baseline_response, length_tolerance, timeout)
        self.cookies = parse_cookies(self.headers.get('Cookie', ''))
        logger.debug(f"Parsed {len(self.cookies)} cookies from request.")
    
    @log_function_call
    def _send_request(self, cookies_to_include: Dict[str, str]) -> requests.Response:
        """
        Send HTTP request with given cookies.
        
        Args:
            cookies_to_include: Dictionary of cookies to include in the request
            
        Returns:
            Response object
        """
        increment_request_counter()
        headers = self.headers.copy()
        
        if cookies_to_include:
            cookie_str = format_cookies(cookies_to_include)
            headers['Cookie'] = cookie_str
            logger.debug(f"Sending request with cookies: {list(cookies_to_include.keys())}")
        else:
            headers.pop('Cookie', None)
            logger.debug("Sending request with no cookies.")
        
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
        """Returns the dictionary of all original cookies found in the initial request."""
        return self.cookies

    @log_function_call
    def reconstruct_request(self, unnecessary_items: Set[str]) -> str:
        """
        Reconstructs the raw HTTP request string removing unnecessary cookies.
        """
        item_type = self.__class__.__name__.replace('Trimmer', '').lower()
        logger.info(f"Reconstructing request, removing {len(unnecessary_items)} unnecessary {item_type}(s): {unnecessary_items}")

        final_headers = self.headers.copy()
        original_cookies = self.cookies

        necessary_cookies = {k: v for k, v in original_cookies.items() if k not in unnecessary_items}

        if necessary_cookies:
            cookie_str = format_cookies(necessary_cookies)
            final_headers['Cookie'] = cookie_str
            logger.debug(f"Rebuilt Cookie header: {cookie_str}")
        else:
            final_headers.pop('Cookie', None)
            logger.debug("Removed Cookie header as no cookies were necessary.")

        request_lines = []
        request_lines.append(f"{self.method} {self.path} HTTP/1.1")
        request_lines.extend(format_headers(final_headers))

        if self.payload:
            request_lines.append("")
            request_lines.append(self.payload)

        reconstructed_request = '\n'.join(request_lines)
        logger.debug(f"Reconstructed request length: {len(reconstructed_request)} chars after cookie trimming")
        return reconstructed_request

    @log_function_call
    def find_unnecessary_items(self) -> str:
        """
        Find unnecessary cookies using divide and conquer and return the trimmed request string.

        Returns:
            Trimmed raw HTTP request string with unnecessary cookies removed.
        """
        if not self.cookies:
            logger.info("No cookies found in the initial request. Skipping cookie trimming.")
            return self.raw_request

        all_cookie_keys = set(self.cookies.keys())
        unnecessary_cookies = set()

        logger.info(f"Testing {len(all_cookie_keys)} cookies using divide and conquer")

        self._divide_and_conquer(all_cookie_keys, unnecessary_cookies)

        logger.info(f"Found {len(unnecessary_cookies)} unnecessary cookies: {unnecessary_cookies}")

        trimmed_request = self.reconstruct_request(unnecessary_cookies)
        return trimmed_request
