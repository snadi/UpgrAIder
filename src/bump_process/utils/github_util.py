import requests
from bs4 import BeautifulSoup
import bs4
import re


# Function to retrieve the data from the URL
def get_url_data(url,github_token):
    headers = {
        "Accept": "text/html"
    }
    
    # Add token for authenticated requests (optional)
    if github_token:
        headers["Authorization"] = f"token {github_token}"
    
    try:
        response = requests.get(url, headers=headers)
        
        if response.status_code == 200:
                #check if resposne.header.get("Content-Type") contains text/html
                if response.headers.get("Content-Type").find("text/html") > -1:
                    return response.text, "html"
               
                else:
                     # Print the raw response if it's not JSON or HTML
                    print(f"Unexpected content type: {response.headers.get('Content-Type')}")
                    print("Response body:", response.text)
                    return None, None
        else:
            print(f"Failed to retrieve URL data. Status code: {response.status_code}")
            print("Response body:", response.text)
            return None, None

    except Exception as e:
        print(f"Error processing pr url: {e}")
        print("Raw response content:", response.text)
        return None,None
      

#Function to get the release notes or repository URL from the PR URL
def get_release_or_repo_url(pr_url,github_token):
    #Check if the PR URL is a valid URL
    if not pr_url:
        raise ValueError("PR URL is not valid")
    #get PR HTML content
    pr_data, content_type = get_url_data(pr_url,github_token)
    #check if the PR data is retrieved successfully
    if pr_data:
        #Check if the content type is HTML
        if content_type == "html":
            #parse the HTML content
            soup = BeautifulSoup(pr_data, 'html.parser')
            #check if the PR has release notes, if so return the link for the library release notes
            all_tags = soup.find_all('code')
            if all_tags:
                for tag in all_tags:
                    if 'bump' in tag.text.lower():
                        # Iterate through the contents of the tag
                        for c in tag.contents:
                            print(type(c))
                            # Check if 'Release notes' is present in the content        
                            if isinstance(c,bs4.element.Tag) and c.name == 'a':
                                # If it's an <a> tag, check if its content contains 'Release notes'
                                if 'bump' in c.text.lower():
                                    # Extract and print the href attribute of the <a> tag
                                    data = c.attrs
                                    print(type(data))
                                    print("Data:", data)
                                    # Extract the 'title' field from the dictionary
                                    title_content = data.get('title', '')
                                    # Use a regular expression to find the URL for "Release notes"
                                    match = re.search(r'\[Release notes\]\((https?://[^\s]+)\)', title_content)
                                    # If a match is found, print the URL
                                    if match:
                                        release_notes_link = match.group(1)
                                        print("Release Notes Link:", release_notes_link)
                                        return "Release Notes",release_notes_link   
                                    else:
                                        print("Release Notes Link not found.")
                                             
            #TODO: if the PR does not have release notes, return the library repo url to check release                             
            return None
        else:
            raise ValueError("Content type is not HTML")
    else:
        raise ValueError("Failed to retrieve PR data")
    
def extract_release_notes_from_html(html_content):
    # Try to locate common tags that might contain release notes
    release_notes = None
        
    # Parse the HTML content using BeautifulSoup
    soup = BeautifulSoup(html_content, 'html.parser')

    # Try to locate the text with release notes

    details = soup.find_all('details')
    release_notes = None

    if details:
        for detail in details:      
            summary = detail.find('summary')
            if summary and 'release notes' in summary.text.lower():
                # Extract the text inside the <blockquote> and any <ul> for structured release notes
                blockquote = detail.find('blockquote')
                ul_list = detail.find_all('ul')

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
            return release_notes 
        else:
            return None
