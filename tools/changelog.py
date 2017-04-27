# coding: utf-8
"""
Git changelog generator.
"""
from __future__ import print_function, unicode_literals

from argparse import ArgumentParser
from operator import itemgetter
from re import findall
from subprocess import check_output
from sys import stderr

from requests import HTTPError, get

__version__ = '1.2.0'


def backtick(cmd):
    """ Get command output as stripped string. """

    output = check_output(cmd)
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
    """ Print several examples. """

    print("""
Example {}: changelog.py

    Print changelog of commits from HEAD to the latest release tag.
    If there is no release tag, it will use the full commit history.


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
""".format(*range(1, 42)).strip())  # noqa


def get_latest_tag():
    """ Retrieve the latest release tag. """

    debug('>>> Retrieving latest created tag')
    cmd = 'git rev-list --tags --remove-empty --branches=master --max-count=10'
    for sha1 in backtick(cmd.split()).splitlines():
        cmd = 'git describe --abbrev=0 --tags ' + sha1
        tag = backtick(cmd.split())
        if tag.startswith('release-'):
            return tag
    return ''


def get_issues(args):
    """ Get issues from commits message. """

    if not args.GIT_OPTIONS:
        # No commit ID, so we just need to find commits after the latest tag
        args.GIT_OPTIONS = ['HEAD...' + get_latest_tag()]

    debug('>>> Retrieving commits {}'.format(
        ' '.join(arg.decode('utf-8') for arg in args.GIT_OPTIONS)))
    cmd = ['git', 'log', '--pretty=oneline'] + args.GIT_OPTIONS
    all_commits = backtick(cmd)

    debug('>>> Retrieving issues')
    commits = []
    reverts = []
    for commit in sorted(all_commits.splitlines(), reverse=True):
        parts = commit.split()
        for issue_type in args.types:
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
                return findall(r"'(.+)'", line)[0]


def main():
    """ Main logic. """

    parser = ArgumentParser()
    parser.add_argument('--version', action='version', version=__version__)
    parser.add_argument('--examples', action='store_true',
                        help='show usage examples')
    parser.add_argument('--drive-version', action='store_true',
                        help='show Nuxeo Drive version')
    parser.add_argument('--format', default='txt',
                        choices=('md', 'rst', 'txt'),
                        help='report output format (default: %(default)s)')
    parser.add_argument('--types', nargs='*', default=('NXDRIVE', 'NXP'),
                        help='issues types (default: NXDRIVE NXP)')
    parser.add_argument('GIT_OPTIONS', nargs='*',
                        help='git options forwarded to `git log`')
    args = parser.parse_args()

    if args.examples:
        examples()
        return
    elif args.drive_version:
        print(get_version())
        return

    # Get commits and print out formatted interesting informations
    debug('>>> Changelog.py v{}'.format(__version__))
    changelog([issue for issue in get_issues(args)], formatter=args.format)


if __name__ == '__main__':
    exit(main())
