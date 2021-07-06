# Update the database in bundles
set -x

GINA_SETUP_DB=/root/gina/src/setup_db.py
GINA_CNFG=/root/gina/cnfg
GINA_INI_DEV=/root/gina/src/init_dev_info.py

# Generate the developers information
# python ${GINA_INI_DEV} -c ${GINA_CNFG}/git_boostorg_boost.json

# Generate the git database
python ${GINA_SETUP_DB} -c ${GINA_CNFG}/git_boostorg_boost.json
