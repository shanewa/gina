# -*- coding: utf-8 -*-
import sys
import os
import re
import traceback
import time
import json
import logging
from optparse import OptionParser
import commands
import sqlite3
reload(sys)
sys.setdefaultencoding('utf8')

def parseOpt():
    parser = OptionParser()
    parser.add_option("--configuration", "-c", dest="configuration", default="",
            help="The json file of the configurations.")
    parser.add_option("--no_pull", dest="no_pull", action="store_true", default=False,
            help="Do not pull code.")
    parser.add_option("--debug", "-d", dest="debug", default=30,
            help="e.g. 50 (FATAL), 40 (ERROR), 30 (WARN), 20 (INFO), 10 (DEBUG), 0 (NOTSET)")    
    (options, args) = parser.parse_args()
    configurations = {}
    if options.configuration:
        with open(options.configuration, 'rb') as f:
            configurations = json.load(f)
    if not configurations:
        print("No configuration data!")
        sys.exit(1)
    return options, configurations

def db_handle_execute(cmd):
    if cmd.startswith("CREATE"): logging.debug(cmd)
    try:
        db_handle.execute(cmd)
    except Exception as e:
        for line in traceback.format_stack():
            print(line.strip())
        print(e)
        print("ERROR: " + cmd)
        sys.exit(4)

def populate_developers_teams():
    # Create table developers
    cmd = "CREATE TABLE IF NOT EXISTS developers (dev_id INTEGER PRIMARY KEY AUTOINCREMENT,"
    cmd += " mail VARCHAR(64) NOT NULL,"
    cmd += " team VARCHAR(64) NOT NULL)"
    db_handle_execute(cmd)
    db.commit()
    # Populate the developers infomation
    with open(configurations["dev"], 'rb') as f:
        for dev in json.load(f):
            cmd = "INSERT INTO developers (mail, team) VALUES (\"{0}\", \"{1}\")".format(dev["mail"], dev["team"])
            db_handle_execute(cmd)
    db.commit()

def populate_languages_extensions():
    programming_languages_extensions = {}
    dirname, filename = os.path.split(os.path.abspath(__file__))
    ple_json = dirname + "/programming_languages_extensions.json"
    with open(ple_json, 'rb') as f:
        programming_languages_extensions = json.load(f)
    cmd = "CREATE TABLE IF NOT EXISTS languages (language_id INTEGER PRIMARY KEY AUTOINCREMENT,"
    cmd += " name VARCHAR(32) NOT NULL)"
    db_handle_execute(cmd)
    cmd = "CREATE TABLE IF NOT EXISTS extensions (extension_id INTEGER PRIMARY KEY AUTOINCREMENT,"
    cmd += " language_id INTEGER NOT NULL,"
    cmd += " extension VARCHAR(20) NOT NULL)"   
    db_handle_execute(cmd)
    cmd = "INSERT INTO languages (language_id, name) VALUES (-1, \"Unknown\")"
    db_handle_execute(cmd)
    db.commit()
    for lang in programming_languages_extensions:
        cmd = "INSERT INTO languages (name) VALUES (\"{0}\")".format(lang["name"])
        db_handle_execute(cmd)
        for ext in lang["extensions"]:
            cmd = "INSERT INTO extensions (language_id, extension) VALUES ((SELECT language_id FROM languages WHERE name = \"{0}\"), \"{1}\")".format(lang["name"], ext)
            db_handle_execute(cmd)
    db_handle_execute(cmd)
    db.commit()

def pull_changes(configurations, no_pull=False):
    if no_pull:
        logging.debug("User doesn't want to pull code.")
        return
    if not os.path.exists(configurations["home"]):
        os.makedirs(configurations["home"], 0755)
    branch_path = os.path.join(configurations["home"], configurations["repo_local_name"])
    if not os.path.exists(branch_path):
        logging.info("Cloning for " + configurations["repo_address"])
        cmd = "export GIT_SSH_COMMAND=\"ssh -o StrictHostKeyChecking=no\"; cd {0} && git clone {1} {2} 2>&1".format(configurations["home"], configurations["repo_address"], configurations["repo_local_name"])
        logging.info(cmd)
        (status, result) = commands.getstatusoutput(cmd)
        logging.debug(result)
        if status != 0:
            logging.error("Git clone failed! (status={0})".format(status))
            sys.exit(3)
        else:
            logging.info("Git clone successfully!")
    else:
        logging.info("Pull changes for " + configurations["repo_address"])
        cmd = "cd {0} && git pull --rebase 2>&1".format(branch_path)
        logging.info(cmd)
        (status, result) = commands.getstatusoutput(cmd)
        logging.debug(result)
        if status != 0:
            logging.error("Git pull failed! (status={0})".format(status))
            sys.exit(3)
        else:
            logging.info("Git pull successfully!")

