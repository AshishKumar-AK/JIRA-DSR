## Synopsis

Python3 script to generate daily status reports for JIRA projects using JIRA REST API.

## Motivation

All our software projects are using Atlassian JIRA platform for their project management and development tracking efforts.
Project Managers of those projects needed a simple solution where they can get daily status report about any work or activities being done by team members on their respective JIRA projects.

The information they required in these daily status report of JIRA projects were followings:
- Each team member, working on a JIRA project should receive their daily status report over email which will contain details about any worklogs or activities (issue commit/resolve/fixed/comment) being performed by them on JIRA issues of that project.
- These individual team member reports should also be emailed to project Manager's email address of that JIRA project.
- If there are no user worklogs or activities done on JIRA issues of that project on any particular day then a no worklog report should be emailed only to that Project manager's email address.

The reason I open sourced this home grown solution, thinking may be someone out there might have similar requirement to get a daily status reports about work and activities being performed on any JIRA projects and can make use of this small implementaion.

## Requirements

- Python3
- for additional pip modules used by script check [requirements.txt](requirements.txt)
- REST API is enabled on JIRA servers where JIRA projects are present.

## Installation

Download this script into a directory from where it should be run by simply copying it.

```user@~$ git clone https://github.com/AshishKumar-AK/JIRA-DSR.git```

OR by running in a separate virtualenv

```
user@~$ pip3 install virtualenv
user@~$ cd my_project_folder
user@my_project_folder$ virtualenv -p $(which python3) venv
user@my_project_folder$ git clone https://github.com/AshishKumar-AK/JIRA-DSR.git
user@my_project_folder$ source venv/bin/activate
user@my_project_folder(venv)$ pip3 install -r JIRA-DSR/requirements.txt
```

Check if now script can be run successfully

```user@JIRA-DSR(venv)$ python3 JIRA_DSR.py --help```

## Script Setup

Before understanding inner details of script functionality and its working, we should first understand about script components and its configuration setup.

- [JIRA_DSR.py](JIRA_DSR.py): This is main python3 script which generates JIRA DSR reports.
- [conf](conf): The "conf" directory contains following items which are required for script execution:


Per JIRA Project XML configuration file which contains details about JIRA server URL where JIRA Project is present, JIRA Project Key, jira user credentials and details to a source code review system (Fisheye or stash) as well if project is having a development code base associated. There is an example JIRA Project template conf file is present under conf directory by name [JIRA-Project-config-template.xml](conf/JIRA-Project-config-template.xml) which contains further details about these values.


[schema.xsd](conf/schema.xsd) file which is being used by script to validate xml structure of these per project JIRA XML files.


