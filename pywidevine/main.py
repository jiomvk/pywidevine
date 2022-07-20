import logging
from datetime import datetime
from pathlib import Path

import click
import requests

from pywidevine import __version__
from pywidevine.cdm import Cdm
from pywidevine.device import Device
from pywidevine.license_protocol_pb2 import LicenseType


@click.group(invoke_without_command=True)
@click.option("-v", "--version", is_flag=True, default=False, help="Print version information.")
@click.option("-d", "--debug", is_flag=True, default=False, help="Enable DEBUG level logs.")
def main(version: bool, debug: bool) -> None:
    """pywidevine—Python Widevine CDM implementation."""
    logging.basicConfig(level=logging.DEBUG if debug else logging.INFO)
    log = logging.getLogger()

    copyright_years = 2022
    current_year = datetime.now().year
    if copyright_years != current_year:
        copyright_years = f"{copyright_years}-{current_year}"

    log.info(f"pywidevine version {__version__} Copyright (c) {copyright_years} rlaphoenix")
    log.info("https://github.com/rlaphoenix/pywidevine")
    if version:
        return


@main.command(name="license")
@click.argument("device", type=Path)
@click.argument("pssh", type=str)
@click.argument("server", type=str)
@click.option("-t", "--type", "type_", type=click.Choice(LicenseType.keys(), case_sensitive=False),
              default="STREAMING",
              help="License Type to Request.")
@click.option("-r", "--raw", is_flag=True, default=False,
              help="PSSH is Raw.")
@click.option("-p", "--privacy", is_flag=True, default=False,
              help="Use Privacy Mode, off by default.")
def license_(device: Path, pssh: str, server: str, type_: str, raw: bool, privacy: bool):
    """
    Make a License Request for PSSH to SERVER using DEVICE.
    It will return a list of all keys within the returned license.

    This expects the Licence Server to be a simple opaque interface where the Challenge
    is sent as is (as bytes), and the License response is returned as is (as bytes).
    This is a common behavior for some License Servers and is our only option for a generic
    licensing function.

    You may modify this function to change how it sends the Challenge and how it parses
    the License response. However, for non-generic license calls, I recommend creating a
    new script that imports and uses the pywidevine module instead. This generic function
    is only useful as a quick generic license call.

    This is also a great way of showing you how to use pywidevine in your own projects.
    """
    log = logging.getLogger("license")

    type_ = LicenseType.Value(type_)

    # load device
    device = Device.load(device)
    log.info(f"[+] Loaded Device ({device.system_id} L{device.security_level})")
    log.debug(device)

    # load cdm
    cdm = Cdm(device, pssh, type_, raw)
    log.info(f"[+] Loaded CDM with PSSH: {pssh}")
    log.debug(cdm)

    if privacy:
        # get service cert for license server via cert challenge
        service_cert = requests.post(
            url=server,
            data=cdm.service_certificate_challenge
        )
        if service_cert.status_code != 200:
            log.error(f"[-] Failed to get Service Privacy Certificate: [{service_cert.status_code}] {service_cert.text}")
            return
        service_cert = service_cert.content
        cdm.set_service_certificate(service_cert)
        log.info("[+] Set Service Privacy Certificate")
        log.debug(service_cert)

    # get license challenge
    challenge = cdm.get_license_challenge(privacy_mode=True)
    log.info("[+] Created License Request Message (Challenge)")
    log.debug(challenge)

    # send license challenge
    licence = requests.post(
        url=server,
        data=challenge
    )
    if licence.status_code != 200:
        log.error(f"[-] Failed to send challenge: [{licence.status_code}] {licence.text}")
        return
    licence = licence.content
    log.info("[+] Got License Message")
    log.debug(licence)

    # parse license challenge
    keys = cdm.parse_license(licence)
    log.info("[+] License Parsed Successfully")

    # print keys
    for key in keys:
        log.info(f"[{key.type}] {key.kid.hex}:{key.key.hex()}")