def format_email(email):
    formatted_email = email
    m = re.match(r'.*(\b[\w.%+-]+@[\w.%+-]+\b).*', email)
    if m is not None:
        formatted_email = m.group(1)
    else:
        formatted_email = re.sub(r'[^@\w.%+-]', "_", email)
        logging.warning("Invalid mail: {0}. Converted to: {1}.".format(email, formatted_email))
    return formatted_email

def create_audit_trigger(mytable):
    # Create audit table
    cmd = "CREATE TABLE IF NOT EXISTS audit (audit_id INTEGER PRIMARY KEY AUTOINCREMENT, entry_date TEXT NOT NULL)"
    db_handle_execute(cmd)
    # Create audit_log trigger
    cmd = "CREATE TRIGGER audit_log AFTER INSERT on {0} ".format(mytable)
    cmd += "BEGIN INSERT INTO AUDIT(entry_date) VALUES (datetime(\"now\")); END"
    db_handle_execute(cmd)
    db.commit()

def create_repo():
    # Create audit table
    cmd = "CREATE TABLE IF NOT EXISTS repo (repo_id INTEGER PRIMARY KEY AUTOINCREMENT,"
    cmd += " address VARCHAR(64) NOT NULL)"
    db_handle_execute(cmd)
    # Save repo info
    cmd = "INSERT INTO repo (address) VALUES (\"{0}\")".format(configurations["repo_address"])
    db_handle_execute(cmd)
    db.commit()

def populate_subsys():
    # Create subsys table
    cmd = "CREATE TABLE IF NOT EXISTS subsys (ss_id INTEGER PRIMARY KEY AUTOINCREMENT,"
    cmd += " subsys VARCHAR(8) NOT NULL)"  
    db_handle_execute(cmd)
    cmd = "INSERT INTO subsys (ss_id, subsys) VALUES (-1, \"Unknown\")"
    db_handle_execute(cmd)
    db.commit()
    # Populate the data
    for ss in configurations["subsys"]:
        cmd = "INSERT INTO subsys (subsys) VALUES (\"{0}\")".format(ss)   
        db_handle_execute(cmd)
    db.commit()

def retry_cmd(cmd, debug=True):
    if debug: logging.debug(cmd)
    max_retry_times = 3
    while max_retry_times:
        max_retry_times -= 1
        (status, result) = commands.getstatusoutput(cmd)
        if status == 0:
            break
        else:
            time.sleep(0.5)
    if status != 0:
        logging.error("Failed shell command: \"{0}\", with code = {1}".format(cmd, status))
    return result.split('\n')

def populate_files(files, sha):
    # Traverse all files
    for file_change in files:
        extension = "Unknown"
        if re.search(r'.+\..+', file_change["file"]) is not None:
            extension = "." + file_change["file"].split(".")[-1]
        subsys = "Unknown"
        for fd in file_change["file"].split("/"):
            if re.match(r'\.+', fd) is not None: continue
            subsys = fd
            break          
        if subsys not in configurations["subsys"]:
            subsys = "Unknown"
        # Query the language id
        language_id = -1 

        cmd = "SELECT language_id FROM extensions WHERE extension = \"{0}\" COLLATE NOCASE".format(extension)
        db_handle_execute(cmd)
        result = db_handle.fetchall()
        if not len(result):
            logging.warning("{0} for {1} is not a valid extention. Set it as -1.".format(extension, file_change["file"]))
        else:
            language_id = result[0][0]
        cmd = "INSERT INTO files (commit_id, language_id, path, ss_id, add_lines, delete_lines) VALUES ("
        cmd += "(SELECT commit_id FROM commits WHERE sha = \"{0}\"), ".format(sha)
        cmd += "{0}, ".format(language_id)
        cmd += "\"{0}\", ".format(file_change["file"])
        cmd += "(SELECT ss_id FROM subsys WHERE subsys = \"{0}\"), ".format(subsys)
        cmd += "{0}, ".format(file_change["add"])
        cmd += "{0})".format(file_change["subtract"])
        db_handle_execute(cmd)
    db.commit()

