"""Custom exception for tool permission requirements"""

class ToolPermissionRequiredException(Exception):
    """
    Exception raised when a tool requires user permission but none exists.
    This exception should bubble up to index.js for user prompting.
    """

    # Capture all metadata needed for the external interface to prompt the user.
    # child_resume_guid is set later by delegation code when this exception crosses
    # a parent-child agent boundary.
    # @param tool_name: Name of the tool that requires permission.
    # @param tool_description: Full tool description shown for context.
    # @param verification_description: Short human-readable approval prompt.
    # @param tool_args: Arguments the tool was called with (shown to the user).
    # @param execution_context: Additional context dict (e.g. timestamp).
    def __init__(self, tool_name: str, tool_description: str, verification_description: str,
                 tool_args: dict = None, execution_context: dict = None):
        self.tool_name = tool_name
        self.tool_description = tool_description
        self.verification_description = verification_description
        self.tool_args = tool_args or {}
        self.execution_context = execution_context or {}
        self.child_resume_guid = None  # Will be set by delegation function if needed

        message = f"User permission required for tool '{tool_name}': {verification_description}"
        super().__init__(message)

    # Serialize the exception to a dict for JSON transport to the external interface.
    # Includes child_resume_guid if set (needed when the exception crossed a delegation boundary).
    # @returns: Dict with all exception fields; child_resume_guid included only if present.
    def to_dict(self) -> dict:
        result = {
            "exception_type": "ToolPermissionRequiredException",
            "tool_name": self.tool_name,
            "tool_description": self.tool_description,
            "verification_description": self.verification_description,
            "tool_args": self.tool_args,
            "execution_context": self.execution_context,
            "message": str(self)
        }

        # Include child_resume_guid if available
        if hasattr(self, 'child_resume_guid') and self.child_resume_guid:
            result["child_resume_guid"] = self.child_resume_guid

        return result
