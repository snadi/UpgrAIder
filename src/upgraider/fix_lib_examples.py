import argparse
from upgraider.Report import (
    Report,
    SnippetReport,
    UpdateStatus,
    RunResult,
    FixStatus,
    DBSource,
)
from upgraider.run_code import run_code
from upgraider.Model import Model, parse_model_response
from upgraider.promptCrafting import construct_fixing_prompt
import os
import json
import difflib
from apiexploration.Library import Library
from enum import Enum
import ast
from collections import namedtuple, defaultdict
import time


def fix_example(
    library: Library,
    example_file: str,
    examples_path: str,
    requirements_file: str,
    output_dir: str,
    use_references: bool,
    model: Model,
    threshold: float = None,
):

    example_file_path = os.path.join(examples_path, example_file)

    print(f"Fixing {example_file_path}...")
    with open(example_file_path, "r") as f:
        original_code = f.read()

    original_code_result = run_code(library, example_file_path, requirements_file)

    prompt_text = construct_fixing_prompt(
        original_code=original_code, use_references=use_references, threshold=threshold
    )

    print("Writing prompt to file...")
    prompt_file = _write_result(
        prompt_text, ResultType.PROMPT, output_dir, example_file
    )

    model_response = model.query(prompt_text)

    print("Writing model response to file...")
    model_response_file = _write_result(
        model_response, ResultType.RESPONSE, output_dir, example_file
    )

    parsed_model_response = parse_model_response(model_response)

    final_code_result = None  # will stay as None if no update occurs
    updated_code_file = None
    diff = None
    updated_code = None
    example_file_root = os.path.splitext(example_file)[0]

    if parsed_model_response.update_status == UpdateStatus.UPDATE:
        updated_code = parsed_model_response.updated_code
        if updated_code is None:
            print(
                f"WARNING: update occurred for {example_file} but could not retrieve updated code"
            )
        else:
            updated_code = _fix_imports(
                old_code=original_code, updated_code=updated_code
            )
            updated_code_file = os.path.join(
                output_dir, f"updated/{example_file_root}_updated.py"
            )
            os.makedirs(os.path.dirname(updated_code_file), exist_ok=True)
            with open(updated_code_file, "w") as f:
                f.write(updated_code)

            final_code_result = run_code(library, updated_code_file, requirements_file)
            diff = _unidiff(original_code, updated_code)

    snippet_results = SnippetReport(
        original_file=example_file,
        api=example_file_root,  # for now, file name is in format <api>.py
        prompt_file=prompt_file,
        # num_references=len(parsed_model_response.references),
        modified_file=updated_code_file,
        original_run=original_code_result,
        model_response=parsed_model_response,
        model_reponse_file=model_response_file,
        modified_run=final_code_result,
        fix_status=(
            _determine_fix_status(original_code_result, final_code_result)
            if final_code_result is not None
            else FixStatus.NOT_FIXED
        ),
        diff=diff,
    )

    return snippet_results


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Fix example(s) for a given library")
    parser.add_argument(
        "--libpath",
        type=str,
        help="absolute path of target library folder",
        required=True,
    )
    parser.add_argument(
        "--outputDir",
        type=str,
        help="absolute path of directory to write output to",
        required=True,
    )
    parser.add_argument(
        "--useref",
        type=bool,
        help="Whether to use references from documentation (i.e., augmented prompt with release notes)",
        default=True,
        action=argparse.BooleanOptionalAction,
    )
    parser.add_argument(
        "--threshold", type=float, help="Similarity Threshold for retrieval"
    )
    parser.add_argument(
        "--examplefile",
        type=str,
        help="Specific example file to run on (optional). Only name of example file needed.",
        required=False,
    )
    parser.add_argument(
        "--model",
        type=str,
        help="Which model to use for fixing",
        default="gpt-3.5-turbo-0125",
        choices=["gpt-3.5-turbo-0125", "gpt-4"],
    )

    args = parser.parse_args()
    script_dir = os.path.dirname(__file__)

    with open(os.path.join(args.libpath, "library.json"), "r") as jsonfile:
        libinfo = json.loads(jsonfile.read())
        library = Library(
            name=libinfo["name"],
            ghurl=libinfo["ghurl"],
            baseversion=libinfo["baseversion"],
            currentversion=libinfo["currentversion"],
            path=args.libpath,
        )
        output_dir = os.path.join(script_dir, args.outputDir)

        if args.examplefile is not None:
            # fix a specific example
            fix_example(
                library=library,
                example_file=args.examplefile,
                examples_path=os.path.join(library.path, "examples"),
                requirements_file=os.path.join(library.path, "requirements.txt"),
                output_dir=output_dir,
                use_references=args.useref,
                model=args.model,
                threshold=args.threshold,
            )
        else:
            # fix all examples for this library
            fix_lib_examples(
                library=library,
                output_dir=output_dir,
                model=args.model,
                use_references=args.useref,
                threshold=args.threshold,
            )
