#Get the url from the json file for the commit, reterive the PR from github and check if it contains release notes for the version update
import json
import requests
import pandas as pd
import argparse
from dotenv import load_dotenv
import os
from bs4 import BeautifulSoup
import logging

## Load environment variables from .env file
load_dotenv()

# Get SSH details from environment variables
# GitHub API token for authentication (optional)
GITHUB_TOKEN = os.getenv('GITHUB_TOKEN')


def parse_arguments():
    parser = argparse.ArgumentParser(description='Process JSON files to get release notes from PR.')
    parser.add_argument('--json_folder_path', required=True, type=str, help='Folder path containing the JSON files.')
    parser.add_argument('--specific_file', type=str, default=None, help='Optional: Specify a single JSON file to process.')
    parser.add_argument('--category', type=str, required=True, help='Failure category to process (e.g., COMPILATION_FAILURE).')
    parser.add_argument('--output_dir', required=True, type=str, help='Folder path for output folder.')

    return parser.parse_args()

def _setup_logger(logfile_name, output_dir):
    """Sets up logging to log messages to a file."""
    logs_output_dir = os.path.join(output_dir, "logs")
    os.makedirs(logs_output_dir, exist_ok=True)
    log_file = os.path.join(logs_output_dir, logfile_name)

    # Create a logger instance for each log file
    logger = logging.getLogger(logfile_name)
    logger.setLevel(logging.INFO)

    # Check if the logger already has handlers
    if not logger.hasHandlers():
        file_handler = logging.FileHandler(log_file)
        file_handler.setLevel(logging.INFO)
        stream_handler = logging.StreamHandler()
        stream_handler.setLevel(logging.INFO)

        # Define the formatter and set it for both handlers
        formatter = logging.Formatter('%(levelname)s - %(message)s')
        file_handler.setFormatter(formatter)
        stream_handler.setFormatter(formatter)

        logger.addHandler(file_handler)
        logger.addHandler(stream_handler)

    return logger


# Function to load JSON file and get pr data
def process_for_release(data,json_file_path,output_dir,logger):
    
    pr_url = data.get('url')
    if not pr_url:
        print("No pull request URL found in the JSON file.")
        return
    
    pr_data, content_type = get_pr_data(pr_url)
    logger.info(f"Processing PR: {pr_url}")
  
    if pr_data:
        logger.info(f"PR data retrieved successfully for: {pr_url}")
        logger.info(f"Content type: {content_type}")
        logger.info(f"PR data: {pr_data}")
        # Decide which extraction method to use based on content type
        if content_type == "json":
            # Extract the release notes and other information from JSON
            release_info = extract_release_info_from_json(pr_data, data, json_file_path, pr_url)
        elif content_type == "html":
            # Extract the release notes from HTML content
            release_info = extract_release_notes_from_html(pr_data, data, json_file_path, pr_url)
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
  
    


# Function to retrieve the PR data from the URL
def get_pr_data(pr_url):
    headers = {
        "Accept": "application/vnd.github.v3+json"
    }
    
    # Add token for authenticated requests (optional)
    if GITHUB_TOKEN:
        headers["Authorization"] = f"token {GITHUB_TOKEN}"
    
    try:
        response = requests.get(pr_url, headers=headers)
        
        if response.status_code == 200:
                #Check if the content is JSON
                if response.headers.get("Content-Type") == "application/json":
                    # Try to parse the JSON response
                    return response.json(), "json"
                #check if resposne.header.get("Content-Type") contains text/html
                if response.headers.get("Content-Type").find("text/html") > -1:
                    return response.text, "html"
               
                else:
                     # Print the raw response if it's not JSON or HTML
                    print(f"Unexpected content type: {response.headers.get('Content-Type')}")
                    print("Response body:", response.text)
                    return None, None
        else:
            print(f"Failed to retrieve PR data. Status code: {response.status_code}")
            print("Response body:", response.text)
            return None, None

    except Exception as e:
        print(f"Error processing pr url: {e}")
        print("Raw response content:", response.text)
        return None
      
        
