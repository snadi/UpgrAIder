import os
import logging as log

# from upgraider.fix_lib_examples import fix_lib_examples
from apiexploration.Library import Library, CodeSnippet
import json
import argparse
from upgraider.Model import Model
from upgraider.upgraide import Upgraider
import time
from upgraider.Report import (
    Report,
    SnippetReport,
    UpdateStatus,
    RunResult,
    FixStatus,
    DBSource,
    ModelResponse,
)
import json
from enum import Enum


def main():
    threshold = 0.5
    print("Starting experiment...")
    script_dir = os.path.dirname(__file__)

    parser = argparse.ArgumentParser(
        description="Run upgraider on all library examples"
    )
    parser.add_argument(
        "--outputDir", type=str, help="directory to write output to", required=True
    )
    parser.add_argument(
        "--model",
        type=str,
        help="Which model to use for fixing",
        default="gpt-3.5-turbo-0125",
        choices=["gpt-3.5-turbo-0125", "gpt-4"],
    )

    args = parser.parse_args()

    libraries_folder = os.path.join(script_dir, "../../libraries")
    output_dir = args.outputDir
    model = Model(args.model)
    upgraider = Upgraider(model)

    for lib_dir in os.listdir(libraries_folder):
        if lib_dir.startswith("."):
            continue
        lib_path = os.path.join(libraries_folder, lib_dir)
        with open(
            os.path.join(libraries_folder, f"{lib_dir}/library.json"), "r"
        ) as jsonfile:
            libinfo = json.loads(jsonfile.read())
            library = Library(
                name=libinfo["name"],
                ghurl=libinfo["ghurl"],
                baseversion=libinfo["baseversion"],
                currentversion=libinfo["currentversion"],
                path=lib_path,
            )

            print(f"Fixing examples for {library.name} with no references...")
            _fix_lib_examples(
                library=library,
                output_dir=os.path.join(output_dir, lib_dir, DBSource.modelonly.value),
                use_references=False,
                threshold=threshold,
                upgraider=upgraider,
            )

            print(f"Fixing examples for {library.name} with documentation...")
            _fix_lib_examples(
                library=library,
                output_dir=os.path.join(
                    output_dir, lib_dir, DBSource.documentation.value
                ),
                use_references=True,
                threshold=threshold,
                upgraider=upgraider,
            )


def _fix_lib_examples(
    library: Library,
    output_dir: str,
    use_references: bool,
    upgraider: Upgraider,
    threshold: float = None,
):
    print(
        f"=== Fixing examples for {library.name} with model {upgraider.model.model_name} ==="
    )

    report = Report(library)
    snippets = {}
    examples_path = os.path.join(library.path, "examples")

    if os.path.exists(examples_path):
        requirements_file = os.path.join(library.path, "requirements.txt")

        if not os.path.exists(requirements_file):
            requirements_file = None

        for example_file in os.listdir(examples_path):
            if example_file.startswith("."):
                continue

            model_response = upgraider.upgraide(
                code_snippet=CodeSnippet(
                    filename=example_file,
                    code=_load_example(os.path.join(examples_path, example_file)),
                ),
                library=library,
                use_references=use_references,
                threshold=threshold,
                output_dir=output_dir,
            )

            snippet_results = upgraider.validate_upgraide(model_response)

            _write_experiment_files(model_response, output_dir)

            # snippet_results = fix_example(
            #     library=library,
            #     example_file=example_file,
            #     examples_path=examples_path,
            #     requirements_file=requirements_file,
            #     output_dir=output_dir,
            #     use_references=use_references,
            #     model=model,
            #     threshold=threshold,
            # )

            print(f"Finished fixing {example_file}...")
            snippets[example_file] = snippet_results

            # wait 30 seconds between each example
            time.sleep(30)

    report.snippets = snippets
    report.num_snippets = len(snippets)
    report.db_source = (
        DBSource.modelonly.value
        if use_references is False
        else DBSource.documentation.value
    )
    report.num_fixed = len(
        [s for s in snippets.values() if s.fix_status == FixStatus.FIXED]
    )
    report.num_updated = len(
        [
            s
            for s in snippets.values()
            if s.model_response.update_status == UpdateStatus.UPDATE
        ]
    )
    report.num_updated_w_refs = len(
        [
            s
            for s in snippets.values()
            if s.model_response.update_status == UpdateStatus.UPDATE
            and s.model_response.references is not None
            and "No references used" not in s.model_response.references
        ]
    )
    report.num_apis = 0  # len(set([s.api for s in snippets.values()]))

    output_json_file = os.path.join(output_dir, "report.json")
    jsondata = report.to_json(indent=4)
    os.makedirs(os.path.dirname(output_json_file), exist_ok=True)
    with open(output_json_file, "w") as jsonfile:
        jsonfile.write(jsondata)


class ResultType(Enum):
    PROMPT = 1
    RESPONSE = 2


def _load_example(filepath: str) -> str:
    with open(filepath, "r", encoding="utf-8") as f:
        return f.read()


def _write_experiment_files(model_response: ModelResponse, output_dir: str):

    print("Writing prompt to file...")
    prompt_file = _write_result(
        model_response.prompt,
        ResultType.PROMPT,
        output_dir,
        model_response.original_code.filename,
    )

    print("Writing model response to file...")
    model_response_file = _write_result(
        model_response.raw_response,
        ResultType.RESPONSE,
        output_dir,
        model_response.original_code.filename,
    )


def _write_result(
    result: str, result_type: ResultType, output_dir: str, example_file: str
):
    result_file_root = os.path.splitext(example_file)[0]

    if result_type == ResultType.RESPONSE:
        result_file = os.path.join(
            output_dir, f"responses/{result_file_root}_response.txt"
        )
    elif result_type == ResultType.PROMPT:
        result_file = os.path.join(output_dir, f"prompts/{result_file_root}_prompt.txt")
    else:
        print(f"Invalid result type: {result_type}")
        return

    os.makedirs(os.path.dirname(result_file), exist_ok=True)
    if result is None:
        result = ""

    with open(result_file, "w") as f:
        f.write(result)
    return result_file


if __name__ == "__main__":
    main()
