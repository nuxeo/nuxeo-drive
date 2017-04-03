# coding: utf-8
"""
Git changelog generator.

Usage:
  changelog.py [<start_commit>] [<end_commit>] [--format=FORMAT] [--issue-types=TYPE]
  changelog.py (--help|--version)
  changelog.py --examples

Options:
  --help              Show this screen.
  --version           Show version.
  --examples          Show usage examples.
  --format=FORMAT     Output format [default: txt].
  --issue-types=TYPE  Issues types [default: NXDRIVE,NXP].

Arguments:

    start_commit: ''   - use default value (HEAD)
                  SHA1 - commit ID that is the scan upper bound

    end_commit: ''   - use default value (latest release tag)
                SHA1 - commit ID that is the scan lower bound

    FORMAT: md  - Markdown
            rst - reStructuredText
            txt - plain text
"""
from __future__ import print_function, unicode_literals

from operator import itemgetter
from subprocess import check_output
from sys import stderr

from docopt import docopt
from requests import HTTPError, get

__version__ = '1.0.2'


def backtick(cmd):
    """ Get command output as stripped string. """

    output = check_output(cmd.split())
    return output.decode('utf-8').strip()


def changelog(issues, formatter='txt', func=None):
    """ Generate the changelog. """

    # def report_simple(issues_list):
    #     """ A simple report. """
    #
    #     print('Bug fixes / improvements:')
    #     for issue in issues_list:
    #         print(formatter[issue['sla']].format(**issue))

    def report_categorized(issues_list):
        """ A more sophisticated report using primary components. """

        components = {'Core': [], 'GUI': [], 'Packaging / Build': [],
                      'Tests': [], 'Doc': []}

        for issue in issues_list:
            for component in components:
                if component in issue['components']:
                    components[component].append(
                        formatter[issue['sla']].format(**issue))
                    break
            else:
                components['Core'].append(
                    formatter[issue['sla']].format(**issue))

        for component in components:
            if components[component]:
                subheader = {'title': component,
                             'separator': '-',
                             'length': len(component)}
                print(formatter['subheader'].format(**subheader))
                print('\n'.join(components[component]))

    # Available formatters
    format_issue = {
        'md': {'header': '# {title}',
               'subheader': '### {title}',
               'regular': '- [{name}]({url}): {title}',
               'important': '- **[{name}]({url})**: {title}'},
        'rst': {'header': '{title}\n{separator:{separator}>{length}}',
                'subheader': '{title}\n{separator:{separator}>{length}}',
                'regular': '- `{name} <{url}>`_: {title}',
                'important': '- **[SupCom]** `{name} <{url}>`_: {title}'},
        'txt': {'header': '{title}',
                'subheader': '{title}:',
                'regular': '- {name}: {title}',
                'important': '- [SupCom] {name}: {title}'}
    }
    formatter = format_issue[formatter]

    # Important issues first, then regular ones sorted by type, priority, name
    issues = sorted(issues, key=itemgetter('sla', 'type', 'priority', 'name'))

    # Print the header
    version = get_version()
    header = {'title': version,
              'separator': '=',
              'length': len(version)}
    print(formatter['header'].format(**header))

    # Print the report
    if not callable(func):
        func = report_categorized
    func(issues)


def debug(*args, **kwargs):
    """ Print a line to STDERR to no pollute generated changelog. """

    print(*args, file=stderr, **kwargs)


def examples():
    """
For every command, you can specify --format and --issue-types arguments.
And, of course, you can use git notations like "HEAD^", "HEAD~6", etc..

Example 1: changelog.py

    Print changelog of commits from HEAD to the latest release tag.
    If there is no release tag, it will use the full commit history.

Example 2: changelog.py COMMIT_ID

    Print changelog of commits from COMMIT_ID to the latest release tag.
    If there is no release tag, it will use the full commit history starting
    from COMMIT_ID.

Example 3: changelog.py '' COMMIT_ID

    Print changelog of commits from HEAD to COMMIT_ID.

Example 4: changelog.py release-2.2.227 release-2.3.323

    Print changelog of commits between the 2 releases.
    """

    print(examples.__doc__.strip())