def extract_release_notes_from_html(html_content,json_data,json_file_path,pr_url):
    """
    This function processes the provided HTML content and extracts release notes.
    
    :param html_content: A string containing HTML content of the PR
    :return: Extracted release notes or a message indicating no release notes were found
    """

    # Try to locate common tags that might contain release notes
    release_notes = None
    release_info = []
    
    # Parse the HTML content using BeautifulSoup
    soup = BeautifulSoup(html_content, 'html.parser')

    # Try to locate the text with release notes
    divs = soup.find_all('div')

    for div in divs:
        print(div.text)
        if 'release notes' in div.text.lower():
            release_notes = div.text.strip()
            break

    details = soup.find('details', open=True)
    release_notes = None

    if details:
        summary = details.find('summary')
        if summary and 'release notes' in summary.text.lower():
            # Extract the text inside the <blockquote> and any <ul> for structured release notes
            blockquote = details.find('blockquote')
            ul_list = details.find_all('ul')

            release_notes = ""
            
            # Extract and format the blockquote content
            if blockquote:
                release_notes += blockquote.text.strip() + "\n\n"
            
            # Extract and format the list of bullet points
            if ul_list:
                for ul in ul_list:
                    for li in ul.find_all('li'):
                        release_notes += f"- {li.text.strip()}\n"
    
    # If release notes found, return them
    if release_notes:
         # Extract data from the JSON structure provided
        dependency_group_id = json_data['updatedDependency']['dependencyGroupID']
        previous_version = json_data['updatedDependency']['previousVersion']
        new_version = json_data['updatedDependency']['newVersion']
        
        # Append the extracted data
        release_info.append({
            "commitID": os.path.basename(json_file_path),
            "prURL": pr_url,
            "dependencyGroupID": dependency_group_id,
            "previousVersion": previous_version,
            "newVersion": new_version,
            "releaseNotes": release_notes
        })
        return release_info
    else:
        return []

# Function to check if PR has release notes and return the required data
def extract_release_info_from_json(pr_data, json_data, json_file_path, pr_url):
    release_info = []
    
    # Extract the PR body where release notes might be present
    pr_body = pr_data.get('body', '')
    
    # Check if the PR contains release notes
    if 'release notes' in pr_body.lower():
        release_notes = pr_body.split("Release Notes:")[1].strip() if "Release Notes:" in pr_body else "No notes"
        
        # Extract data from the JSON structure provided
        dependency_group_id = json_data['updatedDependency']['dependencyGroupID']
        previous_version = json_data['updatedDependency']['previousVersion']
        new_version = json_data['updatedDependency']['newVersion']
        
        # Append the extracted data
        release_info.append({
            "commitID": os.path.basename(json_file_path),
            "prURL": pr_url,
            "dependencyGroupID": dependency_group_id,
            "previousVersion": previous_version,
            "newVersion": new_version,
            "releaseNotes": release_notes
        })
    
    return release_info

# Function to load JSON file
def load_json_file(json_file_path):
    with open(json_file_path, 'r') as file:
        return json.load(file)

# Function to write release info to CSV
def write_to_csv(release_info,output_dir):
    if release_info:
        df = pd.DataFrame(release_info)
        csv_file_path = os.path.join(output_dir,release_info["commitID"],"release_info.csv")
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
                logger=_setup_logger(f"{args.specific_file.replace(".json","")}.log",args.output_dir)
                data=load_json_file(specific_file_path)
                process_for_release(data,specific_file_path,args.output_dir,logger)
            else:
                print(f"Specified file {args.specific_file} does not exist in {args.json_folder_path}.")
        else:
            files_list = [f for f in os.listdir(args.json_folder_path) if os.path.isfile(os.path.join(args.json_folder_path, f)) and f.endswith('.json')]       
            for filename in files_list:
                if filename.endswith('.json'):
                    json_file_path = os.path.join(args.json_folder_path, filename)
                    logger=_setup_logger(f"{filename.replace(".json","")}.log",args.output_dir)
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
