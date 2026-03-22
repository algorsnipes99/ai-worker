import json
from typing import Dict, Any, List
from functions.function import Function
from sqlalchemy import create_engine, inspect, text
from sqlalchemy.exc import SQLAlchemyError

class GetSQLTableData(Function):
    """Returns breakdown of all table properties in an SQL database"""

    # Register the get_sql_table_data tool with its parameter schema.
    def __init__(self):
        super().__init__(
            name="get_sql_table_data",
            description="Get detailed breakdown of all tables and their properties in an SQL database",
            # needs_verification=True,
            verification_description="Access and analyze database schema information",
            parameters={
                "connection_string": {
                    "type": "string",
                    "description": "SQL database connection string (e.g., postgresql://user:pass@host:port/dbname)"
                },
                "include_sample_data": {
                    "type": "boolean",
                    "default": False,
                    "description": "Whether to include sample data from each table (first 3 rows)"
                }
            }
        )

    # Connect to the database, enumerate all tables, and return detailed schema info for each.
    # Supports postgresql, mysql, sqlite, and mssql connection strings.
    # @param args: Dict with 'connection_string' (required) and 'include_sample_data' (default False).
    # @returns: Dict with 'database_info' containing table count and list, or 'error' on failure.
    def execute(self, args: Dict[str, Any]) -> Dict[str, Any]:
        try:
            connection_string = args["connection_string"]
            include_sample_data = args.get("include_sample_data", False)

            if not connection_string:
                return {"error": "Connection string is required"}

            # Validate connection string format
            if not any(prefix in connection_string for prefix in
                      ["postgresql://", "mysql://", "sqlite://", "mssql://"]):
                return {"error": "Invalid connection string format. Must start with database type prefix"}

            engine = create_engine(connection_string)

            with engine.connect() as conn:
                inspector = inspect(conn)

                # Get all table names
                tables = inspector.get_table_names()

                result = {
                    "database_info": {
                        "tables_count": len(tables),
                        "tables": []
                    }
                }

                for table_name in tables:
                    table_info = self._get_table_details(inspector, table_name, conn, include_sample_data)
                    result["database_info"]["tables"].append(table_info)

                return result

        except SQLAlchemyError as e:
            return {"error": f"Database error: {str(e)}"}
        except Exception as e:
            return {"error": f"Unexpected error: {str(e)}"}

    # Collect columns, primary keys, foreign keys, indexes, row count, and optionally
    # sample data for a single table.
    # @param inspector: SQLAlchemy Inspector bound to the active connection.
    # @param table_name: Name of the table to inspect.
    # @param connection: Active SQLAlchemy connection for row count / sample queries.
    # @param include_sample_data: Whether to fetch up to 3 sample rows.
    # @returns: Dict with table metadata fields.
    def _get_table_details(self, inspector, table_name: str, connection, include_sample_data: bool) -> Dict[str, Any]:
        table_info = {
            "table_name": table_name,
            "columns": [],
            "primary_keys": [],
            "foreign_keys": [],
            "indexes": [],
            "row_count": 0
        }

        # Get column information
        columns = inspector.get_columns(table_name)
        for column in columns:
            column_info = {
                "name": column["name"],
                "type": str(column["type"]),
                "nullable": column.get("nullable", True),
                "default": column.get("default"),
                "autoincrement": column.get("autoincrement", False),
                "primary_key": column.get("primary_key", False)
            }
            table_info["columns"].append(column_info)

        # Get primary keys
        primary_keys = inspector.get_pk_constraint(table_name)
        table_info["primary_keys"] = primary_keys.get("constrained_columns", [])

        # Get foreign keys
        foreign_keys = inspector.get_foreign_keys(table_name)
        for fk in foreign_keys:
            fk_info = {
                "name": fk.get("name"),
                "constrained_columns": fk.get("constrained_columns", []),
                "referred_table": fk.get("referred_table"),
                "referred_columns": fk.get("referred_columns", [])
            }
            table_info["foreign_keys"].append(fk_info)

        # Get indexes
        indexes = inspector.get_indexes(table_name)
        for idx in indexes:
            idx_info = {
                "name": idx.get("name"),
                "columns": idx.get("column_names", []),
                "unique": idx.get("unique", False)
            }
            table_info["indexes"].append(idx_info)

        # Get row count
        try:
            result = connection.execute(text(f"SELECT COUNT(*) FROM {table_name}"))
            table_info["row_count"] = result.scalar()
        except:
            table_info["row_count"] = "unknown"

        # Get sample data if requested
        if include_sample_data and table_info["row_count"] > 0:
            try:
                result = connection.execute(text(f"SELECT * FROM {table_name} LIMIT 3"))
                sample_data = []
                for row in result:
                    # Convert row to dict
                    row_dict = {}
                    for i, value in enumerate(row):
                        column_name = result.keys()[i]
                        # Handle various data types for JSON serialization
                        if hasattr(value, 'isoformat'):
                            row_dict[column_name] = value.isoformat()
                        else:
                            row_dict[column_name] = value
                    sample_data.append(row_dict)
                table_info["sample_data"] = sample_data
            except:
                table_info["sample_data"] = "unavailable"

        return table_info
