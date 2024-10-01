#Get the url from the json file for the commit, reterive the PR from github and check if it contains release notes for the version update
import json
import requests
import pandas as pd
import argparse
from dotenv import load_dotenv
import os
from bs4 import BeautifulSoup
import logging
from utils.util import setup_logger,load_json_file
from utils.github_util import get_url_data,extract_release_notes_from_html
## Load environment variables from .env file
load_dotenv()


# GitHub API token for authentication (optional)
GITHUB_TOKEN = os.getenv('GITHUB_TOKEN')


def parse_arguments():
    parser = argparse.ArgumentParser(description='Process JSON files to get release notes from PR.')
    parser.add_argument('--json_folder_path', required=True, type=str, help='Folder path containing the JSON files.')
    parser.add_argument('--specific_file', type=str, default=None, help='Optional: Specify a single JSON file to process.')
    parser.add_argument('--category', type=str, required=True, help='Failure category to process (e.g., COMPILATION_FAILURE).')
    parser.add_argument('--output_dir', required=True, type=str, help='Folder path for output folder.')

    return parser.parse_args()



# Function to load JSON file and get pr data
def process_for_release(data,json_file_path,output_dir,logger):
    
    pr_url = data.get('url')
    if not pr_url:
        print("No pull request URL found in the JSON file.")
        return
    
    pr_data, content_type = get_url_data(pr_url, GITHUB_TOKEN)
    logger.info(f"Processing PR: {pr_url}")
  
    if pr_data:
        logger.info(f"PR data retrieved successfully for: {pr_url}")
        logger.info(f"Content type: {content_type}")
        logger.info(f"PR data: {pr_data}")
        if content_type == "html":
            # Extract the release notes from HTML content
            release_info = get_release_notes_from_html(pr_data, data, json_file_path, pr_url)
        else:
            print("Unknown content type, cannot process PR data.")
            return
        if release_info:
            print(f"Release notes found for PR: {pr_url}")
            # Write the extracted information to a CSV file
            write_to_csv(release_info,output_dir)
        else:
            print(f"No release notes found for PR: {pr_url}")    
    else:
        print("Failed to process the pull request.")
  
    
        
def get_release_notes_from_html(html_content,json_data,json_file_path,pr_url):
    """
    This function processes the provided HTML content and extracts release notes.
    
    :param html_content: A string containing HTML content of the PR
    :return: Extracted release notes or a message indicating no release notes were found
    """
    # Try to locate common tags that might contain release notes
    release_notes = extract_release_notes_from_html(html_content)
    release_info = {}
    
    # If release notes found, return them
    if release_notes:
         # Extract data from the JSON structure provided
        dependency_group_id = json_data['updatedDependency']['dependencyGroupID']
        previous_version = json_data['updatedDependency']['previousVersion']
        new_version = json_data['updatedDependency']['newVersion']
        
        release_info["commitID"] = os.path.basename(json_file_path)
        release_info["prURL"] = pr_url
        release_info["dependencyGroupID"] = dependency_group_id
        release_info["previousVersion"] = previous_version
        release_info["newVersion"] = new_version
        release_info["releaseNotes"] = release_notes
        
        return release_info
    else:
        return {}



# Function to write release info to CSV
def write_to_csv(release_info,output_dir):
    if release_info:
        # Convert the release_info dictionary to a DataFrame
        df = pd.DataFrame([release_info])
        csv_file_path = os.path.join(output_dir,release_info["dependencyGroupID"]+"_"+release_info["previousVersion"]+"_"+release_info["newVersion"]+"_release_notes.csv")
        df.to_csv(csv_file_path, index=False)
        print(f"CSV file {csv_file_path} created successfully.")
    else:
        print("No release information found to write to CSV.")

# Main function to process the JSON file and fetch PR info
def main():
    args = parse_arguments()
    try:      
        if args.specific_file:
            specific_file_path = os.path.join(args.json_folder_path, args.specific_file)
            if os.path.exists(specific_file_path):
                logger=setup_logger(f"{args.specific_file.replace(".json","")}.log",args.output_dir)
                data=load_json_file(specific_file_path)
                process_for_release(data,specific_file_path,args.output_dir,logger)
            else:
                print(f"Specified file {args.specific_file} does not exist in {args.json_folder_path}.")
        else:
            files_list = [f for f in os.listdir(args.json_folder_path) if os.path.isfile(os.path.join(args.json_folder_path, f)) and f.endswith('.json')]       
            for filename in files_list:
                if filename.endswith('.json'):
                    json_file_path = os.path.join(args.json_folder_path, filename)
                    logger=setup_logger(f"{filename.replace(".json","")}.log",args.output_dir)
                    data=load_json_file(json_file_path)
                    if data.get('failureCategory') == args.category:
                        print(f"Processing {filename}...")
                        process_for_release(data,json_file_path,args.output_dir,logger)
                    else:
                        print(f"{filename} does not match the failure category '{args.category}' and will not be processed.")
                    print(f"Processed {filename}.")    
    except Exception as e:
        print(f"An error occurred: {e}")   


if __name__ == "__main__":
    main()
