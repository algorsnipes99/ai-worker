import json
from typing import Dict, Any, List
from functions.function import Function
from sqlalchemy import create_engine, text
from sqlalchemy.exc import SQLAlchemyError

class SQLQuery(Function):
    """Execute SQL queries and return results in array format"""

    # Register the sql_query tool with its parameter schema.
    def __init__(self):
        super().__init__(
            name="sql_query",
            description="Execute SQL queries on a database and return results in array format",
            # needs_verification=True,
            verification_description="Execute SQL queries on databases",
            parameters={
                "connection_string": {
                    "type": "string",
                    "description": "SQL database connection string (e.g., postgresql://user:pass@host:port/dbname)"
                },
                "query": {
                    "type": "string",
                    "description": "SQL query to execute (SELECT, INSERT, UPDATE, DELETE, etc.)"
                },
                "limit": {
                    "type": "integer",
                    "default": 1000,
                    "description": "Maximum number of rows to return (for SELECT queries)"
                },
                "parameters": {
                    "type": "object",
                    "default": {},
                    "description": "Query parameters for parameterized queries"
                }
            }
        )

    # Validate inputs, connect to the database, and dispatch to the appropriate
    # query executor. Blocks DROP, TRUNCATE, and ALTER operations.
    # @param args: Dict with 'connection_string', 'query', 'limit' (default 1000),
    #              and 'parameters' (default {}).
    # @returns: Query result dict, or 'error' on validation/database failure.
    def execute(self, args: Dict[str, Any]) -> Dict[str, Any]:
        try:
            connection_string = args["connection_string"]
            query = args["query"]
            limit = args.get("limit", 1000)
            parameters = args.get("parameters", {})

            if not connection_string:
                return {"error": "Connection string is required"}

            if not query:
                return {"error": "SQL query is required"}

            # Validate connection string format
            if not any(prefix in connection_string for prefix in
                      ["postgresql://", "mysql://", "sqlite://", "mssql://"]):
                return {"error": "Invalid connection string format. Must start with database type prefix"}

            # Validate query to prevent destructive operations without proper handling
            query_upper = query.upper().strip()
            if query_upper.startswith(("DROP", "TRUNCATE", "ALTER")):
                return {
                    "error": "Destructive operations (DROP, TRUNCATE, ALTER) are not allowed through this function. Use update_sql function for data modifications."
                }

            engine = create_engine(connection_string)

            with engine.connect() as conn:
                # Handle SELECT queries differently
                if query_upper.startswith("SELECT"):
                    return self._execute_select_query(conn, query, limit, parameters)
                else:
                    return self._execute_modification_query(conn, query, parameters)

        except SQLAlchemyError as e:
            return {"error": f"Database error: {str(e)}"}
        except Exception as e:
            return {"error": f"Unexpected error: {str(e)}"}

    # Run a SELECT query, auto-appending LIMIT if not already present.
    # Serializes dates via isoformat and other values via str.
    # @param connection: Active SQLAlchemy connection.
    # @param query: SELECT SQL string.
    # @param limit: Row cap to append if LIMIT not in query.
    # @param parameters: Bind parameters dict for parameterized queries.
    # @returns: Dict with 'status', 'query_type', 'columns', 'row_count', 'data', 'limited'.
    def _execute_select_query(self, connection, query: str, limit: int, parameters: Dict[str, Any]) -> Dict[str, Any]:
        try:
            # Add LIMIT if not already present and it's a SELECT query
            query_upper = query.upper()
            if "LIMIT" not in query_upper:
                query += f" LIMIT {limit}"

            result = connection.execute(text(query), parameters)

            # Get column names
            columns = list(result.keys())

            # Convert results to array of dictionaries
            rows = []
            for row in result:
                row_dict = {}
                for i, value in enumerate(row):
                    column_name = columns[i]
                    # Handle various data types for JSON serialization
                    if value is None:
                        row_dict[column_name] = None
                    elif hasattr(value, 'isoformat'):
                        row_dict[column_name] = value.isoformat()
                    elif hasattr(value, '__str__'):
                        row_dict[column_name] = str(value)
                    else:
                        row_dict[column_name] = value
                rows.append(row_dict)

            return {
                "status": "success",
                "query_type": "SELECT",
                "columns": columns,
                "row_count": len(rows),
                "data": rows,
                "limited": "LIMIT" not in query_upper.upper()  # Indicate if we added limit
            }

        except Exception as e:
            return {"error": f"Query execution error: {str(e)}"}

    # Run an INSERT, UPDATE, or DELETE query and commit the transaction.
    # Rolls back on failure.
    # @param connection: Active SQLAlchemy connection.
    # @param query: Non-SELECT SQL string.
    # @param parameters: Bind parameters dict.
    # @returns: Dict with 'status', 'query_type', 'affected_rows', 'message'.
    def _execute_modification_query(self, connection, query: str, parameters: Dict[str, Any]) -> Dict[str, Any]:
        try:
            result = connection.execute(text(query), parameters)
            connection.commit()

            # Get affected row count
            rowcount = result.rowcount

            query_type = self._get_query_type(query)

            return {
                "status": "success",
                "query_type": query_type,
                "affected_rows": rowcount,
                "message": f"{query_type} operation completed successfully"
            }

        except Exception as e:
            connection.rollback()
            return {"error": f"Modification query error: {str(e)}"}

    # Determine the SQL statement type from the first keyword of the query.
    # @param query: SQL string to classify.
    # @returns: One of 'INSERT', 'UPDATE', 'DELETE', 'CREATE', 'ALTER', or 'OTHER'.
    def _get_query_type(self, query: str) -> str:
        query_upper = query.upper().strip()

        if query_upper.startswith("INSERT"):
            return "INSERT"
        elif query_upper.startswith("UPDATE"):
            return "UPDATE"
        elif query_upper.startswith("DELETE"):
            return "DELETE"
        elif query_upper.startswith("CREATE"):
            return "CREATE"
        elif query_upper.startswith("ALTER"):
            return "ALTER"
        else:
            return "OTHER"
