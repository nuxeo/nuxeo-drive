"""
Git changelog generator.
"""

import argparse
import codecs
import operator
import re
import subprocess
import sys

__version__ = "2.0.0"


# Available formatters
FORMAT_ISSUE = {
    "md": {
        "header": "# {title}",
        "subheader": "### {title}",
        "regular": "- [{name}]({url}): {title}",
        "important": "- **[{name}]({url})**: {title}",
    },
    "rst": {
        "header": "{title}\n{separator:{separator}>{length}}",
        "subheader": "{title}\n{separator:{separator}>{length}}",
        "regular": "- `{name} <{url}>`_: {title}",
        "important": "- **[SupCom]** `{name} <{url}>`_: {title}",
    },
    "txt": {
        "header": "{title}",
        "subheader": "{title}:",
        "regular": "- {name}: {title}",
        "important": "- [SupCom] {name}: {title}",
    },
}


def backtick(cmd):
    """Get command output as stripped string."""

    output = subprocess.check_output(cmd)
    return output.decode("utf-8").strip()


def changelog(issues, formatter="txt", func=None):
    """Generate the changelog."""

    fmt = FORMAT_ISSUE[formatter]

    # Important issues first, then regular ones sorted by type, priority, name
    sorter = operator.itemgetter("sla", "type", "priority", "name")
    issues = sorted(issues, key=sorter)

    # Print the header
    version = get_version()
    header = {"title": version, "separator": "=", "length": len(version)}
    print(fmt["header"].format(**header))

    # Print the report
    if not callable(func):
        func = report_categorized
    func(issues, fmt)


def debug(*args, **kwargs):
    """Print a line to STDERR to no pollute generated changelog."""

    print(*args, file=sys.stderr, **kwargs)


def examples():
    """Print several examples."""

    print(
        """
Example {}: changelog.py

    Print changelog of commits from HEAD to the latest release tag.
    If there is no release tag, it will use the full commit history.


Example {}: changelog.py --format=md

    Same as previously, but printed changelog is in Markdown format.


Example {}: changelog.py --format=md --types NXPY SUPNXP

    Same as previously, but printed changelog takes into account only
    NXPY and SUPNXP issues.


Example {}: changelog.py -- HEAD...COMMIT_ID

    Print changelog of commits from HEAD to COMMIT_ID.


Example {}: changelog.py -- HEAD...HEAD~6

    Print changelog of latest 6 commits.


Example {}: changelog.py -- release-2.2.227...release-2.2.323

    Print changelog of commits between the 2 releases.


Example {}: changelog.py -- --since=2017-03-16 --until=2017-03-28

    Print changelog of commits between the dates on the master branch.


Example {}: changelog.py -- --since=2017-03-16 --until=2017-03-28 --author="Mickaël Schoentgen"

    Print changelog of commits between the dates on the master branch for a given author.
    Useful for sprint reports.
""".format(
            *range(1, 42)
        ).strip()
    )  # noqa


def get_latest_tag():
    """Retrieve the latest release tag."""

    debug(">>> Retrieving latest created tag")
    # Retrieve 32 IDs as there may be at least 21 alpha. Taking large.
    cmd = "git rev-list --tags --remove-empty --branches=master --max-count=32"
    latest = ""
    for sha1 in backtick(cmd.split()).splitlines():
        cmd = "git describe --abbrev=0 --tags " + sha1
        tag = backtick(cmd.split())
        if tag.startswith("release-") and tag > latest:
            latest = tag
    return latest


def get_issues(args):
    """Get issues from commits message."""

    if not args.GIT_OPTIONS:
        # No commit ID, so we just need to find commits after the latest tag
        args.GIT_OPTIONS = ["HEAD..." + get_latest_tag()]

    debug(">>> Retrieving commits")
    cmd = ["git", "log", "--pretty=format:%B"] + args.GIT_OPTIONS
    all_commits = backtick(cmd)

    # Match any categories (issue type) with inconsistent use of spaces
    regexp = re.compile(
        r"^((?:{categories})\s*-\s*\d+\s*):.*".format(categories="|".join(args.types)),
        re.IGNORECASE,
    )

    debug(">>> Retrieving issues")
    commits = []
    for commit in all_commits.splitlines():
        # Skip timebox tickets
        if "timebox" in commit.lower():
            continue

        for issue in regexp.findall(commit):
            # Remove superfluous spaces and uppercase the word
            issue = re.sub(r"\s+", "", issue).upper()
            commits.append(issue)

    for commit in set(commits):
        data = get_issue_infos(commit)
        if data:
            yield data


