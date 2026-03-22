import os
import shutil
import json
import tempfile
from typing import Dict, Any, Optional
from functions.function import Function
from datetime import datetime


class FileEditFunction(Function):
    """Edits content of a file"""

    # Register the editFile tool with its full parameter schema.
    def __init__(self):
        super().__init__(
            name="editFile",
            description="Edits content of a file at the specified path",
            parameters={
                "path": {
                    "type": "string",
                    "description": "Path to the file to edit"
                },
                "content": {
                    "type": "string",
                    "description": "New content to write"
                },
                "mode": {
                    "type": "string",
                    "enum": ["overwrite", "append", "insert"],
                    "default": "overwrite",
                    "description": "Edit mode: overwrite, append, or insert"
                },
                "line": {
                    "type": "integer",
                    "description": "Line number for insert mode (1-based)"
                },
                "create": {
                    "type": "boolean",
                    "default": True,
                    "description": "Create file if it doesn't exist"
                },
                "backup": {
                    "type": "boolean",
                    "default": True,
                    "description": "Create backup before editing (for existing files)"
                },
                "cleanup_backups": {
                    "type": "boolean",
                    "default": False,
                    "description": "Delete the backup created for this edit after success"
                },
                "retain_backups": {
                    "type": "boolean",
                    "default": True,
                    "description": "If True, keep backups and apply retention policy (if configured)"
                },
                "backup_retention": {
                    "type": "integer",
                    "default": 20,
                    "description": "Keep last N backups per file when retain_backups=True"
                },
                "format_json": {
                    "type": "boolean",
                    "default": True,
                    "description": "If path ends with .json, validate and pretty-print JSON content"
                },
                "auto_format_json_nonjson_files": {
                    "type": "boolean",
                    "default": False,
                    "description": "If True, pretty-print JSON even when file extension is not .json"
                },
                "ensure_newline_separation": {
                    "type": "boolean",
                    "default": True,
                    "description": "For append mode, ensure appended content starts on a new line"
                },
                "ensure_trailing_newline": {
                    "type": "boolean",
                    "default": False,
                    "description": "Ensure the final file ends with a newline (useful for text files)"
                }
            }
        )

    # Try to parse the given string as JSON.
    # @param content: String to parse.
    # @returns: Parsed object, or None if not valid JSON.
    def _try_parse_json(self, content: str) -> Optional[Dict[str, Any]]:
        try:
            return json.loads(content)
        except ValueError:
            return None

    # Write text to a file atomically: write to a temp file in the same directory,
    # then os.replace() to swap it in. Cleans up the temp file on failure.
    # @param path: Destination file path.
    # @param content: Text content to write (UTF-8, Unix line endings).
    def _atomic_write_text(self, path: str, content: str) -> None:
        directory = os.path.dirname(path) or "."
        os.makedirs(directory, exist_ok=True)

        fd, tmp_path = tempfile.mkstemp(prefix=".tmp_edit_", dir=directory, text=True)
        try:
            with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as f:
                f.write(content)
            os.replace(tmp_path, path)  # atomic on most platforms for same filesystem
        except Exception:
            # best-effort cleanup
            try:
                if os.path.exists(tmp_path):
                    os.remove(tmp_path)
            except Exception:
                pass
            raise

    # Validate parameters, optionally format JSON content, create or modify the file,
    # manage backups, and return a result dict. Rolls back from backup on failure.
    # @param args: Dict containing path, content, mode, and all optional flags.
    # @returns: Dict with 'status' and 'path', plus optional backup/rollback info, or 'error'.
    def execute(self, args: Dict[str, Any]) -> Dict[str, Any]:
        # Parameter validation
        path = args.get("path")
        if not path or not isinstance(path, str):
            return {"error": "Invalid path parameter"}

        content = args.get("content")
        if not isinstance(content, str):
            return {"error": "Content must be a string"}

        mode = args.get("mode", "overwrite")
        line = args.get("line")
        create = args.get("create", True)
        backup = args.get("backup", True)
        cleanup_backups = args.get("cleanup_backups", False)
        retain_backups = args.get("retain_backups", True)
        backup_retention = args.get("backup_retention", 20)

        format_json = args.get("format_json", True)
        auto_format_json_nonjson_files = args.get("auto_format_json_nonjson_files", False)

        ensure_newline_separation = args.get("ensure_newline_separation", True)
        ensure_trailing_newline = args.get("ensure_trailing_newline", False)

        print(f"Editing file: {path}")

        # Validate mode early
        if mode not in {"overwrite", "append", "insert"}:
            return {"error": f"Invalid mode: {mode}"}

        # Insert requires line
        if mode == "insert" and (line is None or not isinstance(line, int)):
            return {"error": "Insert mode requires an integer 'line' parameter (1-based)."}

        # JSON handling
        try:
            is_json_path = path.lower().endswith(".json")
            parsed = self._try_parse_json(content)

            if is_json_path and format_json:
                if parsed is None:
                    return {"error": "Invalid JSON content for .json file", "original_content": content}
                content = json.dumps(parsed, indent=2, ensure_ascii=False) + "\n"
            elif (not is_json_path) and auto_format_json_nonjson_files and parsed is not None:
                content = json.dumps(parsed, indent=2, ensure_ascii=False)
        except Exception as e:
            return {"error": f"JSON processing failed: {str(e)}"}

        # Optionally ensure trailing newline in the *content* (for overwrite scenarios)
        if ensure_trailing_newline and mode == "overwrite" and content and not content.endswith("\n"):
            content += "\n"

        backup_path = None
        existed = os.path.exists(path)

        # Create file if missing
        if not existed:
            if not create:
                return {"error": f"File not found and create=False: {path}"}
            try:
                return self._create_file(path, content)
            except Exception as e:
                return {"error": f"Failed to create file: {str(e)}"}

        # Existing file: create backup for any mutating mode
        try:
            if backup:
                backup_path = self._create_backup(path)

            if mode == "overwrite":
                result = self._overwrite_file(path, content)
            elif mode == "append":
                result = self._append_file(
                    path,
                    content,
                    ensure_newline_separation=ensure_newline_separation,
                    ensure_trailing_newline=ensure_trailing_newline
                )
            else:  # insert
                result = self._insert_file(
                    path,
                    content,
                    line=line,
                    ensure_trailing_newline=ensure_trailing_newline
                )

            # Backup retention / cleanup
            if backup_path:
                result["backup_path"] = backup_path

                # Delete the backup created for *this* edit after success (if requested)
                if cleanup_backups:
                    try:
                        if os.path.exists(backup_path):
                            os.remove(backup_path)
                        result["backup_cleaned"] = True
                    except Exception as e:
                        result["backup_clean_error"] = str(e)
                else:
                    # Keep backups, optionally trim older ones
                    if retain_backups and isinstance(backup_retention, int) and backup_retention > 0:
                        self._enforce_backup_retention(path, backup_retention)

            return result

        except Exception as e:
            # Best-effort rollback if we have a backup and something failed after making it
            if backup_path and os.path.exists(backup_path):
                try:
                    shutil.copy2(backup_path, path)
                    return {
                        "error": str(e),
                        "rolled_back": True,
                        "backup_path": backup_path
                    }
                except Exception as rb_e:
                    return {
                        "error": str(e),
                        "rolled_back": False,
                        "rollback_error": str(rb_e),
                        "backup_path": backup_path
                    }
            return {"error": str(e)}

    # Create the file and any missing parent directories, then write content atomically.
    # @param path: File path to create.
    # @param content: Text content to write.
    # @returns: Dict with 'status': 'created' and 'path'.
    def _create_file(self, path: str, content: str) -> Dict[str, Any]:
        dirname = os.path.dirname(path)
        if dirname:
            os.makedirs(dirname, exist_ok=True)
        # atomic create/write
        self._atomic_write_text(path, content)
        return {"status": "created", "path": path}

    # Overwrite the file content atomically.
    # @param path: File path to overwrite.
    # @param content: New text content.
    # @returns: Dict with 'status': 'overwritten' and 'path'.
    def _overwrite_file(self, path: str, content: str) -> Dict[str, Any]:
        self._atomic_write_text(path, content)
        return {"status": "overwritten", "path": path}

    # Append content to the file, optionally ensuring a newline separator and trailing newline.
    # @param path: File path to append to.
    # @param content: Text to append.
    # @param ensure_newline_separation: Prepend a newline if file doesn't end with one.
    # @param ensure_trailing_newline: Ensure the file ends with a newline after appending.
    # @returns: Dict with 'status': 'appended' and 'path'.
    def _append_file(
        self,
        path: str,
        content: str,
        ensure_newline_separation: bool = True,
        ensure_trailing_newline: bool = False
    ) -> Dict[str, Any]:
        # Ensure appended content starts on a new line (if file doesn't end with one)
        if ensure_newline_separation:
            needs_newline = False
            try:
                with open(path, "rb") as f:
                    if f.seek(0, os.SEEK_END) != 0:
                        f.seek(-1, os.SEEK_END)
                        last = f.read(1)
                        needs_newline = last not in (b"\n", b"\r")
            except OSError:
                # if we can't read, just skip this nicety
                needs_newline = False

            if needs_newline and content and not content.startswith("\n"):
                content = "\n" + content

        if ensure_trailing_newline and content and not content.endswith("\n"):
            content += "\n"

        with open(path, "a", encoding="utf-8", newline="\n") as f:
            f.write(content)

        if ensure_trailing_newline:
            # Ensure final file ends with newline (content may have been empty)
            with open(path, "rb+") as f:
                f.seek(0, os.SEEK_END)
                if f.tell() > 0:
                    f.seek(-1, os.SEEK_END)
                    if f.read(1) not in (b"\n", b"\r"):
                        f.write(b"\n")

        return {"status": "appended", "path": path}

    # Insert content at the given 1-based line number, shifting existing lines down.
    # Writes the resulting file atomically.
    # @param path: File path to insert into.
    # @param content: Text to insert (may be multi-line).
    # @param line: 1-based line number at which to insert.
    # @param ensure_trailing_newline: Ensure the final file ends with a newline.
    # @returns: Dict with 'status': 'inserted', 'path', and 'line', or 'error' for invalid line.
    def _insert_file(
        self,
        path: str,
        content: str,
        line: int,
        ensure_trailing_newline: bool = False
    ) -> Dict[str, Any]:
        with open(path, "r", encoding="utf-8") as f:
            lines = f.readlines()

        if line < 1 or line > len(lines) + 1:
            return {"error": f"Invalid line number: {line}. File has {len(lines)} lines."}

        # Insert multi-line content properly
        insert_lines = content.splitlines(True)
        if content and not insert_lines:
            insert_lines = [content]

        # If content doesn't end with newline, preserve typical line structure by adding one
        if insert_lines and not insert_lines[-1].endswith(("\n", "\r")):
            insert_lines[-1] += "\n"

        new_lines = lines[: line - 1] + insert_lines + lines[line - 1 :]

        # Atomic write the whole updated file
        new_content = "".join(new_lines)

        if ensure_trailing_newline and new_content and not new_content.endswith("\n"):
            new_content += "\n"

        self._atomic_write_text(path, new_content)

        return {"status": "inserted", "path": path, "line": line}

    # Copy the file to a timestamped backup in a 'backups/' subdirectory beside it.
    # @param path: File path to back up.
    # @returns: The backup file path string.
    def _create_backup(self, path: str) -> str:
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        backup_dir = os.path.join(os.path.dirname(path) or ".", "backups")
        os.makedirs(backup_dir, exist_ok=True)
        filename = os.path.basename(path)
        backup_path = os.path.join(backup_dir, f"{filename}.bak_{timestamp}")
        shutil.copy2(path, backup_path)
        return backup_path

    # Delete old backups for this file, keeping only the most recent keep_last entries.
    # Backups are identified by the '{filename}.bak_YYYYMMDD_HHMMSS' naming pattern.
    # @param path: Original file path (used to locate and name-match backups).
    # @param keep_last: Maximum number of backups to retain.
    def _enforce_backup_retention(self, path: str, keep_last: int) -> None:
        backup_dir = os.path.join(os.path.dirname(path) or ".", "backups")
        if not os.path.isdir(backup_dir):
            return

        filename = os.path.basename(path)
        prefix = f"{filename}.bak_"

        backups = [
            os.path.join(backup_dir, f)
            for f in os.listdir(backup_dir)
            if f.startswith(prefix)
        ]
        if len(backups) <= keep_last:
            return

        # Sort by filename timestamp suffix (YYYYMMDD_HHMMSS) descending
        backups.sort(key=lambda p: os.path.basename(p), reverse=True)
        to_delete = backups[keep_last:]

        for bp in to_delete:
            try:
                os.remove(bp)
            except Exception:
                pass
