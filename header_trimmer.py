import requests
import logging
import time
from typing import Dict, List, Tuple, Any, Optional, Set
from .utils import logger, BaseTrimmer, log_function_call, increment_request_counter

class HeaderTrimmer(BaseTrimmer):
    def __init__(self, base_url: str, raw_request: str, baseline_response: Optional[requests.Response] = None, 
                 length_tolerance: int = 10, timeout: int = 10):
        """
        Initialize the HeaderTrimmer.
        
        Args:
            base_url: Base URL for the request
            raw_request: Raw HTTP request
            baseline_response: Optional baseline response to compare against
            length_tolerance: Maximum allowed difference in response length (in bytes)
            timeout: Timeout for HTTP requests in seconds
        """
        super().__init__(base_url, raw_request, baseline_response, length_tolerance, timeout)
        self.essential_headers = set(['Host', 'Content-Length', 'Content-Type'])
        logger.debug(f"Essential headers that will not be tested: {self.essential_headers}")
    
    @log_function_call
    def _send_request(self, headers: Dict[str, str]) -> requests.Response:
        """
        Send HTTP request with given headers.
        
        Args:
            headers: Dictionary of headers to include in the request
            
        Returns:
            Response object
        """
        url = f"{self.base_url}{self.path}"
        logger.debug(f"Sending {self.method} request to {url} with {len(headers)} headers")
        if self.payload:
            logger.debug(f"Payload length: {len(self.payload)} bytes")
        start_time = time.time()
        
        try:
            # Increment the global request counter
            increment_request_counter()
            
            # Handle different HTTP methods
            if self.method == 'GET':
                response = requests.get(url, headers=headers, timeout=self.timeout)
            elif self.method == 'POST':
                # Send the payload exactly as it is in the raw request
                response = requests.post(url, headers=headers, data=self.payload, timeout=self.timeout)
            elif self.method == 'PUT':
                response = requests.put(url, headers=headers, data=self.payload, timeout=self.timeout)
            elif self.method == 'DELETE':
                response = requests.delete(url, headers=headers, timeout=self.timeout)
            else:
                raise ValueError(f"Unsupported HTTP method: {self.method}")
            
            end_time = time.time()
            logger.debug(f"Request completed in {end_time - start_time:.2f} seconds with status code {response.status_code}")
            return response
        except requests.exceptions.Timeout:
            logger.error(f"Request timed out after {self.timeout} seconds")
            raise
        except requests.exceptions.RequestException as e:
            logger.error(f"Request failed: {str(e)}")
            raise
    
    @log_function_call
    def _get_baseline_response(self) -> requests.Response:
        """
        Get baseline response with all headers.
        
        Returns:
            Baseline response object
        """
        logger.info("Getting baseline response with all headers")
        if self.baseline_response is None:
            self.baseline_response = self._send_request(self.headers)
            logger.info(f"Baseline response received with status code {self.baseline_response.status_code}")
        return self.baseline_response
    
    @log_function_call
    def find_unnecessary_headers(self, baseline_response: Optional[requests.Response] = None) -> Set[str]:
        """
        Find unnecessary headers using divide and conquer approach.
        
        Args:
            baseline_response: Optional baseline response to compare against
            
        Returns:
            Set of unnecessary header names
        """
        if baseline_response is None:
            baseline_response = self._get_baseline_response()
            
        all_headers = set(self.headers.keys())
        
        # Remove Cookie header as it will be handled by cookie_trimmer
        if 'Cookie' in all_headers:
            all_headers.remove('Cookie')
            logger.debug("Removed Cookie header from testing as it will be handled by cookie_trimmer")
        
        # Remove essential headers that should always be included
        headers_to_test = all_headers - self.essential_headers
        unnecessary_headers = set()
        
        logger.info(f"Testing {len(headers_to_test)} headers using divide and conquer")
        logger.debug(f"Headers to test: {headers_to_test}")
        
        # Use divide and conquer to find unnecessary headers
        self._divide_and_conquer(headers_to_test, baseline_response, unnecessary_headers)
        
        logger.info(f"Found {len(unnecessary_headers)} unnecessary headers")
        logger.debug(f"Unnecessary headers: {unnecessary_headers}")
        return unnecessary_headers
    
    @log_function_call
    def _divide_and_conquer(self, headers_to_test: Set[str], baseline_response: requests.Response, 
                           unnecessary_headers: Set[str]) -> None:
        """
        Recursively apply divide and conquer to find unnecessary headers.
        
        Args:
            headers_to_test: Set of headers to test
            baseline_response: Baseline response to compare against
            unnecessary_headers: Set to store unnecessary headers (modified in-place)
        """
        if not headers_to_test:
            return
            
        # First, remove any headers that have already been confirmed as unnecessary
        headers_to_test = headers_to_test - unnecessary_headers
        if not headers_to_test:
            return
            
        if len(headers_to_test) == 1:
            # Base case: test a single header
            header = next(iter(headers_to_test))
            # Include all headers except the one being tested and those already known to be unnecessary
            test_headers = {k: v for k, v in self.headers.items() 
                           if k != header and k not in unnecessary_headers}
            
            logger.info(f"Testing if header '{header}' is necessary by removing it")
            try:
                test_response = self._send_request(test_headers)
                baseline_length = len(baseline_response.content)
                test_length = len(test_response.content)
                length_diff = abs(baseline_length - test_length)
                
                logger.info(f"Header '{header}' test - Baseline: {baseline_length} bytes, Without header: {test_length} bytes, Diff: {length_diff} bytes")
                
                if self._compare_responses(baseline_response, test_response):
                    unnecessary_headers.add(header)
                    logger.info(f"Header '{header}' is unnecessary (response works without it)")
                else:
                    logger.info(f"Header '{header}' is necessary (response changed without it)")
            except Exception as e:
                logger.error(f"Error testing header '{header}': {e}")
            return
            
        if len(headers_to_test) == 2:
            # Special case for exactly 2 headers: if one is unnecessary, the other must be necessary
            headers_list = list(headers_to_test)
            header1, header2 = headers_list[0], headers_list[1]
            
            # First, test if the entire group is necessary by removing both headers
            test_headers = {k: v for k, v in self.headers.items() 
                           if k not in headers_to_test and k not in unnecessary_headers}
            logger.info(f"Testing if all headers in the group are necessary by removing them all: {headers_to_test}")
            try:
                test_response = self._send_request(test_headers)
                baseline_length = len(baseline_response.content)
                test_length = len(test_response.content)
                length_diff = abs(baseline_length - test_length)
                
                logger.info(f"Group test - Baseline: {baseline_length} bytes, Without group: {test_length} bytes, Diff: {length_diff} bytes")
                
                if self._compare_responses(baseline_response, test_response):
                    # Both headers are unnecessary
                    unnecessary_headers.update(headers_to_test)
                    logger.info(f"All headers in the group are unnecessary: {headers_to_test}")
                    return
                else:
                    logger.info(f"Group contains at least one necessary header, testing individually")
                    
                    # Now test the first header
                    test_headers = {k: v for k, v in self.headers.items() 
                                   if k != header1 and k not in unnecessary_headers}
                    logger.info(f"Testing if header '{header1}' is necessary by removing it")
                    try:
                        test_response = self._send_request(test_headers)
                        test_length = len(test_response.content)
                        length_diff = abs(baseline_length - test_length)
                        
                        logger.info(f"Header '{header1}' test - Baseline: {baseline_length} bytes, Without header: {test_length} bytes, Diff: {length_diff} bytes")
                        
                        if self._compare_responses(baseline_response, test_response):
                            # If header1 is unnecessary, then header2 must be necessary
                            # (since removing both headers breaks the response)
                            unnecessary_headers.add(header1)
                            logger.info(f"Header '{header1}' is unnecessary (response works without it)")
                            logger.info(f"Header '{header2}' is necessary (deduced from group test)")
                        else:
                            # If header1 is necessary, we need to test header2 as well
                            logger.info(f"Header '{header1}' is necessary (response changed without it)")
                            
                            # Test the second header
                            test_headers = {k: v for k, v in self.headers.items() 
                                           if k != header2 and k not in unnecessary_headers}
                            logger.info(f"Testing if header '{header2}' is necessary by removing it")
                            try:
                                test_response = self._send_request(test_headers)
                                test_length = len(test_response.content)
                                length_diff = abs(baseline_length - test_length)
                                
                                logger.info(f"Header '{header2}' test - Baseline: {baseline_length} bytes, Without header: {test_length} bytes, Diff: {length_diff} bytes")
                                
                                if self._compare_responses(baseline_response, test_response):
                                    unnecessary_headers.add(header2)
                                    logger.info(f"Header '{header2}' is unnecessary (response works without it)")
                                else:
                                    logger.info(f"Header '{header2}' is necessary (response changed without it)")
                            except Exception as e:
                                logger.error(f"Error testing header '{header2}': {e}")
                    except Exception as e:
                        logger.error(f"Error testing header '{header1}': {e}")
                        # Test header2 individually
                        self._divide_and_conquer({header2}, baseline_response, unnecessary_headers)
            except Exception as e:
                logger.error(f"Error testing header group: {e}")
                # Test headers individually
                self._divide_and_conquer({header1}, baseline_response, unnecessary_headers)
                self._divide_and_conquer({header2}, baseline_response, unnecessary_headers)
            return
            
        # Divide headers into two groups
        mid = len(headers_to_test) // 2
        group1 = set(list(headers_to_test)[:mid])
        group2 = headers_to_test - group1
        
        logger.info(f"Dividing {len(headers_to_test)} headers into Group 1 ({len(group1)} headers) and Group 2 ({len(group2)} headers)")
        
        # Test removing group1
        # Include all headers except those in group1 and those already known to be unnecessary
        test_headers = {k: v for k, v in self.headers.items() 
                       if k not in group1 and k not in unnecessary_headers}
        logger.info(f"Testing if all headers in Group 1 are necessary by removing them all: {group1}")
        try:
            test_response = self._send_request(test_headers)
            baseline_length = len(baseline_response.content)
            test_length = len(test_response.content)
            length_diff = abs(baseline_length - test_length)
            
            logger.info(f"Group 1 test - Baseline: {baseline_length} bytes, Without group: {test_length} bytes, Diff: {length_diff} bytes")
            
            if self._compare_responses(baseline_response, test_response):
                # All headers in group1 are unnecessary
                unnecessary_headers.update(group1)
                logger.info(f"All headers in Group 1 are unnecessary: {group1}")
            else:
                # Some headers in group1 might be necessary, test them individually
                logger.info(f"Group 1 contains necessary headers, testing individual headers")
                self._divide_and_conquer(group1, baseline_response, unnecessary_headers)
        except Exception as e:
            logger.error(f"Error testing Group 1: {e}")
            # If error occurs, test headers individually
            logger.info(f"Error occurred testing Group 1, testing individual headers")
            self._divide_and_conquer(group1, baseline_response, unnecessary_headers)
        
        # Test removing group2
        # First, remove any headers that have already been confirmed as unnecessary
        group2 = group2 - unnecessary_headers
        if not group2:
            logger.info("Skipping Group 2 testing as all headers in it have already been confirmed as unnecessary")
            return
            
        # Include all headers except those in group2 and those already known to be unnecessary
        test_headers = {k: v for k, v in self.headers.items() 
                       if k not in group2 and k not in unnecessary_headers}
        logger.info(f"Testing if all headers in Group 2 are necessary by removing them all: {group2}")
        try:
            test_response = self._send_request(test_headers)
            baseline_length = len(baseline_response.content)
            test_length = len(test_response.content)
            length_diff = abs(baseline_length - test_length)
            
            logger.info(f"Group 2 test - Baseline: {baseline_length} bytes, Without group: {test_length} bytes, Diff: {length_diff} bytes")
            
            if self._compare_responses(baseline_response, test_response):
                # All headers in group2 are unnecessary
                unnecessary_headers.update(group2)
                logger.info(f"All headers in Group 2 are unnecessary: {group2}")
            else:
                # Some headers in group2 might be necessary, test them individually
                logger.info(f"Group 2 contains necessary headers, testing individual headers")
                self._divide_and_conquer(group2, baseline_response, unnecessary_headers)
        except Exception as e:
            logger.error(f"Error testing Group 2: {e}")
            # If error occurs, test headers individually
            logger.info(f"Error occurred testing Group 2, testing individual headers")
            self._divide_and_conquer(group2, baseline_response, unnecessary_headers)
    
    @log_function_call
    def get_trimmed_request(self) -> str:
        """
        Get the trimmed HTTP request with only necessary headers.
        
        Returns:
            Trimmed raw HTTP request as a string
        """
        logger.info("Generating trimmed request with only necessary headers")
        unnecessary_headers = self.find_unnecessary_headers()
        necessary_headers = {k: v for k, v in self.headers.items() if k not in unnecessary_headers}
        logger.debug(f"Necessary headers: {list(necessary_headers.keys())}")
        
        # Reconstruct the request
        request_lines = [f"{self.method} {self.path} HTTP/2"]
        for key, value in necessary_headers.items():
            request_lines.append(f"{key}: {value}")
            
        if self.payload:
            request_lines.append("")
            request_lines.append("PAYLOAD")
            request_lines.append(self.payload)
            
        return '\n'.join(request_lines)
