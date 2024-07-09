import os
import json
import argparse
import time
from enum import Enum
from apiexploration.Library import Library, CodeSnippet
from upgraider.Model import Model
from upgraider.upgraide import Upgraider
from upgraider.Report import (
    Report,
    UpdateStatus,
    FixStatus,
    DBSource,
    ModelResponse,
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

            prompt_file_path, model_response_file_path = _write_experiment_files(
                model_response, output_dir
            )
            snippet_results.prompt_file = prompt_file_path
            snippet_results.model_reponse_file = model_response_file_path

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
    with open(output_json_file, mode="w", encoding="utf-8") as jsonfile:
        jsonfile.write(jsondata)


class ResultType(Enum):
    PROMPT = 1
    RESPONSE = 2


def _load_example(filepath: str) -> str:
    with open(filepath, "r", encoding="utf-8") as f:
        return f.read()


def _write_experiment_files(model_response: ModelResponse, output_dir: str):

    print("Writing prompt to file...")
    prompt_file_path = _write_result(
        model_response.prompt,
        ResultType.PROMPT,
        output_dir,
        model_response.original_code.filename,
    )

    print("Writing model response to file...")
    model_response_file_path = _write_result(
        model_response.raw_response,
        ResultType.RESPONSE,
        output_dir,
        model_response.original_code.filename,
    )

    return prompt_file_path, model_response_file_path


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

    with open(result_file, mode="w", encoding="utf-8") as f:
        f.write(result)
    return result_file


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
        "--threshold",
        type=float,
        help="Similarity Threshold for retrieval",
        default=0.0,
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

    model = Model(args.model)
    upgraider = Upgraider(model)

    with open(
        os.path.join(args.libpath, "library.json"), mode="r", encoding="utf-8"
    ) as jsonfile:
        libinfo = json.loads(jsonfile.read())
        library = Library(
            name=libinfo["name"],
            ghurl=libinfo["ghurl"],
            baseversion=libinfo["baseversion"],
            currentversion=libinfo["currentversion"],
            path=args.libpath,
        )

    output_dir = args.outputDir

    print(f"Fixing examples for {library.name} with no references...")
    _fix_lib_examples(
        library=library,
        output_dir=os.path.join(output_dir, library.name, DBSource.modelonly.value),
        use_references=False,
        threshold=args.threshold,
        upgraider=upgraider,
    )

    print(f"Fixing examples for {library.name} with documentation...")
    _fix_lib_examples(
        library=library,
        output_dir=os.path.join(output_dir, library.name, DBSource.documentation.value),
        use_references=True,
        threshold=args.threshold,
        upgraider=upgraider,
    )