def get_commits_between(start, end):
    """ Retrieve commits between two states. """

    commit_range = start
    if end:
        commit_range = '{}...{}'.format(start, end)
    debug('>>> Retrieving commits {}'.format(commit_range))
    all_commits = backtick('git log --pretty=oneline ' + commit_range)
    return sorted(all_commits.splitlines(), reverse=True)


def get_latest_tag():
    """ Retrieve the latest release tag. """

    debug('>>> Retrieving latest created tag')
    cmd = 'git rev-list --tags --remove-empty --branches=master --max-count=10'
    for sha1 in backtick(cmd).splitlines():
        tag = backtick('git describe --abbrev=0 --tags ' + sha1)
        if tag.startswith('release-'):
            return tag
    return ''


def get_issues(start='HEAD', end=None, types=('NXDRIVE', 'NXP')):
    """ Get issues from commits message. """

    if not start:
        start = 'HEAD'
    if not end:
        # No commit ID, so we just need to find commits after the latest tag
        end = get_latest_tag()

    all_commits = get_commits_between(start, end)
    debug('>>> Retrieving issues')
    commits = []
    reverts = []
    for commit in all_commits:
        parts = commit.split()
        for issue_type in types:
            if parts[1] == 'Revert':
                issue = parts[2].lstrip('"').rstrip(':')
                reverts.append(issue)
                break
            elif parts[1].startswith(issue_type):
                issue = parts[1].split(':')[0]
                commits.append(issue)
                break

    for commit in set(set(commits) - set(reverts)):
        data = get_issue_infos(commit)
        if data:
            yield data


def get_issue_infos(issue, raw=False):
    """ Retrieve issue informations. """

    debug('>>> Fetching informations of {}'.format(issue))
    base_url = 'https://jira.nuxeo.com'
    url = base_url + '/rest/api/2/issue/{}'.format(issue)

    for _ in range(5):
        try:
            content = get(url)
            break
        except HTTPError:
            pass
        finally:
            data = content.json()
    else:
        debug('>>> Impossible to to retrieve informations, passing')
        return

    # Skip unfinished work
    if data['fields']['status']['name'] != 'Resolved':
        return

    if raw:
        return data

    infos = {'name': data['key'],
             'url': base_url + '/browse/' + data['key'],
             'title': data['fields']['summary'],
             'priority': data['fields']['priority']['id'],
             'type': data['fields']['issuetype']['name'],
             'sla': 'regular', 'components': []}

    # Fill components
    for component in data['fields']['components']:
        infos['components'].append(component['name'])

    try:
        # We are not authentificated, so we cannot know the SUPNXP issue but
        # we can know that there is a related SUPNXP and set the issue as
        # high prioriy.
        if 'SupCom' in data['fields']['customfield_10080']:
            infos['sla'] = 'important'
    except (KeyError, TypeError):
        pass

    return infos


def get_version():
    """ Find the current version. """

    init_file = 'nuxeo-drive-client/nxdrive/__init__.py'
    with open(init_file) as handler:
        for line in handler.readlines():
            if line.startswith('__version__'):
                return line.split('=')[1].replace("'", '').strip()


def main():
    """ Main logic. """

    debug('>>> Changelog.py v{}'.format(__version__))

    args = docopt(__doc__, version=__version__)

    if args['--examples']:
        examples()
        return

    start = args['<start_commit>']
    end = args['<end_commit>']
    issue_types = set(args['--issue-types'].split(','))
    formatter = args['--format']

    if formatter not in ('md', 'rst', 'txt'):
        formatter = 'txt'
        debug('>>> Bad formatter value, using "{}"'.format(formatter))

    # Get commits and print out formatted interesting informations
    issues = []
    for issue in get_issues(start=start, end=end, types=issue_types):
        issues.append(issue)
    changelog(issues, formatter=formatter)


if __name__ == '__main__':
    exit(main())