def get_remotes_branch_heads():
    heads = {}
    cmd = "cd {0} && git branch -v --all".format(os.path.join(configurations["home"], configurations["repo_local_name"]))
    result = retry_cmd(cmd)
    for line in result:
        m = re.match(r'\s*remotes/origin/(\S+)\s+(\S+)\s+.+', line)
        if m is not None:
            heads[m.group(1)] = m.group(2)
    logging.debug(heads)
    return heads

def populate_view(a_view):
    logging.info("Populating view: ")
    logging.info(a_view)
    is_invalid_view = False
    # Check the necessary fields must be included in a view dict.
    if "view_name" not in a_view or "from_commit" not in a_view or "to_commit" not in a_view:
        logging.error("Invalid view: missing necessary fields!")
        is_invalid_view = True
    # Get the head SHA if needed.
    elif a_view["to_commit"] == "HEAD":
        if "branch" not in a_view or not a_view["branch"]:
            logging.error("Must provide branch name for HEAD!")
            is_invalid_view = True
        else:
            head_sha = heads[a_view["branch"]]
            if not head_sha:
                logging.error("Cannot get the SHA of the HEAD of branch {0}!".format(a_view["branch"]))
                is_invalid_view = True
            else:
                a_view["to_commit"] = head_sha
                logging.info("Reset the to_commit from HEAD to {0} for view {1}.".format(head_sha, a_view["view_name"]))
    if is_invalid_view: return
    # Save this view
    cmd = "INSERT INTO views (view_name, from_commit, to_commit) VALUES (\"{0}\", \"{1}\", \"{2}\")".format(a_view["view_name"], a_view["from_commit"], a_view["to_commit"])
    db_handle_execute(cmd)
    # Traverse all commits in this view including merges (without option --no-merges)
    cmd = "cd {0} && git log {1}..{2} --numstat --pretty=\"%ae__@@__%H__@@__%s__@@__%cI\"".format(os.path.join(configurations["home"], configurations["repo_local_name"]), a_view["from_commit"], a_view["to_commit"])
    result = retry_cmd(cmd)
    files = []
    file_change = {"add": "0", "subtract": "0", "file": ""}
    mail = ""
    sha = ""
    summary = ""
    hook = ""
    commit_date = ""
    def save_commit_info():
        if mail and sha and summary and hook and commit_date:
            # Save commit
            cmd = "INSERT INTO commits (sha, summary, hook, dev_id, commit_date) VALUES ("
            cmd += "\"{0}\", ".format(sha)
            cmd += "\"{0}\", ".format(summary)
            cmd += "\"{0}\", ".format(hook)
            cmd += "(SELECT dev_id FROM developers WHERE mail = \"{0}\" COLLATE NOCASE), ".format(mail)
            cmd += "\"{0}\")".format(commit_date)
            db_handle_execute(cmd)
            populate_files(files, sha)
            # Save mapping
            cmd = "INSERT INTO mappings (view_id, commit_id) VALUES ("
            cmd += "(SELECT view_id FROM views WHERE view_name = \"{0}\"), ".format(a_view["view_name"])
            cmd += "(SELECT commit_id FROM commits WHERE sha = \"{0}\"))".format(sha)
            db_handle_execute(cmd)
    for line in result:
        line = line.strip()
        if not line: continue
        # m = re.match(r'(.+)__@@__(.+)__@@__\s*(Revert \"|Merge \"|)(\w+-\d+)\s*:\s*(.+)', line)
        m = re.match(r'(.+)__@@__(.+)__@@__(.+)__@@__(\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}).+', line)
        if m is not None:
            # Save the previous commit info
            save_commit_info()
            sha = m.group(2)
            mail = format_email(m.group(1).lower())
            hooks = re.findall(r'\"?(\w+-\d+)\s*:\s*', m.group(3))
            if not len(hooks):
                # logging.warning("Cannot parse hook from commit {0} - {1}".format(sha, m.group(3)))
                # sys.exit(5)
                hooks.append("Unknown")
            hook = hooks[0]
            summary = re.sub(hook + "\s*:\s*", "", m.group(3))
            summary = re.sub("[\"\']", "", summary)
            # commit date format: e.g. 2021-05-17T13:56:08+03:00
            # grafana date format: e.g. 2021-05-17T00:00:00Z
            commit_date = m.group(4) + "Z"
            files = []
        else:
            m = re.match(r'(\d+)\s+(\d+)\s+(.+)', line)
            if m is not None:
                file_change = {"add": "0", "subtract": "0", "file": ""}
                file_change["add"] = m.group(1)
                file_change["subtract"] = m.group(2)
                file_change["file"] = m.group(3)
                files.append(file_change)
            else:
                logging.exception("Cannot handle this line: " + line)
    # Save the last commit info
    save_commit_info()
    db.commit()
    
