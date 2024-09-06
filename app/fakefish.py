#!/usr/bin/env python3
# coding=utf-8

import flask
import json
import os
import requests
import subprocess
import argparse
import base64
import uuid
import random
from datetime import datetime
from requests.packages.urllib3.exceptions import InsecureRequestWarning
requests.packages.urllib3.disable_warnings(InsecureRequestWarning)

app = flask.Flask(__name__)

sessions = {}
bootsourceoverride_enabled = 'Disabled'
bootsourceoverride_target = 'None'
bootsourceoverride_mode = 'UEFI'

@app.route('/redfish/v1/')
def root_resource():
    return flask.render_template('root.json')

@app.route('/redfish/v1/Managers')
def manager_collection_resource():
    return flask.render_template('managers.json')

@app.route('/redfish/v1/SessionService')
def sessionservice_collection_resource():
    return flask.render_template('sessionservice.json')

@app.route('/redfish/v1/SessionService/Sessions', methods=['GET', 'POST'])
def sessions_collection_resource():
    global sessions
    if flask.request.method == 'POST':
        username = flask.request.json.get('UserName')
        password = flask.request.json.get('Password')
        token = f'{random.getrandbits(128):016x}'
        id = username + uuid.uuid4().hex
        sessions[token] = {'id': id, 'decoded_creds': username + ':' + password}
        app.logger.info('Number of sessions: ' + str(len(sessions)))
        app.logger.info('Token: ' + token + ', Data: ' + str(sessions[token]))

        location = flask.request.script_root + flask.request.path + '/' + id
        data = flask.render_template(
           'session.json',
           id=id,
           username=username,
           location=location,
         )
        resp = flask.Response(data)
        resp.headers['X-Auth-Token'] = token
        resp.headers['Location'] = location
        return resp

    return flask.render_template(
        'fake_session.json',
        url=flask.request.script_root + flask.request.path,
        id_list=[sessions[key]['id'] for key in sessions.keys()],
        count=len(sessions),
     )

@app.route('/redfish/v1/SessionService/Sessions/<sessionid>', methods=['GET', 'DELETE'])
def session_resource(sessionid):
    global sessions
    if flask.request.method == 'DELETE':
        for token in sessions.keys():
            if sessionid in sessions[token]['id']:
                sessions.pop(token)
                app.logger.info('Number of sessions: ' + str(len(sessions)))
                return '', 200
        return '', 404

    for token in sessions.keys():
        if sessionid in sessions[token]['id']:
            return flask.render_template(
                'session.json',
                id=sessionid,
                username=sessions[token]['decoded_creds'].split(':', 1)[0],
                location=flask.request.script_root + flask.request.path
             )
    return '', 404

@app.route('/redfish/v1/Chassis')
def chassis_collection_resource():
    return flask.render_template('chassis.json')

@app.route('/redfish/v1/Systems')
def system_collection_resource():
    return flask.render_template('systems.json')

@app.route('/redfish/v1/Systems/1', methods=['GET', 'PATCH'])
def system_resource():
    username, password = get_credentials(flask.request)
    global bmc_ip
    global power_state
    global bootsourceoverride_enabled
    global bootsourceoverride_target
    global bootsourceoverride_mode
    if flask.request.method == 'GET':
       return flask.render_template(
           'fake_system.json',
           power_state=power_state,
           bootsourceoverride_enabled=bootsourceoverride_enabled,
           bootsourceoverride_target=bootsourceoverride_target,
           bootsourceoverride_mode=bootsourceoverride_mode,
        )
    else:
       app.logger.info('patch request')
       boot = flask.request.json.get('Boot')
       if not boot:
           return ('PATCH only works for Boot'), 400
       if boot:
           enabled = boot.get('BootSourceOverrideEnabled', bootsourceoverride_enabled)
           target = boot.get('BootSourceOverrideTarget', bootsourceoverride_target)
           mode = boot.get('BootSourceOverrideMode', bootsourceoverride_mode)
           if not target and not mode:
               return ('Missing the BootSourceOverrideTarget and/or '
                       'BootSourceOverrideMode element', 400)
           else:
               app.logger.info('Running script that sets boot from VirtualCD once')
               try:
                   my_env = set_env_vars(bmc_ip, username, password)
                   my_env['BOOTSOURCEOVERRIDE_ENABLED'] = enabled
                   my_env['BOOTSOURCEOVERRIDE_TARGET'] = target
                   my_env['BOOTSOURCEOVERRIDE_MODE'] = mode
                   subprocess.check_call(['custom_scripts/bootfromcdonce.sh'], env=my_env)
               except subprocess.CalledProcessError as e:
                   return ('Failed to set boot from virtualcd once', 400)

               bootsourceoverride_enabled = enabled
               bootsourceoverride_target = target
               bootsourceoverride_mode = mode
               return '', 204

