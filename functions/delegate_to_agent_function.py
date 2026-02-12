from functions.function import Function
from typing import Dict, Any
import os
import sys
import json

# Add the parent directory to sys.path to import agents
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from planner_agent import PlannerAgent
from agents.file_manager_agent import FileManagerAgent
from agents.command_prompt_agent import CommandPromptAgent
from agents.api_agent import ApiAgent
from agents.database_agent import DatabaseAgent
from agents.base_agent import BaseAgent

class DelegateToAgentFunction(Function):
    """Delegate tasks to specialized agents"""
    
    def __init__(self, calling_agent=None, parent_resume_guid=None, child_resume_guid=None):
        self.calling_agent = calling_agent
        self.parent_resume_guid = parent_resume_guid
        self.child_resume_guid = child_resume_guid
        super().__init__(
            name="delegateToAgent",
            description="Delegate a task to a specialized agent that will create a plan and execute it",
            parameters={
                "agent_name": {
                    "type": "string",
                    "enum": ["file_manager", "command_prompt", "api", "database"],
                    "description": "The name of the specialized agent to delegate to"
                },
                "task_description": {
                    "type": "string", 
                    "description": "Detailed description of the task to be performed by the agent"
                },
                "task_context": {
                    "type": "string", 
                    "description": "Some important context information the agent might need to complete their tasks"
                }
                # resume_guid removed - now provided through constructor only
            }
        )
        
        # Mapping of agent names to their planning prompts and agent classes
        self.agent_config = {
            "file_manager": {
                "planning_prompt": "prompts/file_manager_planning_prompt.txt",
                "agent_class": FileManagerAgent
            },
            "command_prompt": {
                "planning_prompt": "prompts/command_prompt_planning_prompt.txt", 
                "agent_class": CommandPromptAgent
            },
            "api": {
                "planning_prompt": "prompts/api_agent_planning_prompt.txt",
                "agent_class": ApiAgent
            },
            "database": {
                "planning_prompt": "prompts/database_agent_planning_prompt.txt",
                "agent_class": DatabaseAgent
            }
        }
        
    def add_between_context_tags(text, new_content):
        return text.replace("<context>", f"<context>{new_content}", 1)
    
    def execute(self, args: Dict[str, Any]) -> Dict[str, Any]:
        """Execute the agent delegation"""
        try:
            agent_name = args.get("agent_name")
            task_description = args.get("task_description")
            task_context = args.get("task_context", "")
            # Use child_resume_guid from constructor, or extract from calling agent's state if resuming
            child_resume_guid = self.child_resume_guid
            
            # If we don't have a child_resume_guid but we're resuming (parent_resume_guid exists),
            # try to extract it from the calling agent's execution state
            if not child_resume_guid and self.parent_resume_guid and self.calling_agent:
                if hasattr(self.calling_agent, 'execution_state') and self.calling_agent.execution_state:
                    # Look for the last delegation result that might have a child_resume_guid
                    last_tool_results = self.calling_agent.execution_state.get("last_tool_results", [])
                    for tool_result in reversed(last_tool_results):  # Check most recent first
                        if tool_result.get("tool_call_id"):
                            # Try to load the saved messages to find delegation results
                            try:
                                messages = self.calling_agent._load_messages(self.calling_agent.message_guid)
                                if messages:
                                    for msg in reversed(messages):
                                        if (msg.get("role") == "tool" and 
                                            msg.get("tool_call_id") == tool_result["tool_call_id"]):
                                            content = json.loads(msg.get("content", "{}"))
                                            if content.get("child_resume_guid"):
                                                child_resume_guid = content["child_resume_guid"]
                                                print(f"🔄 Found child resume GUID from state: {child_resume_guid[:8]}...")
                                                break
                                    if child_resume_guid:
                                        break
                            except:
                                pass  # If we can't load state, continue without resumption
            
            task_context = '<context>' + task_context + '</context>' if task_context else ''
            
            if not agent_name or not task_description:
                return {
                    "status": "error",
                    "message": "Both agent_name and task_description are required"
                }
            
            if agent_name not in self.agent_config:
                return {
                    "status": "error", 
                    "message": f"Unknown agent: {agent_name}. Available agents: {list(self.agent_config.keys())}"
                }
            
            print(f"Delegating tasks to {agent_name}" + 
                  (f" (resuming {child_resume_guid[:8]}...)" if child_resume_guid else ""))

            config = self.agent_config[agent_name]
            planning_prompt_path = config["planning_prompt"]
            agent_class = config["agent_class"]
            
            # Use a hardcoded API key (in production, this should come from environment)
            api_key = 'sk-3dcb45f26a4745129f4aa6dd846c25c5'
            
            # If resuming, skip planning and go straight to execution
            plan_text = None
            plan_guid = None
            
            if not child_resume_guid:
                # STEP 1: Create plan using specialized planning prompt
                try:
                    planner = PlannerAgent(api_key)
                    planning_result = planner.plan(task_description + task_context, planning_prompt_path)
                    
                    if "error" in planning_result:
                        return {
                            "status": "error",
                            "message": f"Planning failed: {planning_result['error']}"
                        }
                    
                    if "choices" not in planning_result or len(planning_result["choices"]) == 0:
                        return {
                            "status": "error",
                            "message": "No plan generated"
                        }
                    
                    plan_text = planning_result["choices"][0]["message"]["content"]
                    plan_guid = planning_result.get("plan_guid")
                    
                except Exception as e:
                    return {
                        "status": "error",
                        "message": f"Planning error: {str(e)}"
                    }
            else:
                # When resuming, we'll use a placeholder plan since the real plan is already in the state file
                plan_text = "Resuming previous plan execution"
            
            # STEP 2: Execute plan using specialized agent
            try:
                # Create agent with parent-child relationship and possible resumption
                agent = agent_class(
                    task_description, 
                    plan_text, 
                    api_key,
                    parent_message_guid=self.calling_agent.message_guid if self.calling_agent else None,
                    parent_resume_guid=self.parent_resume_guid,
                    child_resume_guid=child_resume_guid
                )
                
                # Run the agent (with optional resumption)
                execution_result = agent.run()
                
                if "error" in execution_result:
                    return {
                        "status": "error",
                        "message": f"Execution failed: {execution_result['error']}",
                        "agent_state": execution_result.get("status", BaseAgent.STATE_ERROR)
                    }
                
                if "choices" not in execution_result or len(execution_result["choices"]) == 0:
                    return {
                        "status": "error", 
                        "message": "No execution result",
                        "agent_state": BaseAgent.STATE_ERROR
                    }
                
                execution_response = execution_result["choices"][0]["message"]["content"]
                execution_guid = execution_result.get("message_guid")
                
                # Get final state information to include in the result
                final_state = "unknown"
                if hasattr(agent, "execution_state"):
                    final_state = agent.execution_state.get("status", BaseAgent.STATE_COMPLETED)
                
                return {
                    "status": "success",
                    "agent_name": agent_name,
                    "task_description": task_description,
                    "plan_guid": plan_guid,
                    "execution_guid": execution_guid,
                    "agent_state": final_state,
                    "plan_preview": plan_text[:200] + "..." if plan_text and len(plan_text) > 200 else plan_text,
                    "result": execution_response,
                    "message": f"Task successfully delegated to {agent_name} agent and completed",
                    "resumable": True,
                    "child_resume_guid": execution_guid  # Include the execution_guid for potential future resumption
                }
                
            except Exception as e:
                # Import the exception class for proper handling
                from exceptions.tool_permission_exception import ToolPermissionRequiredException
                
                # Re-raise permission exceptions to allow user prompting
                if isinstance(e, ToolPermissionRequiredException):
                    print(f"🔐 Permission required for {e.tool_name}, re-raising from delegation...")
                    
                    # CRITICAL: Capture the child agent's message_guid before re-raising
                    # This allows resumption to find the interrupted child agent
                    if hasattr(agent, 'message_guid') and agent.message_guid:
                        print(f"🔄 Capturing child resume GUID: {agent.message_guid[:8]}...")
                        e.child_resume_guid = agent.message_guid
                    
                    raise e
                
                # Handle other exceptions normally
                return {
                    "status": "error",
                    "message": f"Execution error: {str(e)}",
                    "agent_state": BaseAgent.STATE_ERROR,
                    "error_details": str(e)
                }
                
        except Exception as e:
            # Import the exception class for proper handling
            from exceptions.tool_permission_exception import ToolPermissionRequiredException
            
            # Re-raise permission exceptions to allow user prompting
            if isinstance(e, ToolPermissionRequiredException):
                print(f"🔐 Permission required for {e.tool_name}, final re-raise from delegation...")
                raise e
            
            # Handle other exceptions normally
            return {
                "status": "error",
                "message": f"Delegation error: {str(e)}",
                "error_details": str(e)
            }
