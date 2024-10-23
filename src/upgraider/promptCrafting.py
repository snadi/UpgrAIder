import numpy as np
import openai
import os
from string import Template
import tiktoken
from upgraider.Database import (
    get_embedded_doc_sections,
    DeprecationComment,
    get_section_content,
)
from os import environ as env
from dotenv import load_dotenv
from apiexploration.Library import Library
from bump_process.process_release_db import get_library_release_notes
from utils.util import format_release_notes
import re

load_dotenv(override=True)

EMBEDDING_MODEL = "text-embedding-ada-002"

# TODO: use token length
MAX_SECTION_LEN = 500
SEPARATOR = "\n* "

ENCODING = "cl100k_base"  # encoding for text-embedding-ada-002

encoding = tiktoken.get_encoding(ENCODING)
separator_len = len(encoding.encode(SEPARATOR))


def construct_fixing_prompt(
    original_code: str,
    use_references: bool,
    threshold: float = None,
    use_embeddings: bool = False,
    db_name: str = None,
    library: Library = None,
    error_file: str = None,
    error_str: str = None,
):

    if use_references is True:
        if use_embeddings is True:
            references = get_reference_list(
                original_code=original_code, threshold=threshold
        )
        else:
            #extract version number from '8.1.11.v20130520' to be 8.1.11 use regex to remove the .v part
            #check if the version has the .v part in string 
            if ".v" in library.currentversion:
                library.currentversion = re.sub(r"\.v.*", "", library.currentversion)
            if ".v" in library.baseversion:
             library.baseversion = re.sub(r"\.v.*", "", library.baseversion)      
            references = get_library_release_notes(db_name,library.name,library.currentversion,library.baseversion)  
            references= format_release_notes(references) 
            #convert refrences to string
            # references_str = [f"\n{str(i+1)}. {ref['version']}: {ref['details']}" for i, ref in enumerate(references)]
    else:
        references = []

    script_dir = os.path.dirname(__file__)
    if use_embeddings:
        template_path=os.path.join(script_dir,"resources/chat_template.txt")
    elif not use_references:   
        template_path=os.path.join(script_dir,"resources/bump_chat_template_no_ref.txt") 
    else:
        template_path=os.path.join(script_dir,"resources/bump_chat_template.txt")
    with open(
       template_path, "r", encoding="utf-8"
    ) as file:
        chat_template = Template(file.read())
        if use_embeddings:
            prompt_text = chat_template.substitute(
                original_code=original_code, references="".join(references)
            )
        elif not use_references:
              prompt_text = chat_template.substitute(
                library_name=library.name,
                base_version= library.baseversion,
                new_version=library.currentversion,
                file_name=error_file,
                error=error_str,
                original_code=original_code,
            )       
        else:
            if len(references) == 0:
                references = "No references provided"
            prompt_text = chat_template.substitute(
                library_name=library.name,
                base_version= library.baseversion,
                new_version=library.currentversion,
                file_name=error_file,
                error=error_str,
                original_code=original_code,
                references=references
            )    
              
    return prompt_text


def order_document_sections_by_code_similarity(
    code: str, contexts: dict[(int, int), np.array], threshold: float = None
) -> list[(float, (int, int))]:
    """
    Find the embedding for the supplied code snippet, and compare it against all of the pre-calculated document embeddings
    to find the most relevant documentation sections.

    Return the list of document sections, sorted by relevance in descending order.
    """
    code_embedding = get_embedding(code)

    if code_embedding is None:
        return []

    document_similarities = sorted(
        [
            (vector_similarity(code_embedding, doc_embedding), doc_index)
            for doc_index, doc_embedding in contexts.items()
        ],
        reverse=True,
    )

    if threshold:
        document_similarities = [
            sim for sim in document_similarities if sim[0] > threshold
        ]

    return document_similarities


def get_reference_list(
    original_code: str,
    threshold: float = 0.0,
):
    chosen_sections = []
    chosen_sections_len = 0
    ref_count = 0

    context_embeddings = get_embedded_doc_sections()

    most_relevant_document_sections = order_document_sections_by_code_similarity(
        original_code, context_embeddings, threshold
    )

    for similarity, section_index in most_relevant_document_sections:

        if chosen_sections_len > MAX_SECTION_LEN:
            break

        # Add sections as context, until we run out of space.
        section_content = get_section_content(section_index)
        # section for section in sections if section.id == section_index

        section_tokens = section_content.split(" ")

        if len(section_tokens) < 3:
            continue  # skip one or two word references

        len_if_added = chosen_sections_len + len(section_tokens) + separator_len

        # if current section will exceed max length, truncate it
        if len_if_added > MAX_SECTION_LEN:
            section_content = " ".join(
                section_tokens[: MAX_SECTION_LEN - chosen_sections_len]
            )

        chosen_sections_len = len_if_added
        ref_count += 1

        chosen_sections.append(
            "\n" + str(ref_count) + ". " + section_content.replace("\n", " ")
        )

    return chosen_sections


def get_embedding(text: str, model: str = EMBEDDING_MODEL) -> list[float]:
    """
    Returns the embedding for the supplied text.
    """
    openai.api_key = env["OPENAI_API_KEY"]

    try:
        result = openai.Embedding.create(model=model, input=text)
    except openai.error.InvalidRequestError as e:
        print(f"ERROR: {e}")
        return None

    return result["data"][0]["embedding"]


def vector_similarity(x: list[float], y: list[float]) -> float:
    """
    Returns the similarity between two vectors.

    Because OpenAI Embeddings are normalized to length 1, the cosine similarity is the same as the dot product.
    """
    if x is None or y is None:
        return 0.0
    return np.dot(np.array(x), np.array(y))
