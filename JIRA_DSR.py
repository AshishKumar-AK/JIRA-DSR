#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
-----------------------------------------------------------------------------
The purpose of this script is generate Daily status report of JIRA Projects.
For detailed information check README.md file
-----------------------------------------------------------------------------
"""
import os
import requests
import dateutil.parser as dt
import pytz
import argparse
import math
import csv
import traceback
import time
from lib.logger import InteractiveLogger
from datetime import datetime, date, timedelta
from lxml import etree
from jinja2 import Environment, FileSystemLoader
from jira import JIRA
from requests.packages.urllib3.exceptions import InsecureRequestWarning
from lib.sendMail import EmailMessage, SMTPMailer, GMAILAPIMailer
from lib.fsutil import FSUtil


class DSRException(Exception):
    """
    Custom expection class just to hold error conditions
    specific to DSR report generation
    """
    pass


class ProjectConfig:
    """
    This class maps to per project XML config file values.
    """
    def __init__(self, key, manager, url, user, passwd, timezone, source):
        self.key = key
        self.manager = manager
        self.url = url
        self.user = user
        self.passwd = passwd
        self.timezone = timezone
        self.source = source

    def __str__(self):
        return self.key

    def __eq__(self, other):
        return self.key + self.url == other.key + other.url


class SourceConfig:
    """
    This class maps to values of source xml tag defined in project xml config file.
    """
    def __init__(self, _type, url, user, passwd, repo):
        self.type = _type
        self.url = url
        self.user = user
        self.passwd = passwd
        self.repo = repo


class DSRUtil:
    """
    Utility class which conatins many common methods which are being used
    throughout DSR report generation
    """
    @staticmethod
    def get_seconds_in_hour_and_minutes(seconds):
        """
        :param seconds:
        :return: formatted string in "xh ym" format (eg: 6h 11m)
        """
        hours = int(math.modf(seconds / 3600)[1])
        minutes = int(math.modf(seconds % 3600 / 60)[1])
        return "{0}h {1}m".format(hours, minutes)

    @staticmethod
    def get_yesterday_date():
        """
        :return: yeseterday's date in datetime object
        """
        return date.today() - timedelta(1)

    @staticmethod
    def valid_date(date_string):
        """
        :param date_string:
        :return: date_string only if string is in valid date format of '%Y-%m-%d %H:%M'
        else raises argument exception
        """
        try:
            datetime.strptime(date_string, "%Y-%m-%d %H:%M")
            return date_string
        except ValueError:
            msg = "Not a valid date: '{0}' check -h/--help for info".format(date_string)
            raise argparse.ArgumentTypeError(msg)

    @staticmethod
    def valid_path(path):
        """
        :param path:
        :return: path only if provided path string is a valid directory path
        else raises argument exception
        """
        if os.path.isdir(path):
            return path
        else:
            msg = "Not a valid path: '{0}' check -h/--help for info".format(path)
            raise argparse.ArgumentTypeError(msg)

    @staticmethod
    def validate_config_schema(config_xml, xsd):
        """
        :param config_xml:
        :param xsd:
        :return: bool True if Project config xml is valid againts xml schema
        else raises exception
        """
        try:
            with open(xsd, 'r') as f:
                schema_root = etree.XML(f.read())
            schema = etree.XMLSchema(schema_root)
            validator = etree.XMLParser(schema=schema)
            with open(config_xml, 'r') as f:
                etree.fromstring(f.read(), validator)
            return True
        except etree.XMLSchemaError:
            raise

    @staticmethod
    def parse_config(config_xml):
        """
        This method takes Project xml config file and
        returns Project config class object after parsing it

        :param config_xml: Project xml config file
        :return: ProjectConfig object
        """
        project = etree.parse(config_xml).getroot()
        if project.attrib['enabled'].upper() == 'TRUE':
            key = project.attrib['key']
            manager = project.attrib['manager'].split(",")
            url = project.attrib['url']
            user = project.attrib['user']
            passwd = project.attrib['password']
            timezone = project.attrib['timezone']
            source = project.find('source')
            source_type = source.attrib['type'].upper()
            if source_type in ('FISHEYE', 'STASH'):
                source_config = SourceConfig(source_type,
                                             source.attrib['url'],
                                             source.attrib['user'],
                                             source.attrib['password'],
                                             source.attrib['repo'])
            else:
                raise DSRException("Project {0} is not having correct source type value: {1}".format(key, source_type))
            config = ProjectConfig(key, manager, url, user, passwd, timezone, source_config)
            return config
        else:
            raise DSRException("Project is not enabled in XML file: {0}".format(config_xml))

    @staticmethod
    def create_email(subject, recipient, cc, body, attachment):
        """
        This method takes email message headers and content and
        returns an email message object
        :param subject: string
        :param recipient: string
        :param cc: string
        :param body: string
        :param attachment: string
        :return: an email message object
        """
        _from = "dsr-report@forgeahead.io"
        to = recipient if type(recipient) is list else [recipient]
        cc = cc if type(cc) is list else [cc]
        message = EmailMessage()
        message.add_mail_headers(subject, _from, to, cc)
        message.add_html_msg(body)
        if attachment:
            message.add_mail_attachments([attachment])
        return message

    @staticmethod
    def send_email(subject, recipient, cc, body, attachment, args):
        """
        This method sends email message based on email method type
        :param subject: string
        :param recipient: string
        :param cc: string
        :param body: string
        :param attachment: file path string
        :param args: Argparse object
        :return: None
        """
        message = DSRUtil.create_email(subject, recipient, cc, body, attachment)
        if args.email_method == 'SMTP':
            SMTPMailer.send_mail(message, args.smtp_server, args.smtp_port,
                                 args.smtp_tls, args.smtp_user, args.smtp_passwd)
        if args.email_method == 'GMAIL_API':
            secret = os.path.join(args.base_path, args.gmail_config)
            storage = os.path.join(args.base_path, 'gmail.storage')
            GMAILAPIMailer.send_mail(message, secret, storage)


class JIRAProject:
    """
    Custom class which represents a JIRA project for DSR report
    """
    JQL = 'project={project} AND (created >= "{start}" and created <= "{end}") ' \
          'OR (updated >= "{start}" and updated <= "{end}") order by updated asc'

    def __init__(self, config, start_date, end_date):
        self.config = config
        self.start_date = start_date
        self.end_date = end_date
        self.jira = JIRA(server=config.url, basic_auth=(config.user,
                                                        config.passwd))
        self.timezone = pytz.timezone(config.timezone)
        self.name = self.jira.project(config.key).name

    def __str__(self):
        return self.name

    def __eq__(self, other):
        return self.config.key == other

    def get_project_issues(self):
        """
        This method returns a list of JIRA issue objects which have
        any activities within specified start and end date
        s
        :return: [JIRAIssue objects]
        """
        jira_issues_in_proj = self.jira.search_issues(
            JIRAProject.JQL.format(project=self.config.key, start=self.start_date, end=self.end_date))
        if jira_issues_in_proj:
            project_issues = list()
            for issue in jira_issues_in_proj:
                project_issue = JIRAIssue(self,
                                          self.jira,
                                          issue.key,
                                          self.start_date,
                                          self.end_date)
                project_issues.append(project_issue)
            return project_issues


class JIRAIssue:
    """
    Custom class which represents an JIRA issue for DSR report
    """
    def __init__(self, parent, jira, key, start_date, end_date):
        self.parent = parent
        self.jira = jira
        self.key = key
        self.issue = self.jira.issue(key)
        self.start_time = parent.timezone.localize(dt.parse(start_date))
        self.end_time = parent.timezone.localize(dt.parse(end_date))

    def __str__(self):
        return self.key

    def __eq__(self, other):
        return self.key == other

    def get_project(self):
        return self.issue.fields.project.name

    def get_title(self):
        return self.issue.fields.summary

    def get_priority(self):
        return self.issue.fields.priority.name

    def get_assignee(self):
        return self.issue.fields.assignee.displayName

    def get_status(self):
        return self.issue.fields.status.name

    def get_estimated_time(self):
        return DSRUtil.get_seconds_in_hour_and_minutes(self.issue.fields.timeestimate)

    def get_total_spent_time(self):
        return DSRUtil.get_seconds_in_hour_and_minutes(self.issue.fields.timespent)

    def get_work_logs(self):
        """
        This method returns list of Userlog class objects which contains
        details of each work log entered against an JIRA issue within
        specified start and end date

        :return: [Userlog objects]
        """
        userlogs = dict()
        if self.issue.fields.worklog.total:
            for worklog in self.issue.fields.worklog.worklogs:
                issue_updated = dt.parse(worklog.updated).astimezone(self.parent.timezone)
                if self.start_time <= issue_updated <= self.end_time:
                    author = worklog.updateAuthor.displayName
                    email = worklog.updateAuthor.emailAddress
                    if author not in userlogs:
                        userlogs[author] = UserLog(self,
                                                   self.jira,
                                                   self.issue,
                                                   author,
                                                   email,
                                                   self.start_time,
                                                   self.end_time)
                    userlogs[author].add_work_log_time(worklog.timeSpentSeconds)
                    userlogs[author].add_work_log_comment(worklog.comment)
        return userlogs


class UserLog:
    """
    Custom class which represents a JIRA work log entry entered on an JIRA issue.
    """
    def __init__(self, parent, jira, issue, name, email, start_time, end_time):
        self.parent = parent
        self.jira = jira
        self.issue = issue
        self.name = name
        self.email = email
        self.start_time = start_time
        self.end_time = end_time
        self.time = 0
        self.work_log_comments = list()

    def __str__(self):
        return self.name

    def __eq__(self, other):
        return self.name == other

    def add_work_log_time(self, t):
        self.time += t

    def add_work_log_comment(self, comment):
        self.work_log_comments.append(comment)

    def get_work_log_time(self):
        return DSRUtil.get_seconds_in_hour_and_minutes(self.time)

    def get_user_issue_comments(self):
        """
        This method returns a list of user comment strings which have been
        logged on an JIRA issue within specified start and end date

        :return: [user comment strings]
        """
        comments = []
        if self.issue.fields.comment.total:
            for comment in self.issue.fields.comment.comments:
                updated = dt.parse(comment.updated).astimezone(self.parent.parent.timezone)
                if comment.updateAuthor.displayName == self.name and \
                        (self.start_time <= updated <= self.end_time):
                    comments.append(comment.body)
        return comments

    def get_user_issue_commits(self):
        # TODO: Implement method to get all user commits against
        # TODO: JIRA issue within specified start and end date based on
        # TODO: based on source code review system type either FishEye or Stash
        pass

    def get_user_issue_state_transitions(self):
        """
        This method returns a list of state transition strings which have been
        performed on an JIRA issue by users within specified start and end date

        :return: [issue state transitions]
        """
        changelog = self.jira.issue(self.issue.key, expand='changelog').changelog
        if changelog.histories:
            states = []
            for history in changelog.histories:
                created = dt.parse(history.created).astimezone(self.parent.parent.timezone)
                if history.author.displayName == self.name \
                        and (self.start_time <= created <= self.end_time):
                    for item in history.items:
                        if item.field == "status":
                            states.append((item.fromString, item.toString))
            return ["->".join(x) for x in states]


# GLOBAL VARIABLES
# Global logger object used throughout the script
logger = None
# Global variable which holds details about all project DSR report status and script run summary
summary = dict(validation=list(), success=list(), noreport=list(), failed=list())
parser = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
parser.add_argument("--attach", action="store_true",
                    help="Send generated DSR Report as attachment as well in report email")
parser.add_argument("--base_path", default=os.getcwd(), type=DSRUtil.valid_path,
                    help="Relative base path ($base_path) to find all config, "
                         "schema and template files and generate reports and logs "
                         "[DEFAULT: current working directory] ")
parser.add_argument("--config", help="Name of JIRA Project config XML file present under conf "
                                     "directory for which DSR report should be generated")
parser.add_argument("--email_method", choices=['SMTP', 'GMAIL_API'], default='SMTP',
                    help="Sending email using SMTP or GMAIL API method [DEFAULT: SMTP]")
parser.add_argument("--gmail_config", default="client_secret_gmail_api.json",
                    help="Name of the json config file present under conf directory "
                         "which contains OAuth credentials for gmail account"
                         "[DEFAULT: ${base_path}/conf/client_secret_gmail_api.json]")
parser.add_argument("--interactive", action="store_true", default=False,
                    help="Produce logs on standard output as well [DEFAULT: False]")
parser.add_argument("--schema", default="schema.xsd",
                    help="XSD schema validation file name present under conf directory "
                         "to validate JIRA project's config xml file structure"
                         "[DEFAULT: ${base_path}/conf/schema.xsd]", )
parser.add_argument("--report", choices=['HTML', 'CSV'], default='HTML',
                    help="In which format the DSR report should be generated [DEFAULT: HTML]")
parser.add_argument("--smtp_server", default="localhost", help="[DEFAULT: localhost]")
parser.add_argument("--smtp_port", default=25, help="[DEFAULT: 25]")
parser.add_argument("--smtp_user")
parser.add_argument("--smtp_passwd")
parser.add_argument("--smtp_tls", action="store_true", default=False,
                    help="[DEFAULT: False]")
parser.add_argument("--ssl_silent", action="store_true", default=True,
                    help="Suppress SSL certificate warnings about https URLs for those "
                         "JIRA server which do not have valid SSL certificate")
parser.add_argument("--start_date", type=DSRUtil.valid_date,
                    default=DSRUtil.get_yesterday_date().strftime('%Y-%m-%d 00:00'),
                    help="format YYYY-MM-DD HH:MM [DEFAULT: yesterday's date]")
parser.add_argument("--end_date", type=DSRUtil.valid_date,
                    default=DSRUtil.get_yesterday_date().strftime('%Y-%m-%d 23:59'),
                    help="format YYYY-MM-DD HH:MM [DEFAULT: yesterday's date]")
parser.add_argument("--template", default="JIRA-DSR-template.html",
                    help="Name of the jinja2 HTML template file present under conf directory "
                         "which will be used to generate HTML DSR reports"
                         "[DEFAULT: ${base_path}/template/JIRA-DSR-template.html]")
parser.add_argument("--validate", action="store_true",
                    help="Validate JIRA config xml file against XSD schema "
                         "and also check for correct JIRA project config values")
parser.add_argument("--verbose", action="store_true", default=False,
                    help="enable debug level log output [DEFAULT: False]")
parser.add_argument("--summary", help="email address to send report run summary of script "
                                      "with script execution log as attachment")


def validate_config_value(config):
    """
    :param config: Project XML config class object
    :return: bool True if Project XML config values are valid else raises Exception
    """
    try:
        logger.debug("Connecting with Project JIRA server at URL [{}]".format(config.url))
        jira = JIRA(server=config.url, basic_auth=(config.user, config.passwd))
        logger.debug("Successfully connected!")
        logger.debug("Checking if project key exists [{0}] in server".format(config.key))
        name = jira.project(config.key).name
        logger.debug("Project key [{0}] with name [{1}] exists in server".format(config.key, name))
        return True
    except Exception:
        raise


def validate_config_file(config_xml, schema):
    """
    This function returns ProjectConfig object if project config xml file
    is validated correctly against xsd schema and xml values are correct as well.

    :param config_xml: (string) file path to project xml config
    :param schema: (string) file path to xml schema
    :return: ProjectConfig object
    """
    logger.info("Validating {} JIRA Project config xml file against "
                "xsd schema".format(config_xml))
    if DSRUtil.validate_config_schema(config_xml, schema):
        logger.info("{} JIRA Project config xml validated against xsd schema "
                    "successfully".format(config_xml))
        config = DSRUtil.parse_config(config_xml)
        if validate_config_value(config):
            logger.info("{} JIRA Project config xml values validated "
                        "correctly".format(config_xml))
            return config


def parse_arguments(args):
    """
    This function parses all the argument values passed to script
    and sets script wide variables based on their values

    :param args: Argparse object
    :return: None
    """
    logger.info("Parsing script arguments...")
    if args.ssl_silent:
        logger.debug("--ssl-silent argument is passed. "
                     "Disabling JIRA server HTTPS URL certificate validation")
        requests.packages.urllib3.disable_warnings(InsecureRequestWarning)
        JIRA.DEFAULT_OPTIONS['verify'] = False

    conf_base = os.path.join(args.base_path, 'conf')
    args.schema = os.path.join(conf_base, args.schema)

    args.template = os.path.join('template', args.template)
    env = Environment(loader=FileSystemLoader(searchpath=args.base_path))
    args.template = env.get_template(args.template)

    args.gmail_config = os.path.join(conf_base, args.gmail_config)

    if not args.config:
        logger.debug("no explicit Project XML config file defined using --config option."
                     "Script will process all JIRA Projects config xml files present "
                     "within conf directory")
        args.config = [os.path.join(conf_base, file)
                       for file in os.listdir(conf_base) if file.endswith('.xml')]
    else:
        logger.debug("script has been run for {} JIRA Project XML config file "
                     "using --config option".format(args.config))
        args.config = [os.path.join(conf_base, args.config)]

    # DIRTY HACK: If email method gmail api then add script argparse as parent
    # for gmail api argprase while grabbing temporary access credentials via run_flow()
    if args.email_method == "GMAIL_API":
        logger.debug("--email_method option is set to GMAIL_API so manually setting "
                     "script argparse as parent of gmail run_flow argparse object")
        from oauth2client import tools
        tools.argparser._add_container_actions(parser)
    logger.info("Successfully parsed all script arguments")


def parse_project_configs(args):
    """
    This function parses all the project config XMLs
    and returns ProjectConfig object list

    :param args: arparse object
    :return: [ProjectConfig objects]
    """
    xml_configs = list()
    for xml in args.config:
        try:
            logger.info("Processing {} JIRA Project config xml file..".format(xml))
            project_config = validate_config_file(xml, args.schema)
            if project_config not in xml_configs:
                xml_configs.append(project_config)
            else:
                logger.warning("Skipping {0} JIRA Project config xml file as it has already "
                               "been processed for JIRA Project [{1}] of JIRA server [{2}]"
                               .format(xml, project_config.key, project_config.url))
        except Exception as e:
            logger.error(traceback.format_exc())
            summary['validation'].append(str(e))
    if args.validate:
        logger.warning("Quiting script as it has been run with "
                       "--validate option to validate project XML config files only")
        exit(0)
    else:
        return xml_configs


def publish_html_dsr_report(template, project, user, userlogs, report_path):
    """
    This function generates HTML format DSR report for JIRA user having
    any activities within specified start and end dates

    :param template: (string) path to HTML jinja2 template
    :param project: JIRAProject object
    :param user: (string) JIRA user
    :param userlogs: [WorkLog object list] for JIRA user
    :param report_path: (string) local path to JIRA Project report directory
    :return: (string) path to generated HTML DSR report for JIRA user
    """
    publish_datetime = datetime.now(project.timezone)
    publish_date = publish_datetime.strftime("%d-%b-%Y")
    publish_time = publish_datetime.strftime("%H:%M:%S %Z")
    timezone = publish_datetime.strftime("%Z")
    output_from_parsed_template = template.render(project=project,
                                                  user=user,
                                                  userlogs=userlogs,
                                                  publish_date=publish_date,
                                                  publish_time=publish_time,
                                                  start_date=project.start_date,
                                                  end_date=project.end_date,
                                                  timezone=timezone)
    report = os.path.join(report_path, "{0}_dsr-report-{1}_{2}.html".
                          format(project, user, publish_date))
    with open(report, "w") as f:
        f.write(output_from_parsed_template)
    return report


def publish_csv_dsr_report(project, user, userlogs, report_path):
    """
    This function generates CSV format DSR report for JIRA user having
    any activities within specified start and end dates

    :param project: JIRAProject object
    :param user: (string) JIRA user
    :param userlogs: [WorkLog object list] for JIRA user
    :param report_path: (string) local path to JIRA project report directory
    :return: (string) path to generated CSV DSR report for JIRA user
    """
    headers = ('PUBLISH_DATETIME', 'JIRA-ID', 'TITLE', 'PRIORITY',
               'ASSIGNEE', 'STATUS', 'TRANSITIONS', 'ESTIMATED TIME',
               'TOTAL TIME SPENT', 'WORK USER', 'WORK TIME',
               'WORK LOG', 'COMMENTS')
    publish_datetime = datetime.now(project.timezone)
    publish_date = publish_datetime.strftime("%d-%b-%Y")
    publish_time = publish_datetime.isoformat()
    report = os.path.join(report_path, "{0}_dsr-report-{1}_{2}.csv".
                          format(project, user, publish_date))
    with open(report, "w") as f:
        writer = csv.writer(f)
        writer.writerow(headers)
        for userlog in userlogs:
            writer.writerow([publish_time,
                             userlog.parent,
                             userlog.parent.get_title(),
                             userlog.parent.get_priority(),
                             userlog.parent.get_assignee(),
                             userlog.parent.get_status(),
                             userlog.get_user_issue_state_transitions(),
                             userlog.parent.get_estimated_time(),
                             userlog.parent.get_total_spent_time(),
                             user,
                             userlog.time,
                             userlog.work_log_comments,
                             userlog.get_user_issue_comments()])
    return report


def publish_dsr_report(project, manager, project_user_worklogs, args):
    """
    This function creates DSR report for JIRA user based on its activities on
    issues of JIRA project within specified start and end dates and emails it to
    JIRA user and Project manager

    :param project: ProjectConfig object
    :param manager: manager email address specified in project config xml as attribute
    :param project_user_worklogs: (dict) containing all JIRA users and their correspoding
    WorkLog object list
    :param args: Argparse object
    :return: None
    """
    for user, userlogs in project_user_worklogs.items():
        logger.info("Generating DSR Report for user [{0}] "
                    "on JIRA Project [{1}]".format(user, project.name))
        publish_date = datetime.now(project.timezone).strftime("%d-%b-%Y")
        report_path = os.path.join(args.base_path, "reports", project.name, publish_date)
        os.makedirs(report_path, exist_ok=True)
        if args.report == "HTML":
            logger.debug("Creating HTML DSR Report for user [{0}]".format(user))
            report = publish_html_dsr_report(args.template, project, user, userlogs, report_path)
        if args.report == "CSV":
            logger.debug("Creating CSV DSR Report for user [{0}]".format(user))
            report = publish_csv_dsr_report(project, user, userlogs, report_path)
        with open(report, "r") as f:
            message = f.read()
        attachment = report if args.attach else None
        user_email = 'ashish.kumar@forgeahead.io'
        subject = "{0} DSR Report {1} | {2}".format(project, publish_date, user)
        logger.info("Sending DSR Report for user [{0}] for JIRA Project [{1}] "
                    "to email address: [{2}]".format(user, project.name, user_email))
        DSRUtil.send_email(subject, user_email, manager, message, attachment, args)


def publish_no_worklog_report(project, manager, args):
    """
    This function sends a no DSR report email to Project Manager
    if there are activities at all from any JIRA user on any issues
    of JIRA project within specified start and end dates

    :param project: ProjectConfig object
    :param manager: manager email address specified in project config xml as attribute
    :param args: Argparse object
    :return: None
    """
    publish_datetime = datetime.now(project.timezone)
    publish_date = publish_datetime.strftime("%d-%b-%Y")
    timezone = publish_datetime.strftime("%Z")
    subject = "No DSR Report for {0} on {1} ".format(project, publish_date)
    message = "<b>There is no worklog activity present on JIRA Project: [{0}] " \
              "for DSR report between dates [{1} {3}] - [{2} {3}]</b>" \
        .format(project, args.start_date, args.end_date, timezone)
    logger.info("Sending no worklog email report for project [{0}] to "
                "manager [{1}]".format(project.name, manager))
    DSRUtil.send_email(subject, manager, manager, message, None, args)


def generate_jira_project_report(project_config, args):
    """
    This function takes ProjectConfig object of JIRA project xml file
    and generates DSR report

    :param project_config: ProjectConfig object
    :param args: Argparse object
    :return: None
    """
    __NO_REPORT_FLAG = False
    project = JIRAProject(project_config, args.start_date, args.end_date)
    logger.info("Processing DSR reports for JIRA project [{0}] of JIRA server [{1}] "
                "for following start and end date ranges [{2}] - [{3}]".
                format(project, project.config.url, args.start_date, args.end_date))
    manager = project.config.manager
    project_user_worklogs = dict()
    logger.debug("Fetching all JIRA issues for Project [{0}] which have any "
                 "activities within specified start and end dates [{1}] [{2}]"
                 .format(project.name, args.start_date, args.end_date))
    issues = project.get_project_issues()
    if issues:
        for issue in issues:
            logger.debug("Fetching user worklog details for JIRA Issue [{0}] "
                         "which have any user activities within specified start "
                         "and end dates [{1}] [{2}]".format(issue.key, args.start_date,
                                                            args.end_date))
            for worklog_user, worklog in issue.get_work_logs().items():
                if worklog_user not in project_user_worklogs:
                    project_user_worklogs[worklog_user] = [worklog]
                else:
                    project_user_worklogs[worklog_user].append(worklog)
        if project_user_worklogs:
            publish_dsr_report(project, manager,
                               project_user_worklogs, args)
            summary['success'].append(project.config.key)
        else:
            __NO_REPORT_FLAG = True
    else:
        __NO_REPORT_FLAG = True
    if __NO_REPORT_FLAG:
        summary['noreport'].append(project.config.key)
        logger.warning("No Issues have any activity in JIRA Project [{0}] "
                       "for following date ranges [{1} {3}] - [{2} {3}]"
                       .format(project, args.start_date, args.end_date,
                               project.config.timezone))
        publish_no_worklog_report(project, manager, args)
    logger.info("Finished processing DSR reports for JIRA project [{0}] "
                "of JIRA server [{1}] for following start and end date "
                "ranges [{2}] - [{3}]".format(project, project.config.url,
                                              args.start_date, args.end_date))


def generate_run_summary(args):
    """
    This function sends an email to email address passed
    via --summary option which includes details about following:
    1. Name of JIRA projects which have been successfully, failed or have no DSR report
    2. Script log as attachement generated in script execution.

    :param args: Argparse object
    :return: None
    """
    logger.info("Generating Script run summary report...")
    run_date = datetime.now().strftime("%d-%b-%Y")
    subject = "JIRA DSR Report | Daily Run Summary Report | {}".format(run_date)
    to = cc = args.summary
    body = "<h3>Report date range: [{0}] - [{1}]</h3>".format(args.start_date, args.end_date)

    def create_list(section, values):
        if values:
            content = "<ul><h4>{}:</h4>".format(section)
            for item in values:
                content += "<li>{}</li>".format(item)
            content += "</ul>"
            return content
        else:
            return ""

    body += create_list("XML config schema or value validation failed for projects",
                        summary['validation'])
    body += create_list("Reports successfully generated for projects",
                        summary['success'])
    body += create_list("No Reports available for projects",
                        summary['noreport'])
    body += create_list("Reports generation failed for projects",
                        summary['failed'])
    body += "<b>Attachment is the log file generated for this run.</b>"
    logger.info("Sending Script run summary report over email to address: {}".format(to))
    DSRUtil.send_email(subject, to, cc, body, logger.get_logfile(), args)


def main():
    """
    Script execution starts from here
    :return: None
    """
    start_time = time.time()
    args = parser.parse_args()
    log_dir = os.path.join(args.base_path, "logs")
    log_file = 'JIRA_DSR_Report_{}.log'.format(datetime.now().strftime('%Y-%m-%d_%H%M%S'))
    global logger
    logger = InteractiveLogger(log_dir, log_file,
                               verbose=args.verbose, interactive=args.interactive)
    parse_arguments(args)
    try:
        project_configs = parse_project_configs(args)
        for project_config in project_configs:
            try:
                generate_jira_project_report(project_config, args)
            except Exception:
                summary['failed'].append(project_config.key)
                logger.error(traceback.format_exc())
    finally:
        if args.summary:
            generate_run_summary(args)
        FSUtil.rotate_files(args.base_path, file_pattern="reports/**/**/*")
        FSUtil.rotate_files(log_dir, file_pattern="*.log")
        logger.info("Total time script took to finish: {} "
                    "seconds!".format(math.floor(time.time()-start_time)))


if __name__ == "__main__":
    main()