def populate_commmits_views_mappings():
    # Create commits table
    cmd = "CREATE TABLE IF NOT EXISTS commits (commit_id INTEGER PRIMARY KEY AUTOINCREMENT,"
    cmd += " sha VARCHAR(40) NOT NULL,"
    cmd += " summary VARCHAR(75) NOT NULL,"
    cmd += " hook VARCHAR(20) NOT NULL,"
    cmd += " dev_id INTEGER NOT NULL,"
    cmd += " commit_date VARCHAR(20) NOT NULL)"
    db_handle_execute(cmd)
    # Create files table
    cmd = "CREATE TABLE IF NOT EXISTS files (file_id INTEGER PRIMARY KEY AUTOINCREMENT,"
    cmd += " commit_id INTEGER NOT NULL,"
    cmd += " language_id INTEGER NOT NULL,"
    cmd += " path VARCHAR(256) NOT NULL,"
    cmd += " ss_id INTEGER NOT NULL,"
    cmd += " add_lines INTEGER NOT NULL,"
    cmd += " delete_lines INTEGER NOT NULL)"
    db_handle_execute(cmd)
    db.commit()
    # Create views table
    cmd = "CREATE TABLE IF NOT EXISTS views (view_id INTEGER PRIMARY KEY AUTOINCREMENT,"
    cmd += " view_name VARCHAR(75) NOT NULL,"
    cmd += " from_commit VARCHAR(75) NOT NULL,"
    cmd += " to_commit VARCHAR(75) NOT NULL)"
    db_handle_execute(cmd)
    db.commit()
    # Create audit trigger
    create_audit_trigger("views")
    # Create mappings table
    cmd = "CREATE TABLE IF NOT EXISTS mappings (mapping_id INTEGER PRIMARY KEY AUTOINCREMENT,"
    cmd += " view_id INTEGER NOT NULL,"
    cmd += " commit_id INTEGER NOT NULL)"
    db_handle_execute(cmd)
    db.commit()
    # Peocess all views
    for a_view in configurations["views"]:
        populate_view(a_view)

def populate_focus():
    if "focus" not in configurations or not len(configurations["focus"]):
        logging.debug("No Focus specified.")
        return
    for focus_dict in configurations["focus"]:
        # Create a focus table
        table_name = "focus_" + focus_dict["name"]
        cmd = "CREATE TABLE IF NOT EXISTS {0} (focus_id INTEGER PRIMARY KEY AUTOINCREMENT,".format(table_name)
        cmd += " focus_folder VARCHAR(32) NOT NULL,"
        cmd += " focus_path VARCHAR(256) NOT NULL)"
        db_handle_execute(cmd)
        subdirectories = next(os.walk(os.path.join(os.path.join(configurations["home"], configurations["repo_local_name"]), focus_dict['path'])))[1]
        for subd in subdirectories:
            cmd = "INSERT INTO {0} (focus_path, focus_folder) VALUES (\"{1}\", \"{2}\")".format(table_name, os.path.join(focus_dict['path'], subd), subd)
            db_handle_execute(cmd)
    db.commit()

if __name__ == '__main__':
    options, configurations = parseOpt()
    logging.basicConfig(format='%(asctime)s - %(pathname)s[line:%(lineno)d] - %(levelname)s: %(message)s', level=int(options.debug))
    logging.debug(options)
    logging.debug(configurations)
    
    tmp_db = configurations["db"] + ".tmp"
    if os.path.exists(tmp_db): os.remove(tmp_db)
    db = sqlite3.connect(tmp_db)
    db_handle = db.cursor()

    pull_changes(configurations, options.no_pull)
    populate_developers_teams()
    populate_languages_extensions()
    heads = get_remotes_branch_heads()
    populate_subsys()
    populate_commmits_views_mappings()
    populate_focus()
    create_repo()

    db.commit()
    db.close()
    if os.path.exists(configurations["db"]): os.remove(configurations["db"])
    os.rename(tmp_db, configurations["db"])
    logging.info("Successfully get information from {0}.".format(configurations["repo_address"]))
    logging.info("Please check {0}.".format(configurations["db"]))