def get_issue_infos(issue, raw=False):
    """Retrieve issue information."""

    debug(">>> Fetching information of {}".format(issue))
    base_url = "https://jira.nuxeo.com"
    url = base_url + "/rest/api/2/issue/{}".format(issue)
    headers = {"User-Agent": "changelog/{}".format(__version__)}

    import requests  # noqa

    for _ in range(5):
        try:
            with requests.get(url, headers=headers) as content:
                data = content.json()
                break
        except (requests.HTTPError, ValueError):
            pass
    else:
        debug(">>> Impossible to to retrieve information, passing")
        return

    # Skip unfinished work
    if data["fields"]["status"]["name"] != "Resolved":
        return

    # Skip timeboxes
    if "timebox" in data["fields"]["summary"].lower():
        return

    if raw:
        return data

    infos = {
        "name": data["key"],
        "url": base_url + "/browse/" + data["key"],
        "title": data["fields"]["summary"],
        "priority": data["fields"]["priority"]["id"],
        "type": data["fields"]["issuetype"]["name"],
        "sla": "regular",
        "components": [],
    }

    # Fill components
    for component in data["fields"]["components"]:
        infos["components"].append(component["name"])

    try:
        # We are not authentificated, so we cannot know the SUPNXP issue but
        # we can know that there is a related SUPNXP and set the issue as
        # high prioriy.
        if "SupCom" in data["fields"]["customfield_10080"]:
            infos["sla"] = "important"
    except (KeyError, TypeError):
        pass

    return infos


def get_version():
    """Find the current version."""

    init_file = "nxdrive/__init__.py"
    with codecs.open(init_file, encoding="utf-8") as handler:
        for line in handler.readlines():
            if line.startswith("__version__"):
                return re.findall(r'"(.+)"', line)[0]


def report_categorized(issues_list, fmt):
    """A report using primary components."""

    components = {
        "Core": [],
        "GUI": [],
        "Packaging / Build": [],
        "Tests": [],
        "Doc": [],
        "Release": [],
    }

    for issue in issues_list:
        line = fmt[issue["sla"]].format(**issue)
        for component, value_ in components.items():
            if component in issue["components"]:
                components[component].append(line)
                break
        else:
            component = "Packaging / Build" if "QA/CI" in components else "Core"
            value_.append(line)

    for component, value in components.items():
        if component == "Release":
            # Release issues are not revelant as they are used
            # to plan new beta or official release
            continue

        if components[component]:
            subheader = {"title": component, "separator": "-", "length": len(component)}
            print(fmt["subheader"].format(**subheader))
            print("\n".join(value))


def main():
    """Main logic."""

    parser = argparse.ArgumentParser()
    parser.add_argument("--version", action="version", version=__version__)
    parser.add_argument("--examples", action="store_true", help="show usage examples")
    parser.add_argument(
        "--format",
        default="txt",
        choices=("md", "rst", "txt"),
        help="report output format (default: %(default)s)",
    )
    parser.add_argument(
        "--types",
        nargs="*",
        default=("NXDRIVE", "NXP"),
        help="issues types (default: NXDRIVE NXP)",
    )
    parser.add_argument(
        "GIT_OPTIONS", nargs="*", help="git options forwarded to `git log`"
    )
    args = parser.parse_args()

    if args.examples:
        examples()
        return

    # Get commits and print out formatted interesting information
    debug(">>> Changelog.py v{}".format(__version__))
    changelog(list(get_issues(args)), formatter=args.format)


if __name__ == "__main__":
    exit(main())