@app.route('/redfish/v1/Systems/1/EthernetInterfaces', methods=['GET'])
def manage_interfaces():
    return flask.render_template('fake_interfaces.json')

@app.route('/redfish/v1/Chassis/1', methods=['GET'])
def chassis_resource():
    global power_state
    return flask.render_template(
           'fake_chassis.json',
           power_state=power_state,
        )

@app.route('/redfish/v1/Chassis/1/Power', methods=['GET'])
def manage_power():
    return flask.render_template('fake_power.json')

@app.route('/redfish/v1/Chassis/1/Thermal', methods=['GET'])
def manage_thermal():
    return flask.render_template('fake_thermal.json')

@app.route('/redfish/v1/Managers/1', methods=['GET'])
def manager_resource():
    return flask.render_template(
           'fake_manager.json',
           date_time=datetime.now().strftime('%Y-%M-%dT%H:%M:%S+00:00'),
        )

@app.route('/redfish/v1/Systems/1/Actions/ComputerSystem.Reset',
           methods=['POST'])
def system_reset_action():
    global bmc_ip
    global bootsourceoverride_enabled
    global bootsourceoverride_target
    global bootsourceoverride_mode
    username, password = get_credentials(flask.request)
    reset_type = flask.request.json.get('ResetType')
    global power_state
    if reset_type == 'On':
        app.logger.info('Running script that powers on the server')
        try:
            my_env = set_env_vars(bmc_ip, username, password)
            subprocess.check_call(['custom_scripts/poweron.sh'], env=my_env)
        except subprocess.CalledProcessError as e:
            return ('Failed to poweron the server', 400)
        power_state = 'On'

        bootsourceoverride_enabled = 'Disabled'
        bootsourceoverride_target = 'None'
        bootsourceoverride_mode = 'UEFI'

    else:
        app.logger.info('Running script that powers off the server')
        try:
            my_env = set_env_vars(bmc_ip, username, password)
            subprocess.check_call(['custom_scripts/poweroff.sh'], env=my_env)
        except subprocess.CalledProcessError as e:
            return ('Failed to poweroff the server', 400)
        power_state = 'Off'

    return '', 204


@app.route('/redfish/v1/Managers/1/VirtualMedia', methods=['GET'])
def virtualmedia_collection_resource():
    return flask.render_template('virtualmedias.json')

@app.route('/redfish/v1/Managers/1/VirtualMedia/Cd', methods=['GET'])
def virtualmedia_cd_resource():
    global inserted
    return flask.render_template(
        'virtualmedia_cd.json',
        inserted=inserted,
        image_url=image_url,
        )

@app.route('/redfish/v1/Managers/1/VirtualMedia/Cd/Actions/VirtualMedia.InsertMedia',
          methods=['POST'])