[client_secret_gmail_api.json](conf/client_secret_gmail_api.json) file which is a sample GMAIL API JSON config file required by script if you want to send DSR report emails using GMAIL API. For more information about how to obtain this config file for GMAIL account which you want to use to send emails from this script, [check this setup guide](https://developers.google.com/gmail/api/quickstart/python#step_3_set_up_the_sample). Once you have this config json file for your google account, just place it under "conf/" directory with same name.

- [lib](lib): The "lib" directory contains some custom python3 utility classes which are being used by this script for sending emails, logging and performing few file system operations.
- [template](template): The "template" directory contains a jinja2 html template file [JIRA-DSR-template.html](JIRA-DSR-template.html) which is used by script to populate each project members DSR report details and send it to that member over email as HTML content. If you want to customize or modify the layout of this HTML template, you can edit this existing file or replace its content with a new one.

####Now the usual flow of script usage is following:
1. First you need to create a JIRA project's config XML file under "conf/" directory in order to have its daily status report generated. The details about how to create a JIRA project XML file, please check and read the comments and instructions in example template file [JIRA-Project-config-template.xml](conf/JIRA-Project-config-template.xml). You can add as many JIRA project config xml files under conf directory for as many JIRA projects daily status reporting you want. Just one important note to add here, JIRA projects are identified uniquely by their <em>Project KEY + JIRA SERVER URL</em> value from Project config files. This reduces the chance of same JIRA project's duplicate config XML file being processed multiple times. If script finds any duplicate JIRA project config definition in multiple files, it will only process it once and will skip rest of those duplicate config files and generate a warning log about those skipped files. A Project config XML file can have configuration details for only one JIRA project. 
2. Once you have a JIRA project's config xml created, you can also validate the config xml file to check whether it has correct XML schema structure against and also has correct values which can be successfully used by script to generate DSR report by following script arguments:


 ```user@JIRA-DSR(venv)$ python3 JIRA_DSR.py --config="ONLY NAME OF THE JIRA PROJECT CONFIG UNDER CONF DIRECTORY" --validate --interactive```
 
 
 If there are any issues with project's config xml file, it will print for errors on screen.
3. Now to generate the DSR report only for this project, run following:


 ```user@JIRA-DSR(venv)$ python3 JIRA_DSR.py --config="ONLY NAME OF THE JIRA PROJECT CONFIG UNDER CONF DIRECTORY"```


 And this will generate DSR report with date range of yesterday's date and email them to project members and project managers email addresses.
 
4. When running this script without <em>"--config"</em> option, will cause script to process all JIRA projects config xml files present under "conf/" directory and generate DSR reports for each of them.

## Script Usage

Although script available options and arguments are pretty much self explanatory itself when run with <em>-h/--help</em> option:
```
user@JIRA-DSR(venv)$ python3 JIRA_DSR.py --help
usage: JIRA_DSR.py [-h] [--attach] [--base_path BASE_PATH] [--config CONFIG]
                   [--email_method {SMTP,GMAIL_API}]
                   [--gmail_config GMAIL_CONFIG] [--interactive]
                   [--schema SCHEMA] [--report {HTML,CSV}]
                   [--smtp_server SMTP_SERVER] [--smtp_port SMTP_PORT]
                   [--smtp_user SMTP_USER] [--smtp_passwd SMTP_PASSWD]
                   [--smtp_tls] [--ssl_silent] [--start_date START_DATE]
                   [--end_date END_DATE] [--template TEMPLATE] [--validate]
                   [--verbose] [--summary SUMMARY]

-----------------------------------------------------------------------------
The purpose of this script is generate Daily status report of JIRA Projects.
For detailed information check README.md file
-----------------------------------------------------------------------------

optional arguments:
  -h, --help            show this help message and exit
  --attach              Send generated DSR Report as attachment as well in report email
  --base_path BASE_PATH
                        Relative base path ($base_path) to find all config,
                        schema and template files and generate reports and
                        logs [DEFAULT: current working directory]
  --config CONFIG       Name of JIRA Project config XML file present under conf
                        directory for which DSR report should be generated
  --email_method {SMTP,GMAIL_API}
                        Sending email using SMTP or GMAIL API method 
                        [DEFAULT: SMTP]
  --gmail_config GMAIL_CONFIG
                        Name of the json config file present under conf directory which
                        contains OAuth credentials for gmail account 
                        [DEFAULT: ${base_path}/conf/client_secret_gmail_api.json]
  --interactive         Produce logs on standard output as well 
                        [DEFAULT: False]
  --schema SCHEMA       XSD schema validation file name present under conf
                        directory to validate JIRA project's config xml file
                        structure
                        [DEFAULT: ${base_path}/conf/schema.xsd]
  --report {HTML,CSV}   In which format the DSR report should be generated
                        [DEFAULT: HTML]
  --smtp_server SMTP_SERVER
                        [DEFAULT: localhost]
  --smtp_port SMTP_PORT
                        [DEFAULT: 25]
  --smtp_user SMTP_USER
  --smtp_passwd SMTP_PASSWD
  --smtp_tls            [DEFAULT: False]
  --ssl_silent          Suppress SSL certificate warnings about https URLs for
                        those JIRA server which do not have valid SSL
                        certificate
  --start_date START_DATE
                        format YYYY-MM-DD HH:MM [DEFAULT: yesterday's date]
  --end_date END_DATE   
                        format YYYY-MM-DD HH:MM [DEFAULT: yesterday's date]
  --template TEMPLATE   Name of the jinja2 HTML template file present under
                        conf directory which will be used to generate HTML DSR
                        reports
                        [DEFAULT: ${base_path}/template/JIRA-DSR-template.html]
  --validate            Validate JIRA config xml file against XSD schema and
                        also check for correct JIRA project config values
  --verbose             enable debug level log output 
                        [DEFAULT: False]
  --summary SUMMARY     email address to send report run summary of script with
                        script execution log as attachment
```

#####But I will explain few really useful and important options in sections here:

- <em><b>--start_date and --end_date</b></em>: These arguments causes script to generate DSR report for JIRA projects within specified date and time
- <em><b>--validate</b></em>: When passed, this argument will cause script to only run schema validation and value checks on JIRA projects config XML file.
- <em><b>--config</b></em>: This arguments tells DSR script to process and perform operations only for a single JIRA project whose config xml file name is passed as value to this option. The file should be present under conf directory for this option to pick it.
- <em><b>--email_method</b></em>: This option is enables DSR script whether to send DSR report emails using SMTP method and SMTP credential values passed via <em>--smtp_*</em> options or by using google GMAIL API where in this case [client_secret_gmail_api.json](conf/client_secret_gmail_api.json) file should be filled with correct google account GMAIL OAUTH API credential values.
- <em><b>--summary</b></em>: This option causes DSR script to also send an summary email to email address passed as value to this option. The summary report will contain information about:
 list of JIRA projects whose config xml validation and value check failed.
 list of JIRA projects which have been successfully processed for their DSR reports.
 list of JIRA projects had no DSR report generated.
 list of JIRA projects which failed while generating their DSR reports.
 Script execution log as attachment.

## Script Example

- Run this script from a scheduled task or cron job each night or once in a day to get daily status report about work or activities being done yesterday on all configured JIRA projects:
 
 ```python3 JIRA_DSR.py --email_method="GMAIL_API" --summary="adminORreporter@example.com"```

- To manually generate report for any specific project for specific datetime range:
 
 ```python3 JIRA_DSR.py --email_method="GMAIL_API" --config="JIRA_PROJECT.xml" --start_date="2016-04-11 00:00" --end_date="2016-04-12 00:00"```
 
- To generate DSR report for a JIRA project in CSV format and send this report as attachment as well in email:

 ```python3 JIRA_DSR.py --email_method="GMAIL_API" --config="JIRA_PROJECT.xml" --report="CSV" --attach```

## TODOs:

- Take a TDD approach and write unit test cases for script in further development.
- Integrate with Source code review systems FishEye/Stash to get issue commit IDs link from there.
- Fix base64 encoding issue when DSR report is also sent as email attachment.
- Use Travis CI for continuous integration and generating pip packages. 

## Contributors

Contributions are always welcome!
Please read the [contribution guidelines](contributing.md) first.

## License

Licensed under the Apache License, Version 2.0 (the "License")
