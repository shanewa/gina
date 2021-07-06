# Called by crontab
# 0 0 * * * /root/gina/src/cron.sh

GINA_LOG_DIR=/var/gina/log
GINA_RUN=/root/gina/run.sh

[[ ! -d ${GINA_LOG_DIR} ]] && mkdir -p ${GINA_LOG_DIR}
${GINA_RUN} > ${GINA_LOG_DIR}/gina_$(date '+%Y%m%d_%H%M%S').log 2>&1
