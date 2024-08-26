import os
import difflib
import ast
from collections import namedtuple
from enum import Enum
from upgraider.Model import ModelResponse, Model, parse_model_response
from apiexploration.Library import CodeSnippet, Library
from upgraider.promptCrafting import construct_fixing_prompt
from upgraider.run_code import run_code
from upgraider.Report import (
    SnippetReport,
    UpdateStatus,
    RunResult,
    FixStatus,
)


Import = namedtuple("Import", ["module", "name", "alias"])


class Upgraider:
    def __init__(self, model: Model):
        self.model = model

    def upgraide(
        self,
        code_snippet: CodeSnippet,
        library: Library,
        use_references: bool,
        threshold: float = 0.0,
        output_dir: str = None,
    ):

        prompt_text = construct_fixing_prompt(
            original_code=code_snippet.code,
            use_references=use_references,
            threshold=threshold,
        )

        model_response = self.model.query(prompt_text)

        parsed_model_response = parse_model_response(model_response, code_snippet)
        parsed_model_response.prompt = prompt_text
        parsed_model_response.library = library

        if parsed_model_response.update_status == UpdateStatus.UPDATE:
            parsed_model_response.updated_code = _fix_imports(
                old_code=parsed_model_response.original_code,
                updated_code=parsed_model_response.updated_code,
            )

        if output_dir is not None:
            updated_file_path = _write_updated_code(output_dir, parsed_model_response)
            parsed_model_response.updated_code.filename = updated_file_path

        return parsed_model_response

    def validate_upgraide(self, model_response: ModelResponse) -> SnippetReport:

        library = model_response.library
        examples_path = os.path.join(library.path, "examples")

        if os.path.exists(examples_path):
            requirements_file = os.path.join(library.path, "requirements.txt")

            if not os.path.exists(requirements_file):
                requirements_file = None

        example_file_path = os.path.join(
            examples_path, model_response.original_code.filename
        )

        original_code_result = run_code(library, example_file_path, requirements_file)

        updated_code_result = None  # will stay as None if no update occurs
        diff = None

        if model_response.update_status == UpdateStatus.UPDATE:
            updated_code = model_response.updated_code
            if updated_code is None:
                print(
                    f"WARNING: update occurred for {model_response.original_code.filename} but could not retrieve updated code"
                )
            else:
                updated_code_result = run_code(
                    library, model_response.updated_code.filename, requirements_file
                )
                diff = _unidiff(
                    model_response.original_code.code, model_response.updated_code.code
                )

        snippet_report = SnippetReport(
            model_response=model_response,
            original_run=original_code_result,
            modified_run=updated_code_result,
            fix_status=(
                _determine_fix_status(original_code_result, updated_code_result)
                if updated_code_result is not None
                else FixStatus.NOT_FIXED
            ),
            diff=diff,
        )

        return snippet_report


def _fix_imports(old_code: CodeSnippet, updated_code: CodeSnippet) -> CodeSnippet:
    """
    Given the old code and the updated code, this function will ensure that the updated code has all the imports from the old code.
    """
    old_imports = _get_imports(old_code.code)
    updated_imports = _get_imports(updated_code.code)

    if old_imports is None or updated_imports is None:
        print("WARNING: could not parse imports for either old or updated code")
        return updated_code

    if updated_code.code is None or updated_code.code == "":
        return updated_code

    # if there is an old import that is not in the updated code, add it
    for old_import in old_imports:
        if old_import not in updated_imports:
            updated_code.code = f"{_format_import(old_import)}\n{updated_code.code}"

    return updated_code


# GaretJax, https://stackoverflow.com/questions/9008451/python-easy-way-to-read-all-import-statements-from-py-module
def _get_imports(code: str) -> list[Import]:
    try:
        ast_root = ast.parse(code)

        for node in ast.iter_child_nodes(ast_root):
            if isinstance(node, ast.Import):
                module = []
            elif isinstance(node, ast.ImportFrom):
                module = node.module.split(".")
            else:
                continue

            for n in node.names:
                yield Import(module, n.name.split("."), n.asname)
    except:
        return None


def _format_import(import_stmt: Import) -> str:
    if import_stmt.module:
        if import_stmt.alias is not None:
            return f"from {'.'.join(import_stmt.module)} import {'.'.join(import_stmt.name)} as {import_stmt.alias}"
        else:
            return f"from {'.'.join(import_stmt.module)} import {'.'.join(import_stmt.name)}"
    else:
        if import_stmt.alias is not None:
            return f"import {'.'.join(import_stmt.name)} as {import_stmt.alias}"
        else:
            return f"import {'.'.join(import_stmt.name)}"


# https://stackoverflow.com/questions/845276/how-to-print-the-comparison-of-two-multiline-strings-in-unified-diff-format
# https://stackoverflow.com/posts/845432/, Andrea Francia
def _unidiff(old, new):
    """
    Helper function. Returns a string containing the unified diff of two multiline strings.
    """

    old = old.splitlines(1)

    if new is not None:
        new = new.splitlines(1)
    else:
        new = ""

    diff = difflib.unified_diff(old, new)

    return "".join(diff)


def _determine_fix_status(
    original_code_result: RunResult, final_code_result: RunResult
) -> FixStatus:
    # original status is always an error or warning
    if final_code_result.problem_free is True:
        return FixStatus.FIXED

    if original_code_result.problem != final_code_result.problem:
        return FixStatus.NEW_ERROR

    return FixStatus.NOT_FIXED


def _write_updated_code(output_dir: str, model_response: ModelResponse):
    print("Writing updated code... ")
    file_path = os.path.join(
        output_dir,
        f"updated/{model_response.original_code.filename}_updated.py",
    )
    os.makedirs(os.path.dirname(file_path), exist_ok=True)
    _write_file(file_path, model_response.updated_code.code)
    return file_path


def _write_file(path, content):
    if content is None:
        content = ""

    with open(path, mode="w", encoding="utf-8") as f:
        f.write(content)
    return path
