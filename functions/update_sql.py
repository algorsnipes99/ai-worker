import json
from typing import Dict, Any, List
from functions.function import Function
from sqlalchemy import create_engine, text, Table, MetaData, Column, Integer, String
from sqlalchemy.exc import SQLAlchemyError

class UpdateSQL(Function):
    """Update and insert data into SQL tables with validation"""

    # Register the update_sql tool with its parameter schema.
    def __init__(self):
        super().__init__(
            name="update_sql",
            description="Update existing data or insert new data into SQL tables with validation",
            # needs_verification=True,
            verification_description="Modify data in SQL databases",
            parameters={
                "connection_string": {
                    "type": "string",
                    "description": "SQL database connection string (e.g., postgresql://user:pass@host:port/dbname)"
                },
                "operation": {
                    "type": "string",
                    "enum": ["insert", "update", "upsert"],
                    "description": "Type of operation to perform"
                },
                "table_name": {
                    "type": "string",
                    "description": "Name of the table to modify"
                },
                "data": {
                    "type": "object",
                    "description": "Data to insert or update (key-value pairs)"
                },
                "where_clause": {
                    "type": "object",
                    "default": {},
                    "description": "WHERE clause conditions for UPDATE operations (key-value pairs)"
                },
                "primary_key": {
                    "type": "string",
                    "description": "Primary key column name for UPSERT operations"
                }
            }
        )

    # Validate inputs, connect to the database, validate the table and data,
    # then dispatch to the appropriate operation method.
    # @param args: Dict with 'connection_string', 'operation', 'table_name', 'data',
    #              optional 'where_clause' and 'primary_key'.
    # @returns: Operation result dict, or 'error' on validation/database failure.
    def execute(self, args: Dict[str, Any]) -> Dict[str, Any]:
        try:
            connection_string = args["connection_string"]
            operation = args["operation"]
            table_name = args["table_name"]
            data = args["data"]
            where_clause = args.get("where_clause", {})
            primary_key = args.get("primary_key")

            if not connection_string:
                return {"error": "Connection string is required"}

            if not table_name:
                return {"error": "Table name is required"}

            if not data:
                return {"error": "Data is required for insert/update operations"}

            # Validate connection string format
            if not any(prefix in connection_string for prefix in
                      ["postgresql://", "mysql://", "sqlite://", "mssql://"]):
                return {"error": "Invalid connection string format. Must start with database type prefix"}

            engine = create_engine(connection_string)

            with engine.connect() as conn:
                # Validate table exists and get schema
                table_info = self._validate_table(conn, table_name)
                if "error" in table_info:
                    return table_info

                # Validate data against table schema
                validation_result = self._validate_data(table_info, data, operation)
                if "error" in validation_result:
                    return validation_result

                # Perform the operation
                if operation == "insert":
                    return self._perform_insert(conn, table_name, data)
                elif operation == "update":
                    return self._perform_update(conn, table_name, data, where_clause)
                elif operation == "upsert":
                    return self._perform_upsert(conn, table_name, data, primary_key)
                else:
                    return {"error": f"Unsupported operation: {operation}"}

        except SQLAlchemyError as e:
            return {"error": f"Database error: {str(e)}"}
        except Exception as e:
            return {"error": f"Unexpected error: {str(e)}"}

    # Use SQLAlchemy reflection to check that the table exists and gather column metadata.
    # @param connection: Active SQLAlchemy connection.
    # @param table_name: Name of the table to validate.
    # @returns: Dict with 'exists', 'columns' (name → metadata), and 'primary_keys'.
    def _validate_table(self, connection, table_name: str) -> Dict[str, Any]:
        try:
            metadata = MetaData()
            table = Table(table_name, metadata, autoload_with=connection.engine)

            # Get column information
            columns = {}
            for column in table.columns:
                columns[column.name] = {
                    "type": str(column.type),
                    "nullable": column.nullable,
                    "primary_key": column.primary_key,
                    "autoincrement": column.autoincrement
                }

            return {
                "exists": True,
                "columns": columns,
                "primary_keys": [col.name for col in table.primary_key.columns]
            }

        except Exception as e:
            return {"error": f"Table validation failed: {str(e)}"}

    # Check that all provided data keys exist as columns in the table and that
    # no required (non-nullable, non-autoincrement) columns are missing for INSERT.
    # @param table_info: Dict returned by _validate_table.
    # @param data: The data dict to validate.
    # @param operation: 'insert', 'update', or 'upsert' — affects required-column logic.
    # @returns: {'valid': True} on success, or {'error': message} on failure.
    def _validate_data(self, table_info: Dict[str, Any], data: Dict[str, Any], operation: str) -> Dict[str, Any]:
        columns = table_info["columns"]
        primary_keys = table_info["primary_keys"]

        # Check for unknown columns
        unknown_columns = [col for col in data.keys() if col not in columns]
        if unknown_columns:
            return {"error": f"Unknown columns: {unknown_columns}. Available columns: {list(columns.keys())}"}

        # For INSERT operations, check required columns (non-nullable, non-autoincrement)
        if operation == "insert":
            required_columns = [
                col_name for col_name, col_info in columns.items()
                if not col_info["nullable"] and not col_info["autoincrement"]
            ]
            missing_columns = [col for col in required_columns if col not in data]
            if missing_columns:
                return {"error": f"Missing required columns for INSERT: {missing_columns}"}

        # For UPDATE operations with WHERE clause, validate WHERE columns exist
        # (This would be handled in the calling method)

        return {"valid": True}

    # Execute a parameterized INSERT statement and commit.
    # @param connection: Active SQLAlchemy connection.
    # @param table_name: Target table name.
    # @param data: Column → value dict to insert.
    # @returns: Dict with 'status', 'operation', 'affected_rows', 'inserted_data', 'message'.
    def _perform_insert(self, connection, table_name: str, data: Dict[str, Any]) -> Dict[str, Any]:
        try:
            # Build INSERT statement
            columns = ", ".join(data.keys())
            values = ", ".join([f":{key}" for key in data.keys()])
            query = f"INSERT INTO {table_name} ({columns}) VALUES ({values})"

            result = connection.execute(text(query), data)
            connection.commit()

            return {
                "status": "success",
                "operation": "insert",
                "affected_rows": result.rowcount,
                "inserted_data": data,
                "message": f"Successfully inserted {result.rowcount} row(s) into {table_name}"
            }

        except Exception as e:
            connection.rollback()
            return {"error": f"INSERT operation failed: {str(e)}"}

    # Execute a parameterized UPDATE with a mandatory WHERE clause and commit.
    # Rejects updates without a WHERE clause to prevent accidental mass updates.
    # @param connection: Active SQLAlchemy connection.
    # @param table_name: Target table name.
    # @param data: Column → value dict of fields to update.
    # @param where_clause: Column → value dict for the WHERE conditions (required).
    # @returns: Dict with 'status', 'operation', 'affected_rows', 'updated_data',
    #           'where_conditions', 'message'.
    def _perform_update(self, connection, table_name: str, data: Dict[str, Any], where_clause: Dict[str, Any]) -> Dict[str, Any]:
        try:
            if not where_clause:
                return {"error": "WHERE clause is required for UPDATE operations to prevent mass updates"}

            # Build SET clause
            set_clause = ", ".join([f"{key} = :{key}" for key in data.keys()])

            # Build WHERE clause
            where_conditions = " AND ".join([f"{key} = :where_{key}" for key in where_clause.keys()])

            query = f"UPDATE {table_name} SET {set_clause} WHERE {where_conditions}"

            # Combine data and where parameters
            params = data.copy()
            for key, value in where_clause.items():
                params[f"where_{key}"] = value

            result = connection.execute(text(query), params)
            connection.commit()

            return {
                "status": "success",
                "operation": "update",
                "affected_rows": result.rowcount,
                "updated_data": data,
                "where_conditions": where_clause,
                "message": f"Successfully updated {result.rowcount} row(s) in {table_name}"
            }

        except Exception as e:
            connection.rollback()
            return {"error": f"UPDATE operation failed: {str(e)}"}

    # Attempt an UPDATE by primary key; if no rows matched, fall back to INSERT.
    # @param connection: Active SQLAlchemy connection.
    # @param table_name: Target table name.
    # @param data: Column → value dict (must include the primary key column).
    # @param primary_key: Name of the primary key column used for the WHERE clause.
    # @returns: Result dict from _perform_update or _perform_insert.
    def _perform_upsert(self, connection, table_name: str, data: Dict[str, Any], primary_key: str) -> Dict[str, Any]:
        try:
            if not primary_key:
                return {"error": "Primary key is required for UPSERT operations"}

            if primary_key not in data:
                return {"error": f"Primary key '{primary_key}' must be included in the data"}

            # First try to update
            where_clause = {primary_key: data[primary_key]}
            update_result = self._perform_update(connection, table_name, data, where_clause)

            # If no rows were updated, try to insert
            if update_result.get("affected_rows", 0) == 0:
                # Remove the update result from connection state
                connection.rollback()
                return self._perform_insert(connection, table_name, data)
            else:
                return update_result

        except Exception as e:
            connection.rollback()
            return {"error": f"UPSERT operation failed: {str(e)}"}
