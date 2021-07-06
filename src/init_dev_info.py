# -*- coding: utf-8 -*-
from setup_db import *

def get_developers_info_from_git():
    cmd = "cd {0} && git log --all --pretty=\"%ae\"".format(os.path.join(configurations["home"], configurations["repo_local_name"]))
    devs_from_git = set([x.lower() for x in retry_cmd(cmd)])
    devs = []
    for dev in devs_from_git:
        devs.append({"mail": format_email(dev), "team": "unavailable"})
    return devs

if __name__ == '__main__':
    options, configurations = parseOpt()
    logging.basicConfig(format='%(asctime)s - %(pathname)s[line:%(lineno)d] - %(levelname)s: %(message)s', level=int(options.debug))
    logging.debug(options)
    logging.debug(configurations)

    pull_changes(configurations, options.no_pull)
    devs = get_developers_info_from_git()

    # Save the data to json file
    with open(configurations["dev"], 'w') as f:        
        f.write(json.dumps(devs, indent=4))

    logging.info("Successfully get information from {0}.".format(configurations["repo_address"]))
    logging.info("Please check {0}.".format(configurations["dev"]))
