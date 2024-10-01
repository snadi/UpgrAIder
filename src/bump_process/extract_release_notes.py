#get pr url from json file, get the link for repo of the bumped library, check if github or bitbucket, if github, check releases link for release notes
# if release notes found, populate databse with entry for each change in release notes
import os
import argparse
from dotenv import load_dotenv
from utils.util import setup_logger, load_json_file,read_json_files_paths_from_folder
from utils.github_util import get_release_or_repo_url, get_url_data
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
                    #Process the url for release notes
                    link_data, content_type = get_url_data(url,GITHUB_TOKEN)
                    if content_type == "html":
                      print(f"Release Notes Data: {link_data}")
                      logger.info(f"Release Notes Data: {link_data}")
                    else:
                      print("Content type is not HTML")
                      logger.error("Content type is not HTML")
    except Exception as e:
        print(f"Error processing file: {json_file}")
        print(f"Error: {e}")
        logger.error(f"Error processing file: {json_file}")
        logger.error(f"Error: {e}")        
       
if __name__ == "__main__":
    main()