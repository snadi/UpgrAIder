# some code in this script is based off https://github.com/openai/openai-cookbook/blob/main/examples/Question_answering_using_embeddings.ipynb
import openai
from os import environ as env
from dotenv import load_dotenv
from string import Template
import re
from upgraider.Database import get_embedded_doc_sections
from upgraider.Report import UpdateStatus, ModelResponse, CodeSnippet
import requests
import json
from upgraider.promptCrafting import construct_fixing_prompt

load_dotenv(override=True)

LLM_API_PARAMS = {
    "temperature": 0.0,
}


class Model:
    def __init__(self, model_name: str):
        self.model_name = model_name
        # self.api_endpoint = env["OPENAI_API_ENDPOINT"]
        # self.auth_headers = env["OPENAI_AUTH_HEADERS"]
        self.api_key = env["OPENAI_API_KEY"]

    def query(self, query: str) -> str:
        prompt = [
            {
                "role": "system",
                "content": "You are a smart code reviewer who can spot code that uses a non-existent or deprecated API.",
            },
            {"role": "user", "content": query},
        ]

        openai.api_key = self.api_key

        response = openai.ChatCompletion.create(
            messages=prompt, model=self.model_name, **LLM_API_PARAMS
        )

        result = response["choices"][0]["message"]["content"]

        return result


# Helper functions to process model response


def get_update_status(update_status: str) -> UpdateStatus:
    if update_status == "Update":
        return UpdateStatus.UPDATE
    elif update_status == "No update":
        return UpdateStatus.NO_UPDATE
    else:
        print(f"WARNING: unknown update status {update_status}")
        return UpdateStatus.UNKNOWN


def strip_markdown_keywords(code: str) -> str:
    """
    The model sometimes adds a python keyword to the beginning of the code snippet.
    This function removes that keyword.
    """
    if code.startswith("python") or code.startswith("markdown"):
        return "\n".join(code.splitlines()[1:])
    else:
        return code


def find_reason_in_response(model_response: str) -> str:

    reason = None

    prefixes = ["Reason for update:"]
    # try first the case where the model respects the enumeration
    reason_matches = re.search(r"^2\.(.*)", model_response, re.MULTILINE)
    reason = reason_matches.group(1).strip() if reason_matches else None

    if reason is not None:
        # check if reason starts with any of the prefixes and strip out the prefix
        for prefix in prefixes:
            if prefix in reason:
                reason = reason[len(prefix) :].strip()
                break
    else:
        # did not have enumeration so let's try to search in the response
        for prefix in prefixes:
            reason_matches = re.search(
                r"^.*" + prefix + r"(.*)", model_response, re.MULTILINE
            )
            if reason_matches:
                matched_value = reason_matches.group(1).strip()
                # if the group is empty, then it just matched the prefix
                # then it still didn't capture the reasons (could be list)
                if matched_value != "":
                    reason = matched_value
                    break

            multi_reason_matches = re.search(
                r"^.*" + prefix + "\n*(?P<reasons>(-(.*)\n)+)",
                model_response,
                re.MULTILINE,
            )
            if multi_reason_matches:
                reason = multi_reason_matches.group("reasons").strip()
                if len(reason.splitlines()) == 1 and reason.startswith("-"):
                    # if it's a single reason, remove the - since it's not
                    # really a list
                    reason = reason[1:].strip()
                break

    if reason == "None":
        reason = None

    return reason


def find_references_in_response(model_response: str) -> str:
    references = None
    reference_keywords = [
        "Reference used:",
        "Reference number:",
        "References used:",
        "Reference numbers used:",
        "List of reference numbers used:",
    ]
    reference_matches = re.search(r"^3\.(.*)\n", model_response, re.MULTILINE)
    references = reference_matches.group(1).strip() if reference_matches else None

    # response did not follow enumerated format
    if references == None:
        for keyword in reference_keywords:
            if keyword in model_response:
                references = model_response.split(keyword)[1].strip()

                if references.strip(".") == "No references used":
                    references = None

                break

    return references


def _is_no_update(model_response: str) -> bool:
    no_update_keywords = ["No update", "does not need to be updated"]

    if any(keyword in model_response for keyword in no_update_keywords):
        return True

    if model_response == "No references used":
        return True

    return False


def _find_updated_code_snippet(model_response: str) -> str:
    # match the updated code by looking for the fenced code block, even without the correct enumeration

    code_snippets = re.findall(r"\s*(```)\s*([\s\S]*?)(```|$)", model_response)

    updated_code = None

    if len(code_snippets) == 0:
        return updated_code
    elif len(code_snippets) == 1:
        updated_code = strip_markdown_keywords(code_snippets[0][1].strip())
    else:
        selected_snippet = code_snippets[0][1].strip()
        for snippet in code_snippets:
            code = snippet[1].strip()
            if code.startswith("python"):
                selected_snippet = code
            else:
                if len(code.splitlines()) > len(selected_snippet.splitlines()):
                    selected_snippet = code
                    break
        updated_code = strip_markdown_keywords(selected_snippet.strip())
    return updated_code


def parse_model_response(
    model_response: str, original_code: CodeSnippet
) -> ModelResponse:

    updated_code = _find_updated_code_snippet(model_response)

    if updated_code is not None and updated_code.strip() != "":
        if ("No changes needed" in updated_code) or (
            updated_code.strip() == original_code.code.strip()
        ):
            update_status = UpdateStatus.NO_UPDATE
        else:
            update_status = UpdateStatus.UPDATE
    else:
        if _is_no_update(model_response):
            update_status = UpdateStatus.NO_UPDATE
        else:
            update_status = UpdateStatus.NO_RESPONSE

    reason = find_reason_in_response(model_response)
    references = find_references_in_response(model_response)

    response = ModelResponse(
        raw_response=model_response,
        original_code=original_code,
        update_status=update_status,
        references=references,
        updated_code=CodeSnippet(code=updated_code),
        reason=reason,
    )

    return response
