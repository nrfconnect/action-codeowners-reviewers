import json
import os
import sys
from github import Github
import pathspec

def parse_codeowners(filename):
    rules = []
    with open(filename, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            parts = line.split()
            pattern, owners = parts[0], parts[1:]
            if(pattern == "*" or pattern == "/.*"):
                print(f"Skipping pattern '{pattern}'")
                continue
            rules.append((pattern, owners))
    return rules

def compile_pathspecs(rules):
    compiled = []
    for pattern, owners in rules:
        spec = pathspec.PathSpec.from_lines("gitwildmatch", [pattern])
        compiled.append((spec, owners))
    return compiled

def find_all_reviewers(filepath, compiled_specs):
    matched_reviewers = set()
    for spec, owners in compiled_specs:
        if spec.match_file(filepath):
            print(f"Found matching pattern {spec.patterns[0].pattern} for owners {owners}")
            matched_reviewers.update(owners)
    return matched_reviewers

def split_users_and_teams(owners):
    reviewers = []
    team_reviewers = []
    for owner in owners:
        owner = owner.lstrip("@")
        if "/" in owner:
            team_reviewers.append(owner.split("/", 1)[1])
        else:
            reviewers.append(owner)
    return reviewers, team_reviewers

def main():
    github_token = os.getenv("GITHUB_TOKEN")

    if not github_token:
        raise RuntimeError("Missing github_token input")

    event_path = os.getenv("GITHUB_EVENT_PATH")
    repo_name = os.getenv("GITHUB_REPOSITORY")

    if not all([event_path, repo_name]):
        raise RuntimeError("Missing required GitHub environment variables")

    with open(event_path, "r", encoding="utf-8") as f:
        event = json.load(f)

    pr_number = event["pull_request"]["number"]
    print(f"Processing PR #{pr_number} in {repo_name}...")

    gh = Github(github_token)
    repo = gh.get_repo(repo_name)
    pr = repo.get_pull(pr_number)

    if pr.draft:
        sys.exit(0)

    changed_files = [f.filename for f in pr.get_files()]
    print(f"Changed files: {', '.join(changed_files)}")

    rules = parse_codeowners("CODEOWNERS")
    compiled_specs = compile_pathspecs(rules)

    all_owners = set()
    for file in changed_files:
        matched = find_all_reviewers(file, compiled_specs)
        if matched:
            print(f"{file} → {', '.join(matched)}")
            all_owners.update(matched)

    if not all_owners:
        print("No CODEOWNERS matched any changed files.")
        return

    reviewers, team_reviewers = split_users_and_teams(all_owners)
    print(f"Requesting individual reviewers: {', '.join(reviewers) or 'None'}")
    print(f"Requesting team reviewers: {', '.join(team_reviewers) or 'None'}")

    try:
        pr.create_review_request(reviewers=reviewers, team_reviewers=team_reviewers)
        print("Review request created successfully.")
    except Exception as e:
        print(f"Failed to create review request: {e}")

if __name__ == "__main__":
    main()