def virtualmedia_insert():
    global bmc_ip
    username, password = get_credentials(flask.request)
    image = flask.request.json.get('Image')
    if not image:
        return('POST only works for Image'), 400
    else:
        global inserted
        global image_url
        inserted = True
        image_url = image
        app.logger.info('Running script that mounts cd with iso %s', image)
        try:
            my_env = set_env_vars(bmc_ip, username, password)
            subprocess.check_call(['custom_scripts/mountcd.sh', image_url], env=my_env)
        except subprocess.CalledProcessError as e:
            return ('Failed to mount virtualcd', 400)
        return '', 204

@app.route('/redfish/v1/Managers/1/VirtualMedia/Cd/Actions/VirtualMedia.EjectMedia',
          methods=['POST'])
def virtualmedia_eject():
    global bmc_ip
    global inserted
    global image_url
    username, password = get_credentials(flask.request)
    inserted = False
    image_url = ''
    app.logger.info('Running script that unmounts cd')
    try:
        my_env = set_env_vars(bmc_ip, username, password)
        subprocess.check_call(['custom_scripts/unmountcd.sh'], env=my_env)
    except subprocess.CalledProcessError as e:
        return ('Failed to unmount virtualcd', 400)
    return '', 204


def get_credentials(flask_request):
    global sessions
    username = ''
    password = ''
    token = flask_request.headers.get('X-Auth-Token', None)
    if token is not None:
        session = sessions.get(token, None)
        if session is not None:
            decoded_creds = session['decoded_creds']
    else:
        auth = flask_request.headers.get('Authorization', None)
        if auth is not None and auth.startswith('Basic '):
            encoded_creds = auth.split(' ', 1)[1]
            decoded_creds = base64.b64decode(encoded_creds).decode('utf-8')

    if decoded_creds is not None:
        username, password = decoded_creds.split(':', 1)

    app.logger.info('Returning credentials')
    app.logger.info('Username: ' + username + ', password: ' + password)
    return username, password

def set_env_vars(bmc_endpoint, username, password):
    my_env = os.environ.copy()
    my_env["BMC_ENDPOINT"] = bmc_endpoint
    my_env["BMC_USERNAME"] = username
    my_env["BMC_PASSWORD"] = password
    return my_env

def run(port, debug, tls_mode, cert_file, key_file):
    """

    """
    if tls_mode == 'adhoc':
        app.run(host='::', port=port, debug=debug, ssl_context='adhoc')
    elif tls_mode == 'disabled':
        app.run(host='::', port=port, debug=debug)
    else:
        if os.path.exists(cert_file) and os.path.exists(key_file):
            app.run(host='::', port=port, debug=debug, ssl_context=(cert_file, key_file))
        else:
            app.logger.error('%s or %s not found.', cert_file, key_file)
            exit()


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description='FakeFish, an experimental RedFish proxy that calls shell scripts for executing hardware actions.')
    parser.add_argument('--tls-mode', type=str, choices=['adhoc', 'self-signed', 'disabled'], default='adhoc', help='Configures TLS mode. \
                        \'self-signed\' mode expects users to configure a cert and a key files. (default: %(default)s)')
    parser.add_argument('--cert-file', type=str, default='./cert.pem', help='Path to the certificate public key file. (default: %(default)s)')
    parser.add_argument('--key-file', type=str, default='./cert.key', help='Path to the certificate private key file. (default: %(default)s)')
    parser.add_argument('-r', '--remote-bmc', type=str, required=True, help='The BMC IP this FakeFish instance will connect to. e.g: 192.168.1.10')
    parser.add_argument('-p','--listen-port', type=int, required=False, default=9000, help='The port where this FakeFish instance will listen for connections.')
    parser.add_argument('--debug', action='store_true')
    args = parser.parse_args()

    bmc_ip = args.remote_bmc
    port = args.listen_port
    debug = args.debug
    tls_mode = args.tls_mode
    cert_file = args.cert_file
    key_file = args.key_file

    inserted = False
    image_url = ''
    power_state = 'On'
    run(port, debug, tls_mode, cert_file, key_file)
