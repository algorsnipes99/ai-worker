import sys
import os
from typing import Dict, Any, List
from functions.function import Function

# Add the Code-Repository-RAG project to path
_RAG_PATH = os.getenv(
    'CODE_REPOSITORY_RAG_PATH',
    r'C:\Users\BradleySass\Documents\personal_projects\Code-Repository-RAG'
)
if _RAG_PATH not in sys.path:
    sys.path.insert(0, _RAG_PATH)

# Lazily import the CodeRepositoryRAG class from the external RAG project.
# Using importlib to defer the import until first use, avoiding startup errors
# if the RAG project path is not yet configured.
# @returns: The CodeRepositoryRAG class.
def _load_rag_class():
    import importlib
    mod = importlib.import_module('main')
    return mod.CodeRepositoryRAG


class CodebaseQueryFunction(Function):
    """Allows agents to query one or more codebases using the RAG system"""

    # Initialize with a list of repository paths to index.
    # Builds the tool description dynamically from the repo names.
    # RAG instances are created lazily on first query per repo.
    # @param repo_paths: List of absolute paths to repositories to index and query.
    def __init__(self, repo_paths: List[str]):
        self.repo_paths = repo_paths
        # One RAG instance per repo, lazily initialized: {path: <CodeRepositoryRAG>}
        self._rags: Dict[str, Any] = {}

        repo_names = [os.path.basename(p.rstrip('/\\')) for p in repo_paths]
        super().__init__(
            name="codebaseQuery",
            description=(
                f"Find files, configs, and code in the registered repositories, or ask questions about how the code works. "
                f"Use this INSTEAD of find/dir/grep/cat when working with these repositories: {', '.join(repo_names)}. "
                f"Examples: 'What config files exist in mqx_api?', 'Where is authentication implemented?', 'Show me the database connection setup'."
            ),
            parameters={
                "question": {
                    "type": "string",
                    "description": "The question to ask about the codebases (e.g. 'How is authentication implemented?')"
                },
                "repo": {
                    "type": "string",
                    "optional": True,
                    "description": (
                        f"Optional: restrict the search to a specific repository name. "
                        f"Available: {', '.join(repo_names)}. Leave empty to search all."
                    )
                }
            }
        )

    # Return the RAG instance for the given repo path, building and indexing it on first access.
    # @param repo_path: Absolute path to the repository to initialize.
    # @returns: An initialized CodeRepositoryRAG instance ready to answer questions.
    def _get_rag(self, repo_path: str):
        if repo_path not in self._rags:
            print(f"Initializing RAG index for: {repo_path}")
            CodeRepositoryRAG = _load_rag_class()
            rag = CodeRepositoryRAG(granularity="chunk")
            rag.run_full_pipeline(repo_path)
            self._rags[repo_path] = rag
            print(f"RAG index ready for: {repo_path}")
        return self._rags[repo_path]

    # Query one or all indexed repositories and aggregate their answers and source references.
    # @param args: Dict with 'question' (required) and optional 'repo' filter (repo name string).
    # @returns: Dict with 'answer', 'sources', 'num_sources', 'question', 'repos_queried',
    #           'errors', 'status', or 'error' if all repos failed.
    def execute(self, args: Dict[str, Any]) -> Dict[str, Any]:
        question = args["question"]
        repo_filter = args.get("repo", "").strip().lower()

        # Determine which repos to query
        if repo_filter:
            targets = [
                p for p in self.repo_paths
                if os.path.basename(p.rstrip('/\\')).lower() == repo_filter
            ]
            if not targets:
                available = [os.path.basename(p.rstrip('/\\')) for p in self.repo_paths]
                return {
                    "error": f"No indexed repository named '{repo_filter}'. Available: {available}",
                    "status": "error"
                }
        else:
            targets = self.repo_paths

        print(f"Querying {len(targets)} repo(s) for: '{question}'")

        all_answers = []
        all_sources = []
        errors = []

        for repo_path in targets:
            repo_name = os.path.basename(repo_path.rstrip('/\\'))
            try:
                rag = self._get_rag(repo_path)
                result = rag.ask_question(question)

                if "error" in result:
                    errors.append(f"{repo_name}: {result['error']}")
                    continue

                all_answers.append(f"### {repo_name}\n{result.get('answer', '')}")
                all_sources.extend([
                    f"{repo_name}: {src}" for src in result.get("context_sources", [])
                ])
            except Exception as e:
                errors.append(f"{repo_name}: {str(e)}")

        if not all_answers and errors:
            return {"error": "; ".join(errors), "status": "error"}

        return {
            "answer": "\n\n".join(all_answers),
            "sources": all_sources,
            "num_sources": len(all_sources),
            "question": question,
            "repos_queried": [os.path.basename(p.rstrip('/\\')) for p in targets],
            "errors": errors if errors else None,
            "status": "success"
        }
