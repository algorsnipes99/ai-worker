import mysql.connector
from urllib.parse import urlparse
from typing import Dict, Any, List, Optional
from functions.function import Function

class DatabaseFunction(Function):
    """Retrieves database schema information including tables, columns, and foreign keys"""
    
    def __init__(self):
        super().__init__(
            name="getDatabaseSchema",
            description="Retrieves all tables and their schemas from a MySQL database including columns, data types, constraints, and foreign keys",
            # needs_verification=True,
            verification_description="Access database schema information including sensitive connection details",
            parameters={
                "connection_string": {
                    "type": "string",
                    "description": "MySQL connection string (mysql://user:password@host/database)"
                },
                "include_data": {
                    "type": "boolean",
                    "default": False,
                    "description": "Include sample data from tables"
                },
                "max_rows": {
                    "type": "integer",
                    "default": 5,
                    "description": "Maximum number of sample rows to include per table"
                }
            }
        )
    
    def _parse_connection_string(self, connection_string: str) -> Dict[str, str]:
        """Parse MySQL connection string"""
        try:
            parsed = urlparse(connection_string)
            if parsed.scheme != 'mysql':
                raise ValueError("Connection string must start with 'mysql://'")
            
            username = parsed.username
            password = parsed.password
            host = parsed.hostname
            port = parsed.port or 3306
            database = parsed.path.lstrip('/')
            
            return {
                'host': host,
                'port': port,
                'user': username,
                'password': password,
                'database': database
            }
        except Exception as e:
            raise ValueError(f"Invalid connection string format: {str(e)}")
    
    def _get_connection(self, connection_params: Dict[str, str]):
        """Establish MySQL connection"""
        try:
            return mysql.connector.connect(**connection_params)
        except mysql.connector.Error as e:
            raise Exception(f"Database connection failed: {str(e)}")
    
    def _get_tables(self, conn) -> List[str]:
        """Get list of tables in the database"""
        cursor = conn.cursor()
        cursor.execute("""
            SELECT TABLE_NAME 
            FROM INFORMATION_SCHEMA.TABLES 
            WHERE TABLE_SCHEMA = DATABASE() 
            AND TABLE_TYPE = 'BASE TABLE'
            ORDER BY TABLE_NAME
        """)
        return [row[0] for row in cursor.fetchall()]
    
    def _get_table_columns(self, conn, table_name: str) -> List[Dict[str, Any]]:
        """Get column information for a table"""
        cursor = conn.cursor(dictionary=True)
        cursor.execute("""
            SELECT 
                COLUMN_NAME,
                COLUMN_TYPE,
                IS_NULLABLE,
                COLUMN_KEY,
                COLUMN_DEFAULT,
                EXTRA
            FROM INFORMATION_SCHEMA.COLUMNS 
            WHERE TABLE_SCHEMA = DATABASE() 
            AND TABLE_NAME = %s
            ORDER BY ORDINAL_POSITION
        """, (table_name,))
        
        columns = []
        for row in cursor.fetchall():
            columns.append({
                "name": row['COLUMN_NAME'],
                "type": row['COLUMN_TYPE'],
                "nullable": row['IS_NULLABLE'] == 'YES',
                "primary_key": 'PRI' in row['COLUMN_KEY'],
                "default": row['COLUMN_DEFAULT'],
                "auto_increment": 'auto_increment' in row['EXTRA'].lower() if row['EXTRA'] else False
            })
        return columns
    
    def _get_foreign_keys(self, conn, table_name: str) -> List[Dict[str, Any]]:
        """Get foreign key information for a table"""
        cursor = conn.cursor(dictionary=True)
        cursor.execute("""
            SELECT 
                kcu.COLUMN_NAME,
                kcu.REFERENCED_TABLE_NAME,
                kcu.REFERENCED_COLUMN_NAME,
                rc.UPDATE_RULE,
                rc.DELETE_RULE
            FROM INFORMATION_SCHEMA.KEY_COLUMN_USAGE kcu
            JOIN INFORMATION_SCHEMA.REFERENTIAL_CONSTRAINTS rc 
                ON kcu.CONSTRAINT_NAME = rc.CONSTRAINT_NAME 
                AND kcu.TABLE_SCHEMA = rc.CONSTRAINT_SCHEMA
            WHERE kcu.TABLE_SCHEMA = DATABASE() 
            AND kcu.TABLE_NAME = %s
            AND kcu.REFERENCED_TABLE_NAME IS NOT NULL
        """, (table_name,))
        
        foreign_keys = []
        for row in cursor.fetchall():
            foreign_keys.append({
                "column": row['COLUMN_NAME'],
                "references_table": row['REFERENCED_TABLE_NAME'],
                "references_column": row['REFERENCED_COLUMN_NAME'],
                "on_update": row['UPDATE_RULE'],
                "on_delete": row['DELETE_RULE']
            })
        return foreign_keys
    
    def _get_sample_data(self, conn, table_name: str, max_rows: int) -> List[Dict[str, Any]]:
        """Get sample data from a table"""
        cursor = conn.cursor(dictionary=True)
        try:
            cursor.execute(f"SELECT * FROM `{table_name}` LIMIT %s", (max_rows,))
            return cursor.fetchall()
        except mysql.connector.Error:
            # Return empty if we can't read data (e.g., no permissions)
            return []
    
    def execute(self, args: Dict[str, Any]) -> Dict[str, Any]:
        # Parameter validation
        connection_string = args.get("connection_string")
        if not connection_string:
            return {"error": "Connection string is required"}
        
        include_data = args.get("include_data", False)
        max_rows = args.get("max_rows", 5)
        
        try:
            # Parse connection string
            connection_params = self._parse_connection_string(connection_string)
            
            # Connect to database
            conn = self._get_connection(connection_params)
            
            result = {
                "database": connection_params['database'],
                "tables": []
            }
            
            # Get all tables
            tables = self._get_tables(conn)
            
            for table_name in tables:
                table_info = {
                    "name": table_name,
                    "columns": self._get_table_columns(conn, table_name),
                    "foreign_keys": self._get_foreign_keys(conn, table_name)
                }
                
                if include_data:
                    table_info["sample_data"] = self._get_sample_data(conn, table_name, max_rows)
                
                result["tables"].append(table_info)
            
            conn.close()
            return result
            
        except ValueError as e:
            return {"error": str(e)}
        except mysql.connector.Error as e:
            return {"error": f"Database error: {str(e)}"}
        except Exception as e:
            return {"error": f"Unexpected error: {str(e)}"}
