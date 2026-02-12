from functions.function import Function
from typing import Dict, Any, Optional
import requests
import json
import urllib3
from requests.adapters import HTTPAdapter

class ApiFunction(Function):
    """Make generic API calls (GET/POST) to any endpoint"""
    def __init__(self):
        super().__init__(
            name="makeApiCall",
            description="Make HTTP requests to any API endpoint",
            parameters={
                "url": {
                    "type": "string",
                    "description": "The API endpoint URL"
                },
                "method": {
                    "type": "string",
                    "enum": ["GET", "POST"],
                    "default": "GET",
                    "description": "HTTP method to use"
                },
                "headers": {
                    "type": "object",
                    "description": "Request headers as key-value pairs",
                    "default": {}
                },
                "query_params": {
                    "type": "object",
                    "description": "Query parameters for GET requests",
                    "default": {}
                },
                "payload": {
                    "type": "object",
                    "description": "Request payload for POST requests",
                    "default": {}
                },
                "auth_token": {
                    "type": "string",
                    "description": "Optional authorization token",
                    "default": ""
                },
                "agent_mode": {
                    "type": "boolean",
                    "description": "Enable HTTPS agent to bypass SSL verification",
                    "default": False
                }
            }
        )

    def execute(self, args: Dict[str, Any]) -> Dict[str, Any]:
        """Execute the API call"""
        try:
            headers = args.get("headers", {})
            if args.get("auth_token"):
                headers["Authorization"] = f"Bearer {args['auth_token']}"

            request_kwargs = {
                "headers": headers
            }

            if args.get("agent_mode"):
                urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)
                session = requests.Session()
                session.mount('https://', HTTPAdapter(max_retries=3))
                request_kwargs["verify"] = False
                response_func = session.get if args["method"] == "GET" else session.post
            else:
                response_func = requests.get if args["method"] == "GET" else requests.post

            request_kwargs["params"] = args.get("query_params", {}) if args["method"] == "GET" else None
            request_kwargs["json"] = args.get("payload", {}) if args["method"] == "POST" else None
            response = response_func(args["url"], **request_kwargs)

            return {
                "status": "success",
                "status_code": response.status_code,
                "response": response.json() if response.content else None,
                "headers": dict(response.headers)
            }
        except Exception as e:
            return {
                "status": "error",
                "message": str(e)
            }
