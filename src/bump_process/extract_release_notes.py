#get pr url from json file, get the link for repo of the bumped library, check if github or bitbucket, if github, check releases link for release notes
# if release notes found, populate databse with entry for each change in release notes
import os
import argparse
from dotenv import load_dotenv
from utils.util import setup_logger, load_json_file,read_json_files_paths_from_folder
from utils.github_util import get_release_or_repo_url, get_url_data, process_release_notes_html
from bs4 import BeautifulSoup
import bs4
import re

# Load environment variables from .env file
load_dotenv()

# GitHub API token for authentication (optional)
GITHUB_TOKEN = os.getenv('GITHUB_TOKEN')


# Function to parse command-line arguments
def parse_arguments():
    parser = argparse.ArgumentParser(description='Process JSON files to extract release notes from library repository.')
    parser.add_argument('--json_folder_path', required=True, type=str, help='Folder path containing the JSON files.')
    parser.add_argument('--output_dir', required=True, type=str, help='Folder path for output folder.')

    return parser.parse_args()
  

def save_release_notes_to_file(library,release_notes_dict, output_dir):
   #check if output directory of library exists
    output_dir = os.path.join(output_dir, library)
    if not os.path.exists(output_dir):
        os.makedirs(output_dir)
    for version, release_notes in release_notes_dict.items():
        # Save the release notes to a file
        file_name = f"{library}_{version}_release_notes.txt"
        file_path = os.path.join(output_dir, file_name)

        with open(file_path, 'w') as file:
            file.write(release_notes)
        
        print(f"Release notes saved to: {file_path}")

def get_release_from_data(link_data,logger,output_dir,data):
    #Process the url for release notes
    print(f"Release Notes Data: {link_data}")
    logger.info(f"Release Notes Data: {link_data}")
    release_notes_dic=process_release_notes_html(link_data)
    if release_notes_dic:
        save_release_notes_to_file(data['updatedDependency']['dependencyGroupID'],release_notes_dic, output_dir)
    else:
        print("Release notes are not found.")
        logger.error("Release notes are not found.")

def check_more_pages(url, page):
    """
    Function to check if a new page exists.
    It sends a request to the next page URL and checks for its existence.
    Returns True if the page exists, False otherwise.
    """
    paginated_url = f"{url}?page={page}"
    print(f"Checking if page {page} exists: {paginated_url}")
    # Request the paginated URL (head request can be used to check if the page exists)
    link_data, content_type = get_url_data(paginated_url, GITHUB_TOKEN)
    # If the content type is HTML, assume the page exists
    if content_type == "html" and link_data:
        version=process_release_notes_html(link_data)
        if version:
            return True
        else:
            return False
# Main function
def main():
    args = parse_arguments()
    json_folder_path = args.json_folder_path
    output_dir = args.output_dir
    if not os.path.isdir(json_folder_path):
        raise FileNotFoundError(f"The directory {json_folder_path} does not exist.")
    if not os.path.exists(output_dir):
        os.makedirs(output_dir)

   #Get list of json files from folder
    json_files = read_json_files_paths_from_folder(json_folder_path)
    try:
        for json_file in json_files:
            # Load JSON data from the file
            data = load_json_file(json_file)
            # Get the PR URL from the JSON data
            pr_url = data.get('url')
            #setup logger
            logger = setup_logger(f"{os.path.basename(json_file)}_release_notes.log",output_dir)
            logger.info(f"Processing file {os.path.basename(json_file)}")
            print(f"Processing file {os.path.basename(json_file)}")

            #Get either release notes URL or repository URL form the PR URL
            link_type,url= get_release_or_repo_url(pr_url,GITHUB_TOKEN)
            if url:
                print(f"URL: {url}, link is for {link_type}")
                logger.info(f"URL: {url}, link is for {link_type}")
                if link_type == "Release Notes":
                    page = 1  # Start with page 1
                    has_more_pages = True  # Control the loop for paginated results
                    while has_more_pages:
                        # Append ?page=page_number to the URL for paginated results
                        paginated_url = f"{url}?page={page}"
                        print(f"Processing page {page} of Release Notes from {paginated_url}")
                        logger.info(f"Processing page {page} of Release Notes from {paginated_url}")
                        # Process the paginated URL for release notes
                        link_data, content_type = get_url_data(paginated_url, GITHUB_TOKEN)
                        if content_type == "html":
                            get_release_from_data(link_data,logger,output_dir,data)
                            print(f"Processed page {paginated_url} for Release Notes")
                            logger.info(f"Processed page {paginated_url} for Release Notes")
                            logger.info("---------------------------------------------")
                        else:
                            print("Content type is not HTML")
                            logger.error("Content type is not HTML")
                        page += 1
                        has_more_pages=check_more_pages(url,page)
                print(f"Processed {os.path.basename(json_file)} for release notes.")  
                logger.info(f"Processed {os.path.basename(json_file)} for release notes.")      

            #TODO: process the repository URL for releases      
    except Exception as e:
        print(f"Error processing file: {json_file}")
        print(f"Error: {e}")
        logger.error(f"Error processing file: {json_file}")
        logger.error(f"Error: {e}")        
       
if __name__ == "__main__":
    main()