#!/bin/bash
# Environment Variables:
# - VMID=VM id (set through podman -e VMID=<id>)
# - TARGETNODE=ProxMox node hosting the VM (set through podman -e TARGETNODE=<node>)
# - BMC_ENDPOINT=BMC IP address assigned to the VM
# - BMC_USERNAME=ProxMox API access username
# - BMC_PASSWORD=ProxMox API access password

# Retrieve Cookie
COOKIE=$(curl --silent --insecure --data "username=${BMC_USERNAME}&password=${BMC_PASSWORD}" \
        https://${BMC_ENDPOINT}:8006/api2/json/access/ticket | jq --raw-output '.data.ticket' | sed 's/^/PVEAuthCookie=/')

# Retrieve CSRF Token
CSRFTOKEN=$(curl --silent --insecure --data "username=${BMC_USERNAME}&password=${BMC_PASSWORD}" \
        https://${BMC_ENDPOINT}:8006/api2/json/access/ticket | jq --raw-output '.data.CSRFPreventionToken' | sed 's/^/CSRFPreventionToken:/')

ISO=${1}
NAME=${VMID}-$(basename ${ISO})

# Unmount CD on VM
curl --silent --insecure  --cookie "${COOKIE}" --header "${CSRFTOKEN}" -X POST \
        --data-urlencode ide2="none" \
        https://${BMC_ENDPOINT}:8006/api2/json/nodes/${TARGETNODE}/qemu/${VMID}/config
if [ $? -ne 0 ]; then
        exit 1
fi

# Delete existing ISO if it exists
TASK=$(curl --silent --insecure --cookie "${COOKIE}" --header "${CSRFTOKEN}" -X DELETE \
        https://${BMC_ENDPOINT}:8006/api2/json/nodes/${TARGETNODE}/storage/sda4/content/sda4\:iso\/${NAME} | jq --raw-output '.data')
if [ "${TASK}" != "" ]; then
        STATUS="OK"
        while true; do
                STATUS=$(curl --insecure --cookie "${COOKIE}" --header "${CSRFTOKEN}" \
                        https://${BMC_ENDPOINT}:8006/api2/json/nodes/${TARGETNODE}/tasks/${TASK}/status | jq --raw-output '.data.exitstatus')
                [ "${STATUS}" == "null" ] || break
                sleep 2
        done
        [ "${STATUS}" == "OK" ] || exit 1
else
        exit 1
fi

# Copy ISO to ProxMox
TASK=$(curl --silent --insecure --cookie "${COOKIE}" --header "${CSRFTOKEN}" -X POST \
        --data-urlencode content="iso" \
        --data-urlencode filename="${NAME}" \
        --data-urlencode url="${ISO}" \
        --data-urlencode verify-certificates=0 \
        https://${BMC_ENDPOINT}:8006/api2/json/nodes/${TARGETNODE}/storage/sda4/download-url | jq --raw-output '.data')
if [ "${TASK}" != "" ]; then
        STATUS="OK"
        while true; do
                STATUS=$(curl --insecure --cookie "${COOKIE}" --header "${CSRFTOKEN}" \
                        https://${BMC_ENDPOINT}:8006/api2/json/nodes/${TARGETNODE}/tasks/${TASK}/status | jq --raw-output '.data.exitstatus')
                [ "${STATUS}" == "null" ] || break
                sleep 2
        done
        [ "${STATUS}" == "OK" ] || exit 1
else
        exit 1
fi

# Mount CD on VM
curl --silent --insecure  --cookie "${COOKIE}" --header "${CSRFTOKEN}" -X POST \
        --data-urlencode ide2="sda4:iso/${NAME},media=cdrom" \
        https://${BMC_ENDPOINT}:8006/api2/json/nodes/${TARGETNODE}/qemu/${VMID}/config
if [ $? -ne 0 ]; then
        exit 1
fi
exit 0
