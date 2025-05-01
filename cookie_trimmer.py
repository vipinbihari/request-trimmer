import requests
import logging
from typing import Dict, List, Tuple, Any, Optional, Set
from .utils import logger, BaseTrimmer, parse_cookies, log_function_call, increment_request_counter
import time
from functools import wraps

def log_function_call(func):
    @wraps(func)
    def wrapper(*args, **kwargs):
        logger.debug(f"Calling {func.__name__}")
        return func(*args, **kwargs)
    return wrapper

class CookieTrimmer(BaseTrimmer):
    def __init__(self, base_url: str, raw_request: str, baseline_response: Optional[requests.Response] = None,
                 length_tolerance: int = 10, timeout: int = 10):
        """
        Initialize the CookieTrimmer.
        
        Args:
            base_url: Base URL for the request
            raw_request: Raw HTTP request
            baseline_response: Optional baseline response to compare against
            length_tolerance: Maximum allowed difference in response length (in bytes)
            timeout: Timeout for HTTP requests in seconds
        """
        super().__init__(base_url, raw_request, baseline_response, length_tolerance, timeout)
        self.cookies = parse_cookies(self.headers.get('Cookie', ''))
    
    @log_function_call
    def _send_request(self, cookies: Dict[str, str]) -> requests.Response:
        """
        Send HTTP request with given cookies.
        
        Args:
            cookies: Dictionary of cookies to include in the request
            
        Returns:
            Response object
        """
        increment_request_counter()
        headers = self.headers.copy()
        
        # Remove Cookie header if it exists
        if 'Cookie' in headers:
            del headers['Cookie']
        
        # Add cookies to headers if provided
        if cookies:
            cookie_str = '; '.join([f"{k}={v}" for k, v in cookies.items()])
            headers['Cookie'] = cookie_str
        
        logger.debug(f"Sending request with cookies: {cookies}")
        
        # Send the request
        start_time = time.time()
        response = requests.request(
            method=self.method,
            url=f"{self.base_url}{self.path}",
            headers=headers,
            data=self.payload,
            timeout=self.timeout,
            allow_redirects=False
        )
        end_time = time.time()
        
        logger.debug(f"Request completed in {end_time - start_time:.2f} seconds")
        logger.debug(f"Response status code: {response.status_code}")
        logger.debug(f"Response length: {len(response.content)} bytes")
        
        return response
    
    def _get_baseline_response(self) -> requests.Response:
        """
        Get baseline response with all cookies.
        
        Returns:
            Baseline response object
        """
        if self.baseline_response is None:
            self.baseline_response = self._send_request(self.cookies)
        return self.baseline_response
    
    @log_function_call
    def find_unnecessary_cookies(self, baseline_response: Optional[requests.Response] = None) -> Set[str]:
        """
        Find unnecessary cookies using divide and conquer approach.
        
        Args:
            baseline_response: Optional baseline response to compare against
            
        Returns:
            Set of unnecessary cookie names
        """
        if baseline_response is None:
            baseline_response = self._get_baseline_response()
            
        all_cookies = set(self.cookies.keys())
        unnecessary_cookies = set()
        
        logger.info(f"Testing {len(all_cookies)} cookies using divide and conquer")
        
        # Use divide and conquer to find unnecessary cookies
        self._divide_and_conquer(all_cookies, baseline_response, unnecessary_cookies)
        
        return unnecessary_cookies
    
    def _divide_and_conquer(self, cookies_to_test: Set[str], baseline_response: requests.Response, 
                           unnecessary_cookies: Set[str]) -> None:
        """
        Recursively apply divide and conquer to find unnecessary cookies.
        
        Args:
            cookies_to_test: Set of cookies to test
            baseline_response: Baseline response to compare against
            unnecessary_cookies: Set to store unnecessary cookies (modified in-place)
        """
        if not cookies_to_test:
            return
            
        # First, remove any cookies that have already been confirmed as unnecessary
        cookies_to_test = cookies_to_test - unnecessary_cookies
        if not cookies_to_test:
            return
            
        if len(cookies_to_test) == 1:
            # Base case: test a single cookie
            cookie = next(iter(cookies_to_test))
            # Include all cookies except the one being tested and those already known to be unnecessary
            test_cookies = {k: v for k, v in self.cookies.items() 
                           if k != cookie and k not in unnecessary_cookies}
            
            logger.info(f"Testing if cookie '{cookie}' is necessary by removing it")
            try:
                test_response = self._send_request(test_cookies)
                baseline_length = len(baseline_response.content)
                test_length = len(test_response.content)
                length_diff = abs(baseline_length - test_length)
                
                logger.info(f"Cookie '{cookie}' test - Baseline: {baseline_length} bytes, Without cookie: {test_length} bytes, Diff: {length_diff} bytes")
                
                if self._compare_responses(baseline_response, test_response):
                    unnecessary_cookies.add(cookie)
                    logger.info(f"Cookie '{cookie}' is unnecessary (response works without it)")
                else:
                    logger.info(f"Cookie '{cookie}' is necessary (response changed without it)")
            except Exception as e:
                logger.error(f"Error testing cookie '{cookie}': {e}")
            return
            
        if len(cookies_to_test) == 2:
            # Special case for exactly 2 cookies: if one is unnecessary, the other must be necessary
            cookies_list = list(cookies_to_test)
            cookie1, cookie2 = cookies_list[0], cookies_list[1]
            
            # First, test if the entire group is necessary by removing both cookies
            test_cookies = {k: v for k, v in self.cookies.items() 
                           if k not in cookies_to_test and k not in unnecessary_cookies}
            logger.info(f"Testing if all cookies in the group are necessary by removing them all: {cookies_to_test}")
            try:
                test_response = self._send_request(test_cookies)
                baseline_length = len(baseline_response.content)
                test_length = len(test_response.content)
                length_diff = abs(baseline_length - test_length)
                
                logger.info(f"Group test - Baseline: {baseline_length} bytes, Without group: {test_length} bytes, Diff: {length_diff} bytes")
                
                if self._compare_responses(baseline_response, test_response):
                    # Both cookies are unnecessary
                    unnecessary_cookies.update(cookies_to_test)
                    logger.info(f"All cookies in the group are unnecessary: {cookies_to_test}")
                    return
                else:
                    logger.info(f"Group contains at least one necessary cookie, testing individually")
                    
                    # Now test the first cookie
                    test_cookies = {k: v for k, v in self.cookies.items() 
                                   if k != cookie1 and k not in unnecessary_cookies}
                    logger.info(f"Testing if cookie '{cookie1}' is necessary by removing it")
                    try:
                        test_response = self._send_request(test_cookies)
                        test_length = len(test_response.content)
                        length_diff = abs(baseline_length - test_length)
                        
                        logger.info(f"Cookie '{cookie1}' test - Baseline: {baseline_length} bytes, Without cookie: {test_length} bytes, Diff: {length_diff} bytes")
                        
                        if self._compare_responses(baseline_response, test_response):
                            # If cookie1 is unnecessary, then cookie2 must be necessary
                            # (since removing both cookies breaks the response)
                            unnecessary_cookies.add(cookie1)
                            logger.info(f"Cookie '{cookie1}' is unnecessary (response works without it)")
                            logger.info(f"Cookie '{cookie2}' is necessary (deduced from group test)")
                        else:
                            # If cookie1 is necessary, we need to test cookie2 as well
                            logger.info(f"Cookie '{cookie1}' is necessary (response changed without it)")
                            
                            # Test the second cookie
                            test_cookies = {k: v for k, v in self.cookies.items() 
                                           if k != cookie2 and k not in unnecessary_cookies}
                            logger.info(f"Testing if cookie '{cookie2}' is necessary by removing it")
                            try:
                                test_response = self._send_request(test_cookies)
                                test_length = len(test_response.content)
                                length_diff = abs(baseline_length - test_length)
                                
                                logger.info(f"Cookie '{cookie2}' test - Baseline: {baseline_length} bytes, Without cookie: {test_length} bytes, Diff: {length_diff} bytes")
                                
                                if self._compare_responses(baseline_response, test_response):
                                    unnecessary_cookies.add(cookie2)
                                    logger.info(f"Cookie '{cookie2}' is unnecessary (response works without it)")
                                else:
                                    logger.info(f"Cookie '{cookie2}' is necessary (response changed without it)")
                            except Exception as e:
                                logger.error(f"Error testing cookie '{cookie2}': {e}")
                    except Exception as e:
                        logger.error(f"Error testing cookie '{cookie1}': {e}")
                        # Test cookie2 individually
                        self._divide_and_conquer({cookie2}, baseline_response, unnecessary_cookies)
            except Exception as e:
                logger.error(f"Error testing cookie group: {e}")
                # Test cookies individually
                self._divide_and_conquer({cookie1}, baseline_response, unnecessary_cookies)
                self._divide_and_conquer({cookie2}, baseline_response, unnecessary_cookies)
            return
            
        # Divide cookies into two groups
        mid = len(cookies_to_test) // 2
        group1 = set(list(cookies_to_test)[:mid])
        group2 = cookies_to_test - group1
        
        logger.info(f"Dividing {len(cookies_to_test)} cookies into Group 1 ({len(group1)} cookies) and Group 2 ({len(group2)} cookies)")
        
        # Test removing group1
        # Include all cookies except those in group1 and those already known to be unnecessary
        test_cookies = {k: v for k, v in self.cookies.items() 
                       if k not in group1 and k not in unnecessary_cookies}
        logger.info(f"Testing if all cookies in Group 1 are necessary by removing them all: {group1}")
        try:
            test_response = self._send_request(test_cookies)
            baseline_length = len(baseline_response.content)
            test_length = len(test_response.content)
            length_diff = abs(baseline_length - test_length)
            
            logger.info(f"Group 1 test - Baseline: {baseline_length} bytes, Without group: {test_length} bytes, Diff: {length_diff} bytes")
            
            if self._compare_responses(baseline_response, test_response):
                # All cookies in group1 are unnecessary
                unnecessary_cookies.update(group1)
                logger.info(f"All cookies in Group 1 are unnecessary: {group1}")
            else:
                # Some cookies in group1 might be necessary, test them individually
                logger.info(f"Group 1 contains necessary cookies, testing individual cookies")
                self._divide_and_conquer(group1, baseline_response, unnecessary_cookies)
        except Exception as e:
            logger.error(f"Error testing Group 1: {e}")
            # If error occurs, test cookies individually
            logger.info(f"Error occurred testing Group 1, testing individual cookies")
            self._divide_and_conquer(group1, baseline_response, unnecessary_cookies)
        
        # Test removing group2
        # First, remove any cookies that have already been confirmed as unnecessary
        group2 = group2 - unnecessary_cookies
        if not group2:
            logger.info("Skipping Group 2 testing as all cookies in it have already been confirmed as unnecessary")
            return
            
        # Include all cookies except those in group2 and those already known to be unnecessary
        test_cookies = {k: v for k, v in self.cookies.items() 
                       if k not in group2 and k not in unnecessary_cookies}
        logger.info(f"Testing if all cookies in Group 2 are necessary by removing them all: {group2}")
        try:
            test_response = self._send_request(test_cookies)
            baseline_length = len(baseline_response.content)
            test_length = len(test_response.content)
            length_diff = abs(baseline_length - test_length)
            
            logger.info(f"Group 2 test - Baseline: {baseline_length} bytes, Without group: {test_length} bytes, Diff: {length_diff} bytes")
            
            if self._compare_responses(baseline_response, test_response):
                # All cookies in group2 are unnecessary
                unnecessary_cookies.update(group2)
                logger.info(f"All cookies in Group 2 are unnecessary: {group2}")
            else:
                # Some cookies in group2 might be necessary, test them individually
                logger.info(f"Group 2 contains necessary cookies, testing individual cookies")
                self._divide_and_conquer(group2, baseline_response, unnecessary_cookies)
        except Exception as e:
            logger.error(f"Error testing Group 2: {e}")
            # If error occurs, test cookies individually
            logger.info(f"Error occurred testing Group 2, testing individual cookies")
            self._divide_and_conquer(group2, baseline_response, unnecessary_cookies)
    
    def get_trimmed_cookies(self) -> Dict[str, str]:
        """
        Get only the necessary cookies.
        
        Returns:
            Dictionary of necessary cookies
        """
        unnecessary_cookies = self.find_unnecessary_cookies()
        necessary_cookies = {k: v for k, v in self.cookies.items() if k not in unnecessary_cookies}
        return necessary_cookies
    
    def get_trimmed_cookie_header(self) -> str:
        """
        Get the trimmed Cookie header with only necessary cookies.
        
        Returns:
            Trimmed Cookie header value
        """
        necessary_cookies = self.get_trimmed_cookies()
        if not necessary_cookies:
            return ""
            
        return "; ".join([f"{k}={v}" for k, v in necessary_cookies.items()])
