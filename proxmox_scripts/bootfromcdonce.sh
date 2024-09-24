#!/bin/bash
# Environment Variables:
# - VMID=VM id (set through podman -e VMID=<id>)
# - TARGETNODE=ProxMox node hosting the VM (set through podman -e TARGETNODE=<node>)
# - BMC_ENDPOINT=BMC IP address assigned to the VM
# - BMC_USERNAME=ProxMox API access username
# - BMC_PASSWORD=ProxMox API access password
# - BOOTSOURCEOVERRIDE_ENABLED={'Disabled'|'Once'|'Continuous'}
# - BOOTSOURCEOVERRIDE_TARGET={'None'|'Cd'|'Hdd'|'Pxe'}
# - BOOTSOURCEOVERRIDE_MODE={'Legacy'|'UEFI'}

# Retrieve Cookie
COOKIE=$(curl --silent --insecure --data "username=${BMC_USERNAME}&password=${BMC_PASSWORD}" \
        https://${BMC_ENDPOINT}:8006/api2/json/access/ticket | jq --raw-output '.data.ticket' | sed 's/^/PVEAuthCookie=/')

# Retrieve CSRF Token
CSRFTOKEN=$(curl --silent --insecure --data "username=${BMC_USERNAME}&password=${BMC_PASSWORD}" \
        https://${BMC_ENDPOINT}:8006/api2/json/access/ticket | jq --raw-output '.data.CSRFPreventionToken' | sed 's/^/CSRFPreventionToken:/')

curl --silent --insecure  --cookie "${COOKIE}" --header "${CSRFTOKEN}" -X POST \
        --data-urlencode boot='order=ide2;scsi0;net1' \
        https://${BMC_ENDPOINT}:8006/api2/json/nodes/${TARGETNODE}/qemu/${VMID}/config
if [ $? -ne 0 ]; then
        exit 1
fi
exit 0
