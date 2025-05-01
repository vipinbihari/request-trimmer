import requests
import logging
from urllib.parse import urlparse, urlencode
from typing import Dict, List, Tuple, Any, Optional, Set
from .utils import logger, BaseTrimmer, parse_query_params, log_function_call, increment_request_counter
import time
from functools import wraps

def log_function_call(func):
    @wraps(func)
    def wrapper(*args, **kwargs):
        logger.debug(f"Calling {func.__name__}")
        return func(*args, **kwargs)
    return wrapper

class QueryTrimmer(BaseTrimmer):
    def __init__(self, base_url: str, raw_request: str, baseline_response: Optional[requests.Response] = None,
                 length_tolerance: int = 10, timeout: int = 10):
        """
        Initialize the QueryTrimmer.
        
        Args:
            base_url: Base URL for the request
            raw_request: Raw HTTP request
            baseline_response: Optional baseline response to compare against
            length_tolerance: Maximum allowed difference in response length (in bytes)
            timeout: Timeout for HTTP requests in seconds
        """
        super().__init__(base_url, raw_request, baseline_response, length_tolerance, timeout)
        
        # Parse query parameters from path
        self.query_params = parse_query_params(self.path)
        self.base_path = urlparse(self.path).path
    
    def _build_url(self, query_params: Dict[str, List[str]]) -> str:
        """
        Build URL with given query parameters.
        
        Args:
            query_params: Dictionary of query parameters
            
        Returns:
            URL string
        """
        # Convert query parameters to URL-encoded string
        query_string = urlencode(query_params, doseq=True) if query_params else ''
        
        # Build URL
        url = f"{self.base_url}{self.base_path}"
        if query_string:
            url += f"?{query_string}"
            
        return url
    
    @log_function_call
    def _send_request(self, query_params: Dict[str, List[str]]) -> requests.Response:
        """
        Send HTTP request with given query parameters.
        
        Args:
            query_params: Dictionary of query parameters
            
        Returns:
            Response object
        """
        url = self._build_url(query_params)
        logger.debug(f"Sending {self.method} request to {url} with {len(self.headers)} headers")
        if self.payload:
            logger.debug(f"Payload length: {len(self.payload)} bytes")
        start_time = time.time()
        
        try:
            # Increment the global request counter
            increment_request_counter()
            
            # Handle different HTTP methods
            if self.method == 'GET':
                response = requests.get(url, headers=self.headers, timeout=self.timeout)
            elif self.method == 'POST':
                # Send the payload exactly as it is in the raw request
                response = requests.post(url, headers=self.headers, data=self.payload, timeout=self.timeout)
            elif self.method == 'PUT':
                response = requests.put(url, headers=self.headers, data=self.payload, timeout=self.timeout)
            elif self.method == 'DELETE':
                response = requests.delete(url, headers=self.headers, timeout=self.timeout)
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
    
    def _get_baseline_response(self) -> requests.Response:
        """
        Get baseline response with all query parameters.
        
        Returns:
            Baseline response object
        """
        if self.baseline_response is None:
            self.baseline_response = self._send_request(self.query_params)
        return self.baseline_response
    
    @log_function_call
    def find_unnecessary_params(self, baseline_response: Optional[requests.Response] = None) -> Set[str]:
        """
        Find unnecessary query parameters using divide and conquer approach.
        
        Args:
            baseline_response: Optional baseline response to compare against
            
        Returns:
            Set of unnecessary query parameter names
        """
        if baseline_response is None:
            baseline_response = self._get_baseline_response()
            
        all_params = set(self.query_params.keys())
        unnecessary_params = set()
        
        logger.info(f"Testing {len(all_params)} query parameters using divide and conquer")
        
        # Use divide and conquer to find unnecessary query parameters
        self._divide_and_conquer(all_params, baseline_response, unnecessary_params)
        
        return unnecessary_params
        
    # Alias for backward compatibility
    find_unnecessary_query_params = find_unnecessary_params
    
    def _divide_and_conquer(self, params_to_test: Set[str], baseline_response: requests.Response, 
                           unnecessary_params: Set[str]) -> None:
        """
        Recursively apply divide and conquer to find unnecessary query parameters.
        
        Args:
            params_to_test: Set of query parameters to test
            baseline_response: Baseline response to compare against
            unnecessary_params: Set to store unnecessary parameters (modified in-place)
        """
        if not params_to_test:
            return
            
        # First, remove any parameters that have already been confirmed as unnecessary
        params_to_test = params_to_test - unnecessary_params
        if not params_to_test:
            return
            
        if len(params_to_test) == 1:
            # Base case: test a single parameter
            param = next(iter(params_to_test))
            # Include all parameters except the one being tested and those already known to be unnecessary
            test_params = {k: v for k, v in self.query_params.items() 
                          if k != param and k not in unnecessary_params}
            
            logger.info(f"Testing if parameter '{param}' is necessary by removing it")
            try:
                test_response = self._send_request(test_params)
                baseline_length = len(baseline_response.content)
                test_length = len(test_response.content)
                length_diff = abs(baseline_length - test_length)
                
                logger.info(f"Parameter '{param}' test - Baseline: {baseline_length} bytes, Without parameter: {test_length} bytes, Diff: {length_diff} bytes")
                
                if self._compare_responses(baseline_response, test_response):
                    unnecessary_params.add(param)
                    logger.info(f"Parameter '{param}' is unnecessary (response works without it)")
                else:
                    logger.info(f"Parameter '{param}' is necessary (response changed without it)")
            except Exception as e:
                logger.error(f"Error testing parameter '{param}': {e}")
            return
            
        if len(params_to_test) == 2:
            # Special case for exactly 2 parameters: if one is unnecessary, the other must be necessary
            params_list = list(params_to_test)
            param1, param2 = params_list[0], params_list[1]
            
            # First, test if the entire group is necessary by removing both parameters
            test_params = {k: v for k, v in self.query_params.items() 
                          if k not in params_to_test and k not in unnecessary_params}
            logger.info(f"Testing if all parameters in the group are necessary by removing them all: {params_to_test}")
            try:
                test_response = self._send_request(test_params)
                baseline_length = len(baseline_response.content)
                test_length = len(test_response.content)
                length_diff = abs(baseline_length - test_length)
                
                logger.info(f"Group test - Baseline: {baseline_length} bytes, Without group: {test_length} bytes, Diff: {length_diff} bytes")
                
                if self._compare_responses(baseline_response, test_response):
                    # Both parameters are unnecessary
                    unnecessary_params.update(params_to_test)
                    logger.info(f"All parameters in the group are unnecessary: {params_to_test}")
                    return
                else:
                    logger.info(f"Group contains at least one necessary parameter, testing individually")
                    
                    # Now test the first parameter
                    test_params = {k: v for k, v in self.query_params.items() 
                                  if k != param1 and k not in unnecessary_params}
                    logger.info(f"Testing if parameter '{param1}' is necessary by removing it")
                    try:
                        test_response = self._send_request(test_params)
                        test_length = len(test_response.content)
                        length_diff = abs(baseline_length - test_length)
                        
                        logger.info(f"Parameter '{param1}' test - Baseline: {baseline_length} bytes, Without parameter: {test_length} bytes, Diff: {length_diff} bytes")
                        
                        if self._compare_responses(baseline_response, test_response):
                            # If param1 is unnecessary, then param2 must be necessary
                            # (since removing both parameters breaks the response)
                            unnecessary_params.add(param1)
                            logger.info(f"Parameter '{param1}' is unnecessary (response works without it)")
                            logger.info(f"Parameter '{param2}' is necessary (deduced from group test)")
                        else:
                            # If param1 is necessary, we need to test param2 as well
                            logger.info(f"Parameter '{param1}' is necessary (response changed without it)")
                            
                            # Test the second parameter
                            test_params = {k: v for k, v in self.query_params.items() 
                                          if k != param2 and k not in unnecessary_params}
                            logger.info(f"Testing if parameter '{param2}' is necessary by removing it")
                            try:
                                test_response = self._send_request(test_params)
                                test_length = len(test_response.content)
                                length_diff = abs(baseline_length - test_length)
                                
                                logger.info(f"Parameter '{param2}' test - Baseline: {baseline_length} bytes, Without parameter: {test_length} bytes, Diff: {length_diff} bytes")
                                
                                if self._compare_responses(baseline_response, test_response):
                                    unnecessary_params.add(param2)
                                    logger.info(f"Parameter '{param2}' is unnecessary (response works without it)")
                                else:
                                    logger.info(f"Parameter '{param2}' is necessary (response changed without it)")
                            except Exception as e:
                                logger.error(f"Error testing parameter '{param2}': {e}")
                    except Exception as e:
                        logger.error(f"Error testing parameter '{param1}': {e}")
                        # Test param2 individually
                        self._divide_and_conquer({param2}, baseline_response, unnecessary_params)
            except Exception as e:
                logger.error(f"Error testing parameter group: {e}")
                # Test parameters individually
                self._divide_and_conquer({param1}, baseline_response, unnecessary_params)
                self._divide_and_conquer({param2}, baseline_response, unnecessary_params)
            return
            
        # Divide parameters into two groups
        mid = len(params_to_test) // 2
        group1 = set(list(params_to_test)[:mid])
        group2 = params_to_test - group1
        
        logger.info(f"Dividing {len(params_to_test)} parameters into Group 1 ({len(group1)} parameters) and Group 2 ({len(group2)} parameters)")
        
        # Test removing group1
        # Include all parameters except those in group1 and those already known to be unnecessary
        test_params = {k: v for k, v in self.query_params.items() 
                      if k not in group1 and k not in unnecessary_params}
        logger.info(f"Testing if all parameters in Group 1 are necessary by removing them all: {group1}")
        try:
            test_response = self._send_request(test_params)
            baseline_length = len(baseline_response.content)
            test_length = len(test_response.content)
            length_diff = abs(baseline_length - test_length)
            
            logger.info(f"Group 1 test - Baseline: {baseline_length} bytes, Without group: {test_length} bytes, Diff: {length_diff} bytes")
            
            if self._compare_responses(baseline_response, test_response):
                # All parameters in group1 are unnecessary
                unnecessary_params.update(group1)
                logger.info(f"All parameters in Group 1 are unnecessary: {group1}")
            else:
                # Some parameters in group1 might be necessary, test them individually
                logger.info(f"Group 1 contains necessary parameters, testing individual parameters")
                self._divide_and_conquer(group1, baseline_response, unnecessary_params)
        except Exception as e:
            logger.error(f"Error testing Group 1: {e}")
            # If error occurs, test parameters individually
            logger.info(f"Error occurred testing Group 1, testing individual parameters")
            self._divide_and_conquer(group1, baseline_response, unnecessary_params)
        
        # Test removing group2
        # First, remove any parameters that have already been confirmed as unnecessary
        group2 = group2 - unnecessary_params
        if not group2:
            logger.info("Skipping Group 2 testing as all parameters in it have already been confirmed as unnecessary")
            return
            
        # Include all parameters except those in group2 and those already known to be unnecessary
        test_params = {k: v for k, v in self.query_params.items() 
                      if k not in group2 and k not in unnecessary_params}
        logger.info(f"Testing if all parameters in Group 2 are necessary by removing them all: {group2}")
        try:
            test_response = self._send_request(test_params)
            baseline_length = len(baseline_response.content)
            test_length = len(test_response.content)
            length_diff = abs(baseline_length - test_length)
            
            logger.info(f"Group 2 test - Baseline: {baseline_length} bytes, Without group: {test_length} bytes, Diff: {length_diff} bytes")
            
            if self._compare_responses(baseline_response, test_response):
                # All parameters in group2 are unnecessary
                unnecessary_params.update(group2)
                logger.info(f"All parameters in Group 2 are unnecessary: {group2}")
            else:
                # Some parameters in group2 might be necessary, test them individually
                logger.info(f"Group 2 contains necessary parameters, testing individual parameters")
                self._divide_and_conquer(group2, baseline_response, unnecessary_params)
        except Exception as e:
            logger.error(f"Error testing Group 2: {e}")
            # If error occurs, test parameters individually
            logger.info(f"Error occurred testing Group 2, testing individual parameters")
            self._divide_and_conquer(group2, baseline_response, unnecessary_params)
    
    def get_trimmed_query_params(self) -> Dict[str, List[str]]:
        """
        Get only the necessary query parameters.
        
        Returns:
            Dictionary of necessary query parameters
        """
        unnecessary_params = self.find_unnecessary_params()
        necessary_params = {k: v for k, v in self.query_params.items() if k not in unnecessary_params}
        return necessary_params
    
    def get_trimmed_path(self) -> str:
        """
        Get the trimmed path with only necessary query parameters.
        
        Returns:
            Trimmed path string
        """
        necessary_params = self.get_trimmed_query_params()
        query_string = urlencode(necessary_params, doseq=True) if necessary_params else ''
        
        if query_string:
            return f"{self.base_path}?{query_string}"
        else:
            return self.base_path
